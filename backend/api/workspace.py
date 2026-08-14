import uuid
import json
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Literal

from backend.database import get_db, fetch_all, fetch_one
from backend.agents.base import chat_text, chat_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_background_tasks: set = set()

VALID_STATUS = {"draft", "finalized", "locked"}
VALID_ITEM_TYPES = {
    "story_core", "world_setting", "character_setting",
    "outline", "outline_reverse", "foreshadow",
    "chapter_plan", "chapter",
}
STATUS_TRANSITIONS = {
    "draft": {"finalized", "locked"},
    "finalized": {"locked", "draft"},
    "locked": {"draft"},
}

SUMMARIZE_MSG_PROMPTS = {
    "world_setting": """你是一个小说世界观设定整理助手。请将以下对话内容整理为结构化的世界观设定文档。

要求：
1. 提取核心设定，去除对话中的冗余内容
2. 用 Markdown 格式，以 ## 副标题开头组织各部分
3. 保持逻辑清晰，分类明确

返回 JSON 格式：
{
  "subtitle": "概括性副标题（2-6个字）",
  "content": "整理后的 Markdown 内容（以 ## 副标题开头）"
}""",
    "character_setting": """你是一个小说角色设定整理助手。请将以下对话内容整理为结构化的角色设定。

要求：
1. 提取角色的关键设定信息
2. 用 Markdown 格式组织
3. 包含外貌、性格、背景、能力等维度

返回 JSON 格式：
{
  "subtitle": "角色名或概括（2-6个字）",
  "content": "整理后的 Markdown 内容（以 ## 副标题开头）"
}""",
    "outline": """你是一个小说大纲整理助手。请将以下对话内容整理为结构化的大纲。

要求：
1. 提取情节脉络和关键节点
2. 用 Markdown 格式组织
3. 按章节或卷划分

返回 JSON 格式：
{
  "subtitle": "大纲概括（2-6个字）",
  "content": "整理后的 Markdown 内容（以 ## 副标题开头）"
}""",
    "chapter": """你是一个小说章节整理助手。请将以下内容整理为正式的章节正文。

要求：
1. 保持文学性和可读性
2. 修正格式和排版

返回 JSON 格式：
{
  "subtitle": "章节标题",
  "content": "整理后的正文"
}""",
}

SYNC_WORKSPACE_PROMPT = """你是一个小说创作工作台同步助手。请对比 AI 的最新回复与已有工作台条目，找出需要更新的内容。

判断规则：
1. 如果 AI 回复中包含对已有条目的补充或修正，标记为 "update"
2. 如果 AI 回复中包含全新的设定信息，标记为 "create"
3. 如果不确定，标记为 "suggest"

返回 JSON 格式：
{
  "updates": [
    {"item_id": "已有条目ID", "action": "update", "new_content": "追加或替换的内容", "reason": "原因"}
  ],
  "suggestions": [
    {"item_type": "world_setting", "title": "建议标题", "content": "内容", "reason": "原因"}
  ]
}"""

INSPIRATION_PROMPT = """你是一个小说创作灵感整理助手。请从以下用户消息中提取所有有价值的创作灵感和设定信息。

要求：
1. 提取所有关于世界观、角色、情节的设定信息
2. 合并重复内容
3. 用 Markdown 格式输出

返回 JSON 格式：
{
  "subtitle": "灵感概括（2-6个字）",
  "content": "整理后的 Markdown 内容"
}"""

EXTRACT_QUESTIONS_PROMPT = """你是一个小说创作助手。请分析当前项目状态，找出需要用户确认的关键问题。

要求：
1. 只提出对创作有实质影响的问题
2. 每个问题提供2-4个选项建议
3. 不要超过 6 个问题

返回 JSON 格式：
{
  "questions": [
    {
      "id": "q1",
      "question": "问题内容",
      "context": "为什么需要确认这个问题",
      "options": ["选项1", "选项2", "选项3"]
    }
  ]
}"""


class WorkspaceItemCreate(BaseModel):
    item_type: Literal[
        "story_core", "world_setting", "character_setting",
        "outline", "outline_reverse", "foreshadow",
        "chapter_plan", "chapter",
    ]
    title: str = ""
    subtitle: str = ""
    content: str = ""
    metadata: dict = {}
    chapter_number: int | None = None
    status: str = "draft"


class WorkspaceItemUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    content: str | None = None
    metadata: dict | None = None


_WS_ALLOWED_FIELDS = {"title", "subtitle", "content", "metadata"}


class StatusUpdate(BaseModel):
    status: Literal["draft", "finalized", "locked"]

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in VALID_STATUS:
            raise ValueError(f"Invalid status: {v}")
        return v


class SummarizeMessageRequest(BaseModel):
    content: str
    item_type: str


class SyncRequest(BaseModel):
    ai_message: str
    workspace_items: list[dict]


class GenerateItemRequest(BaseModel):
    item_type: str
    conversation_history: list[dict] = []


@router.get("/projects/{project_id}/workspace")
async def list_workspace_items(project_id: str):
    db = await get_db()
    rows = await fetch_all(
        db,
        "SELECT * FROM workspace_items WHERE project_id = ? ORDER BY sort_order ASC, created_at ASC",
        (project_id,),
    )
    return rows


@router.post("/projects/{project_id}/workspace")
async def create_workspace_item(project_id: str, body: WorkspaceItemCreate):
    db = await get_db()
    item_id = str(uuid.uuid4())

    if body.item_type == "chapter":
        if body.chapter_number is None:
            row = await fetch_one(
                db,
                "SELECT MAX(chapter_number) as mx FROM workspace_items WHERE project_id = ? AND item_type = 'chapter'",
                (project_id,),
            )
            chapter_number = (row["mx"] or 0) + 1 if row else 1
        else:
            chapter_number = body.chapter_number
    else:
        chapter_number = None

    sort_row = await fetch_one(
        db,
        "SELECT MAX(sort_order) as mx FROM workspace_items WHERE project_id = ?",
        (project_id,),
    )
    sort_order = (sort_row["mx"] or 0) + 1 if sort_row else 1

    metadata_json = json.dumps(body.metadata, ensure_ascii=False)
    await db.execute(
        """INSERT INTO workspace_items (id, project_id, item_type, status, title, subtitle, content, metadata, chapter_number, sort_order)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_id, project_id, body.item_type, body.status, body.title, body.subtitle, body.content, metadata_json, chapter_number, sort_order),
    )
    await db.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
    await db.commit()

    return {
        "id": item_id,
        "project_id": project_id,
        "item_type": body.item_type,
        "status": body.status,
        "title": body.title,
        "subtitle": body.subtitle,
        "metadata": body.metadata,
        "content": body.content,
        "chapter_number": chapter_number,
        "sort_order": sort_order,
    }


@router.put("/workspace/{item_id}")
async def update_workspace_item(item_id: str, body: WorkspaceItemUpdate):
    db = await get_db()
    item = await fetch_one(db, "SELECT * FROM workspace_items WHERE id = ?", (item_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item["status"] == "locked":
        raise HTTPException(status_code=409, detail="Item is locked and cannot be edited")

    fields = {k: v for k, v in body.model_dump().items() if v is not None and k in _WS_ALLOWED_FIELDS}
    if not fields:
        return item

    if "metadata" in fields:
        fields["metadata"] = json.dumps(fields["metadata"], ensure_ascii=False)

    set_parts = [f"{k} = ?" for k in fields]
    values = list(fields.values())
    values.append(item_id)

    await db.execute(
        f"UPDATE workspace_items SET {', '.join(set_parts)}, updated_at = datetime('now') WHERE id = ?",
        values,
    )
    await db.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (item["project_id"],))
    await db.commit()

    updated = await fetch_one(db, "SELECT * FROM workspace_items WHERE id = ?", (item_id,))
    return updated


@router.put("/workspace/{item_id}/status")
async def update_item_status(item_id: str, body: StatusUpdate):
    db = await get_db()
    item = await fetch_one(db, "SELECT * FROM workspace_items WHERE id = ?", (item_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    current_status = item["status"]
    new_status = body.status

    if current_status != new_status:
        allowed = STATUS_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot transition from '{current_status}' to '{new_status}'",
            )

    await db.execute(
        "UPDATE workspace_items SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (new_status, item_id),
    )
    await db.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (item["project_id"],))
    await db.commit()

    if item["item_type"] == "chapter" and new_status in ("finalized", "locked"):
        task = asyncio.create_task(
            _trigger_chronicle_update(item["project_id"], item["title"] or "", item["content"] or "")
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        meta = {}
        if item["metadata"]:
            try:
                meta = json.loads(item["metadata"])
            except (json.JSONDecodeError, TypeError):
                meta = {}
        if not meta.get("summary"):
            sum_task = asyncio.create_task(
                _generate_chapter_summary(item_id, item["title"] or "", item["content"] or "")
            )
            _background_tasks.add(sum_task)
            sum_task.add_done_callback(_background_tasks.discard)

    updated = await fetch_one(db, "SELECT * FROM workspace_items WHERE id = ?", (item_id,))
    return updated


@router.delete("/workspace/{item_id}")
async def delete_workspace_item(item_id: str):
    db = await get_db()
    item = await fetch_one(db, "SELECT * FROM workspace_items WHERE id = ?", (item_id,))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item["status"] == "locked":
        raise HTTPException(status_code=409, detail="Item is locked and cannot be deleted")

    await db.execute("DELETE FROM workspace_items WHERE id = ?", (item_id,))
    await db.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (item["project_id"],))
    await db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/summarize-message")
async def summarize_message(project_id: str, body: SummarizeMessageRequest):
    prompt = SUMMARIZE_MSG_PROMPTS.get(body.item_type)
    if not prompt:
        raise HTTPException(status_code=400, detail=f"Unknown item type: {body.item_type}")

    result = await chat_json(
        messages=[{"role": "user", "content": body.content}],
        system_prompt=prompt,
        temperature=0.3,
    )

    if "error" in result:
        raise HTTPException(status_code=502, detail="AI 返回格式错误，请重试")

    subtitle = result.get("subtitle", "")
    content = result.get("content", "")
    db = await get_db()
    existing = await fetch_one(
        db,
        "SELECT id, title, subtitle, content FROM workspace_items WHERE project_id = ? AND item_type = ? ORDER BY sort_order LIMIT 1",
        (project_id, body.item_type),
    )
    return {
        "item_type": body.item_type,
        "subtitle": subtitle,
        "content": content,
        "existing": existing,
    }


@router.post("/projects/{project_id}/summarize")
async def summarize_to_workspace(project_id: str):
    db = await get_db()
    rows = await fetch_all(
        db,
        "SELECT role, content FROM messages m JOIN conversations c ON m.conversation_id = c.id WHERE c.project_id = ? AND m.role = 'user' ORDER BY m.created_at",
        (project_id,),
    )
    if not rows:
        raise HTTPException(status_code=400, detail="没有用户消息可整理")

    all_text = "\n\n".join(r["content"] for r in rows)

    result = await chat_json(
        messages=[{"role": "user", "content": all_text}],
        system_prompt=INSPIRATION_PROMPT,
        temperature=0.5,
    )

    if "error" in result:
        raise HTTPException(status_code=502, detail="AI 返回格式错误，请重试")

    subtitle = result.get("subtitle", "灵感笔记")
    content = result.get("content", "")

    existing = await fetch_one(
        db,
        "SELECT id, title, content FROM workspace_items WHERE project_id = ? AND item_type = 'world_setting' ORDER BY sort_order LIMIT 1",
        (project_id,),
    )

    if existing:
        old_content = (existing["content"] or "").rstrip()
        max_length = 50000
        if len(old_content) > max_length:
            old_content = old_content[-max_length:]
        new_content = old_content + "\n\n" + f"## {subtitle}\n\n{content}"
        await db.execute(
            "UPDATE workspace_items SET content = ?, updated_at = datetime('now') WHERE id = ?",
            (new_content, existing["id"]),
        )
        await db.commit()
        return {"id": existing["id"], "action": "appended", "subtitle": subtitle}
    else:
        item_id = str(uuid.uuid4())
        sort_row = await fetch_one(
            db,
            "SELECT MAX(sort_order) as mx FROM workspace_items WHERE project_id = ?",
            (project_id,),
        )
        sort_order = (sort_row["mx"] or 0) + 1 if sort_row else 1
        full_content = f"## {subtitle}\n\n{content}"
        await db.execute(
            """INSERT INTO workspace_items (id, project_id, item_type, status, title, subtitle, content, sort_order)
               VALUES (?, ?, 'world_setting', 'draft', ?, ?, ?, ?)""",
            (item_id, project_id, "灵感笔记", subtitle, full_content, sort_order),
        )
        await db.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
        await db.commit()
        return {"id": item_id, "action": "created", "subtitle": subtitle}


@router.post("/projects/{project_id}/sync-workspace")
async def sync_to_workspace(project_id: str, body: SyncRequest):
    db = await get_db()
    items_text = "\n\n".join(
        f"[ID: {it.get('id','')}] 类型:{it.get('item_type','')} 标题:{it.get('title','')}\n{it.get('content','')}"
        for it in body.workspace_items
    )

    user_content = f"已有条目：\n\n{items_text}\n\n---\n\nAI 的最新回复：\n\n{body.ai_message}"

    result = await chat_json(
        messages=[{"role": "user", "content": user_content}],
        system_prompt=SYNC_WORKSPACE_PROMPT,
        temperature=0.3,
    )

    if "error" in result:
        raise HTTPException(status_code=502, detail="AI 返回格式错误，请重试")

    updates = result.get("updates", [])
    suggestions = result.get("suggestions", [])

    for upd in updates:
        item_id = upd.get("item_id")
        action = upd.get("action")
        new_content = upd.get("new_content", "")
        if action == "update" and item_id and new_content:
            item = await fetch_one(db, "SELECT content, status FROM workspace_items WHERE id = ?", (item_id,))
            if item and item["status"] != "locked":
                merged = (item["content"] or "").rstrip() + "\n\n" + new_content
                await db.execute(
                    "UPDATE workspace_items SET content = ?, updated_at = datetime('now') WHERE id = ?",
                    (merged, item_id),
                )

    for sug in suggestions:
        item_type = sug.get("item_type", "world_setting")
        title = sug.get("title", "")
        content = sug.get("content", "")
        if content:
            item_id = str(uuid.uuid4())
            sort_row = await fetch_one(
                db,
                "SELECT MAX(sort_order) as mx FROM workspace_items WHERE project_id = ?",
                (project_id,),
            )
            sort_order = (sort_row["mx"] or 0) + 1 if sort_row else 1
            await db.execute(
                """INSERT INTO workspace_items (id, project_id, item_type, status, title, content, sort_order)
                   VALUES (?, ?, ?, 'draft', ?, ?, ?)""",
                (item_id, project_id, item_type, title, content, sort_order),
            )

    await db.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
    await db.commit()

    return {"updates": updates, "suggestions": suggestions}


@router.post("/projects/{project_id}/generate-item")
async def generate_item(project_id: str, body: GenerateItemRequest):
    history_text = "\n".join(
        f"{'用户' if m.get('role') == 'user' else '助手'}: {m.get('content', '')}"
        for m in body.conversation_history[-20:]
    )

    prompt = f"请根据以下对话历史，生成一份{body.item_type}的内容。用 Markdown 格式输出。\n\n对话历史：\n{history_text}"

    content = await chat_text(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    return {"item_type": body.item_type, "content": content}


@router.post("/projects/{project_id}/extract-questions")
async def extract_questions(project_id: str):
    db = await get_db()
    items = await fetch_all(
        db,
        "SELECT item_type, title, content, status FROM workspace_items WHERE project_id = ? ORDER BY sort_order",
        (project_id,),
    )

    context = "\n\n".join(
        f"[{it['item_type']}] {it['title'] or ''} ({it['status']})\n{(it['content'] or '')[:500]}"
        for it in items
    )

    if not context.strip():
        return {"questions": []}

    result = await chat_json(
        messages=[{"role": "user", "content": f"当前项目设定：\n\n{context}"}],
        system_prompt=EXTRACT_QUESTIONS_PROMPT,
        temperature=0.5,
    )

    if "error" in result:
        return {"questions": []}

    return {"questions": result.get("questions", [])}


CHAPTER_SUMMARY_PROMPT = """你是一个小说章节摘要专家。请将以下章节内容浓缩为一段200-300字的摘要，用于后续章节创作时的上下文参考。

摘要要求：
1. 包含本章的关键剧情进展
2. 重要角色的行动和变化
3. 关键冲突和转折
4. 为后续剧情埋下的伏笔（如有）

只输出摘要正文，不要标题、不要分点、不要任何解释。"""


async def _generate_chapter_summary(item_id: str, chapter_title: str, chapter_content: str):
    try:
        summary = await chat_text(
            messages=[{"role": "user", "content": f"章节标题：{chapter_title}\n\n章节内容：\n{chapter_content}"}],
            system_prompt=CHAPTER_SUMMARY_PROMPT,
            temperature=0.3,
        )
        summary = (summary or "").strip()
        if not summary:
            return
        db = await get_db()
        row = await fetch_one(db, "SELECT metadata FROM workspace_items WHERE id = ?", (item_id,))
        if not row:
            return
        meta = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except (json.JSONDecodeError, TypeError):
                meta = {}
        meta["summary"] = summary
        await db.execute(
            "UPDATE workspace_items SET metadata = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(meta, ensure_ascii=False), item_id),
        )
        await db.commit()
        logger.info("[chapter-summary] generated for item %s, len=%d", item_id, len(summary))
    except Exception as e:
        logger.warning("[chapter-summary] failed for item %s: %s", item_id, e)


async def _trigger_chronicle_update(project_id: str, chapter_title: str, chapter_content: str):
    try:
        from backend.agents.chronicle import update_chronicle

        db = await get_db()

        chronicle_row = await fetch_one(
            db,
            "SELECT * FROM chronicle WHERE project_id = ?",
            (project_id,),
        )

        world_rows = await fetch_all(
            db,
            "SELECT content FROM workspace_items WHERE project_id = ? AND item_type = 'world_setting' AND status IN ('locked', 'finalized')",
            (project_id,),
        )
        world_text = "\n\n".join(r["content"] for r in world_rows[:3]) if world_rows else ""

        current = {
            "timeline": json.loads(chronicle_row["timeline"]) if chronicle_row and chronicle_row["timeline"] else [],
            "characters": json.loads(chronicle_row["characters"]) if chronicle_row and chronicle_row["characters"] else [],
            "key_events": json.loads(chronicle_row["key_events"]) if chronicle_row and chronicle_row["key_events"] else [],
            "unresolved_threads": json.loads(chronicle_row["unresolved_threads"]) if chronicle_row and chronicle_row["unresolved_threads"] else [],
        }

        updated = await update_chronicle(
            current,
            chapter_title,
            chapter_content,
            world_text,
        )

        if chronicle_row:
            raw_parts = []
            for tl in updated.get("timeline", []):
                raw_parts.append(f"[{tl.get('time','')}] {tl.get('event','')}")
            raw_text = "\n".join(raw_parts)

            await db.execute(
                """UPDATE chronicle SET timeline = ?, characters = ?, key_events = ?, unresolved_threads = ?, raw_text = ?, updated_at = datetime('now')
                   WHERE project_id = ?""",
                (
                    json.dumps(updated.get("timeline", []), ensure_ascii=False),
                    json.dumps(updated.get("characters", []), ensure_ascii=False),
                    json.dumps(updated.get("key_events", []), ensure_ascii=False),
                    json.dumps(updated.get("unresolved_threads", []), ensure_ascii=False),
                    raw_text,
                    project_id,
                ),
            )
        else:
            await db.execute(
                """INSERT INTO chronicle (project_id, timeline, characters, key_events, unresolved_threads, raw_text)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    project_id,
                    json.dumps(updated.get("timeline", []), ensure_ascii=False),
                    json.dumps(updated.get("characters", []), ensure_ascii=False),
                    json.dumps(updated.get("key_events", []), ensure_ascii=False),
                    json.dumps(updated.get("unresolved_threads", []), ensure_ascii=False),
                    "",
                ),
            )

        await db.commit()
        logger.info("Chronicle updated for project=%s chapter=%s", project_id, chapter_title)

    except Exception as e:
        logger.exception("Chronicle update failed for project=%s: %s", project_id, e)
