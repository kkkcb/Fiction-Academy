import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db
from backend.agents.chronicle import update_chronicle
from backend.agents.base import chat_text, chat_json

router = APIRouter()


class WorkspaceItemCreate(BaseModel):
    item_type: str
    title: str
    subtitle: str = ""
    content: str = ""
    chapter_number: Optional[int] = None


class WorkspaceItemUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    content: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


@router.get("/projects/{project_id}/workspace")
async def list_workspace_items(project_id: str):
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE project_id = ? ORDER BY sort_order",
        (project_id,),
    )
    return [dict(row) for row in cursor]


@router.post("/projects/{project_id}/workspace")
async def create_workspace_item(project_id: str, body: WorkspaceItemCreate):
    db = await get_db()
    item_id = str(uuid.uuid4())

    if body.item_type == "chapter":
        cursor = await db.execute_fetchall(
            "SELECT MAX(chapter_number) as max_cn FROM workspace_items WHERE project_id = ? AND item_type = 'chapter'",
            (project_id,),
        )
        max_cn = cursor[0]["max_cn"]
        chapter_number = (max_cn or 0) + 1
    else:
        chapter_number = body.chapter_number

    cursor = await db.execute_fetchall(
        "SELECT MAX(sort_order) as max_so FROM workspace_items WHERE project_id = ?",
        (project_id,),
    )
    max_so = cursor[0]["max_so"]
    sort_order = (max_so or 0) + 1

    await db.execute(
        """INSERT INTO workspace_items (id, project_id, item_type, status, title, subtitle, content, chapter_number, sort_order)
        VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, ?)""",
        (item_id, project_id, body.item_type, body.title, getattr(body, 'subtitle', '') or '', body.content, chapter_number, sort_order),
    )
    await db.commit()

    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE id = ?", (item_id,),
    )
    return dict(cursor[0])


EXTRACT_QUESTIONS_PROMPT = """你是一位细心的小说创作助手。用户会给你一段他们在对话中说过的话。

你的任务：找出用户提到的每一个**关键名词、概念、设定**，如果这个名词/概念在小说创作中还有可发挥空间、需要进一步明确，就针对它生成一个反向确认问题，并给出 2-3 个建议选项。

规则：
1. 只针对用户提到的具体名词/概念提问，不要泛泛而问
2. 每个问题给出 2-3 个常见/有创意的选项建议，方便用户快速选择
3. 如果用户说的信息已经很完整，没有需要确认的，返回空数组
4. 不要超过 6 个问题

返回 JSON 格式：
{
  "questions": [
    {
      "keyword": "剑修",
      "question": "剑修的修炼体系有几个大境界？",
      "options": ["三境（练气、筑基、金丹）", "五境（练气、筑基、金丹、元婴、化神）", "九境（完整的修仙体系）"]
    },
    ...
  ]
}

如果没有任何需要确认的内容，返回：{"questions": []}"""


class ExtractQuestionsRequest(BaseModel):
    user_messages: list[str]


@router.post("/projects/{project_id}/extract-questions")
async def extract_questions(project_id: str, body: ExtractQuestionsRequest):
    combined = "\n\n".join(f"用户说：{msg}" for msg in body.user_messages)
    result = await chat_json(
        messages=[{"role": "user", "content": combined}],
        system_prompt=EXTRACT_QUESTIONS_PROMPT,
    )
    return result


class GenerateItemRequest(BaseModel):
    item_type: str
    conversation_messages: list[dict]


WORLD_SETTING_PROMPT = """你是一位专业的小说世界观设定师。根据用户和AI的对话历史，提取并整理出一份完整的世界观设定文档。

要求：
1. 从对话中提取所有与世界观相关的信息（地理、势力、规则、历史等）
2. 如果信息不完整，根据已有线索合理补充，但标注为「待确认」
3. 用结构化的格式组织（使用标题、列表等）
4. 输出 Markdown 格式
5. 直接输出内容，不要加前缀说明"""

CHARACTER_SETTING_PROMPT = """你是一位专业的小说角色设计师。根据用户和AI的对话历史，提取并整理出角色设定文档。

要求：
1. 从对话中提取所有角色相关信息（姓名、外貌、性格、能力、背景、人际关系等）
2. 如果信息不完整，根据已有线索合理补充，但标注为「待确认」
3. 每个角色一个独立章节，包含：基本信息、性格特点、能力设定、人物关系、背景故事
4. 输出 Markdown 格式
5. 直接输出内容，不要加前缀说明"""

OUTLINE_PROMPT = """你是一位专业的小说大纲策划师。根据用户和AI的对话历史，提取并整理出故事大纲文档。

要求：
1. 从对话中提取所有与剧情相关的内容（主线、支线、关键事件、转折点等）
2. 按时间线或章节结构组织
3. 如果信息不完整，根据已有线索合理补充，但标注为「待确认」
4. 输出 Markdown 格式
5. 直接输出内容，不要加前缀说明"""

ITEM_TYPE_PROMPTS = {
    "world_setting": WORLD_SETTING_PROMPT,
    "character_setting": CHARACTER_SETTING_PROMPT,
    "outline": OUTLINE_PROMPT,
}

ITEM_TYPE_TITLES = {
    "world_setting": "世界观设定",
    "character_setting": "角色设定",
    "outline": "故事大纲",
}


SUMMARIZE_MSG_PROMPTS = {
    "world_setting": """你是一位专业的小说世界观设定师。请从以下AI回复内容中，提取并整理出世界观相关的设定信息。

要求：
1. 提取所有与世界观相关的信息（地理、势力、规则、历史、修炼体系等）
2. 用结构化的格式组织（使用标题、列表等）
3. 只提取内容中明确提到的信息，不要补充
4. 输出 Markdown 格式，直接输出内容""",

    "character_setting": """你是一位专业的小说角色设计师。请从以下AI回复内容中，提取并整理出角色相关的设定信息。

要求：
1. 提取所有角色相关信息（姓名、外貌、性格、能力、背景、人际关系等）
2. 每个角色一个独立章节
3. 只提取内容中明确提到的信息，不要补充
4. 输出 Markdown 格式，直接输出内容""",

    "outline": """你是一位专业的小说大纲策划师。请从以下AI回复内容中，提取并整理出剧情大纲相关的信息。

要求：
1. 提取所有与剧情相关的内容（主线、支线、关键事件、转折点等）
2. 按时间线或章节结构组织
3. 只提取内容中明确提到的信息，不要补充
4. 输出 Markdown 格式，直接输出内容""",
}


class SummarizeMessageRequest(BaseModel):
    content: str
    item_type: str


@router.post("/projects/{project_id}/summarize-message")
async def summarize_message(project_id: str, body: SummarizeMessageRequest):
    prompt = SUMMARIZE_MSG_PROMPTS.get(body.item_type, SUMMARIZE_MSG_PROMPTS["world_setting"])
    title = ITEM_TYPE_TITLES.get(body.item_type, "设定")

    result = await chat_text(
        messages=[{"role": "user", "content": body.content}],
        system_prompt=prompt,
    )

    return {"title": title, "content": result, "item_type": body.item_type}


class SyncToWorkspaceRequest(BaseModel):
    ai_message: str
    workspace_items: list[dict]


SYNC_TO_WORKSPACE_PROMPT = """你是一位细心的小说设定管理员。用户和AI的对话中讨论了对已有设定的修改。

你的任务：
1. 阅读AI的回复内容，识别其中对已有设定做了哪些**修改、补充、覆盖**
2. 将这些变更合并到对应的已有条目中，生成更新后的完整内容
3. 如果AI回复中提到了全新的、不涉及已有条目的信息，也可以建议创建新条目

注意：
- 只修改确实有变化的部分，不要改无关内容
- 合并时保留原有结构，只替换/补充变化的部分
- 如果有矛盾（旧设定说A，新内容说B），以新内容为准

返回 JSON 格式：
{
  "updates": [
    {
      "item_id": "已有条目的id",
      "item_title": "条目标题",
      "changes_summary": "简述改了什么（一句话）",
      "updated_content": "合并后的完整内容（Markdown格式）"
    }
  ],
  "suggestions": [
    {
      "title": "新条目标题",
      "subtitle": "副标题",
      "item_type": "world_setting|character_setting|outline",
      "content": "新条目内容",
      "reason": "为什么建议创建这个新条目"
    }
  ]
}

如果没有任何需要更新的内容，返回：{"updates": [], "suggestions": []}"""


@router.post("/projects/{project_id}/sync-workspace")
async def sync_to_workspace(project_id: str, body: SyncToWorkspaceRequest):
    items_text = "\n\n".join(
        f"【条目ID: {item.get('id', '')}】【标题: {item.get('title', '')}】【副标题: {item.get('subtitle', '')}】\n{item.get('content', '')}"
        for item in body.workspace_items
    )

    user_content = f"以下是工作台已有条目：\n\n{items_text}\n\n---\n\n以下是AI的最新回复（可能包含对上述条目的修改）：\n\n{body.ai_message}"

    result = await chat_json(
        messages=[{"role": "user", "content": user_content}],
        system_prompt=SYNC_TO_WORKSPACE_PROMPT,
    )

    return result


@router.post("/projects/{project_id}/generate-item")
async def generate_workspace_item(project_id: str, body: GenerateItemRequest):
    prompt = ITEM_TYPE_PROMPTS.get(body.item_type, WORLD_SETTING_PROMPT)
    title = ITEM_TYPE_TITLES.get(body.item_type, "设定")

    conversation_text = "\n\n".join(
        f"{'用户' if m.get('role') == 'user' else 'AI'}：{m.get('content', '')}"
        for m in body.conversation_messages
    )

    result = await chat_text(
        messages=[{"role": "user", "content": f"以下是对话历史：\n\n{conversation_text}"}],
        system_prompt=prompt,
    )

    return {"title": title, "content": result, "item_type": body.item_type}


@router.put("/workspace/{item_id}")
async def update_workspace_item(item_id: str, body: WorkspaceItemUpdate):
    db = await get_db()

    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE id = ?", (item_id,),
    )
    if not cursor:
        raise HTTPException(status_code=404, detail="Item not found")

    item = dict(cursor[0])
    if item["status"] == "locked":
        raise HTTPException(status_code=400, detail="Item is locked and cannot be edited")

    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts = [f"{k} = ?" for k in fields]
    values = list(fields.values())
    set_parts.append("updated_at = datetime('now')")

    await db.execute(
        f"UPDATE workspace_items SET {', '.join(set_parts)} WHERE id = ?",
        values + [item_id],
    )
    await db.commit()

    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE id = ?", (item_id,),
    )
    return dict(cursor[0])


@router.put("/workspace/{item_id}/status")
async def update_item_status(item_id: str, body: StatusUpdate):
    db = await get_db()

    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE id = ?", (item_id,),
    )
    if not cursor:
        raise HTTPException(status_code=404, detail="Item not found")

    item = dict(cursor[0])

    await db.execute(
        "UPDATE workspace_items SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (body.status, item_id),
    )
    await db.commit()

    if item["item_type"] == "chapter" and body.status == "finalized":
        asyncio.create_task(
            _trigger_chronicle_update(item["project_id"], item["title"], item["content"])
        )

    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE id = ?", (item_id,),
    )
    return dict(cursor[0])


async def _trigger_chronicle_update(project_id: str, chapter_title: str, chapter_content: str):
    db = await get_db()
    try:
        chronicle_cursor = await db.execute_fetchall(
            "SELECT * FROM chronicle WHERE project_id = ?", (project_id,),
        )
        current_chronicle = dict(chronicle_cursor[0]) if chronicle_cursor else {}

        world_cursor = await db.execute_fetchall(
            "SELECT content FROM workspace_items WHERE project_id = ? AND item_type = 'world_setting' AND status = 'locked' LIMIT 1",
            (project_id,),
        )
        world_setting = dict(world_cursor[0])["content"] if world_cursor else ""

        chronicle_data = {}
        for key in ["timeline", "characters", "key_events", "unresolved_threads"]:
            raw = current_chronicle.get(key, "[]")
            chronicle_data[key] = json.loads(raw) if isinstance(raw, str) else raw

        result = await update_chronicle(
            chronicle_data, chapter_title, chapter_content, world_setting
        )

        await db.execute(
            """INSERT INTO chronicle (project_id, timeline, characters, key_events, unresolved_threads, raw_text, updated_at)
            VALUES (?, ?, ?, ?, ?, '', datetime('now'))
            ON CONFLICT(project_id) DO UPDATE SET
                timeline = excluded.timeline,
                characters = excluded.characters,
                key_events = excluded.key_events,
                unresolved_threads = excluded.unresolved_threads,
                raw_text = excluded.raw_text,
                updated_at = datetime('now')""",
            (
                project_id,
                json.dumps(result.get("timeline", []), ensure_ascii=False),
                json.dumps(result.get("characters", []), ensure_ascii=False),
                json.dumps(result.get("key_events", []), ensure_ascii=False),
                json.dumps(result.get("unresolved_threads", []), ensure_ascii=False),
            ),
        )
        await db.commit()
    except Exception as e:
        print(f"Chronicle update failed: {e}")


@router.delete("/workspace/{item_id}")
async def delete_workspace_item(item_id: str):
    db = await get_db()

    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE id = ?", (item_id,),
    )
    if not cursor:
        raise HTTPException(status_code=404, detail="Item not found")

    item = dict(cursor[0])
    if item["status"] == "locked":
        raise HTTPException(status_code=400, detail="Item is locked and cannot be deleted")

    await db.execute("DELETE FROM workspace_items WHERE id = ?", (item_id,))
    await db.commit()
    return {"ok": True}


class SummarizeRequest(BaseModel):
    content: str
    item_type: str = "world_setting"
    title: str = ""


SUMMARIZE_PROMPT = """你是一位专业的小说创作助手。用户会给你一段他们的想法、灵感或创意描述。请将其整理为一份结构清晰、内容完整的创作设定文档。

要求：
1. 保留用户的所有核心创意和关键信息
2. 用结构化的方式组织内容（使用标题、列表等）
3. 补充合理的细节，但不改变用户的原始意图
4. 语言精炼、适合直接作为创作参考

请直接输出整理后的内容，不要加前缀说明。"""


@router.post("/projects/{project_id}/summarize")
async def summarize_to_workspace(project_id: str, body: SummarizeRequest):
    db = await get_db()

    result = await chat_text(
        messages=[{"role": "user", "content": body.content}],
        system_prompt=SUMMARIZE_PROMPT,
    )

    title = body.title or "灵感笔记"
    item_id = str(uuid.uuid4())

    cursor = await db.execute_fetchall(
        "SELECT MAX(sort_order) as max_so FROM workspace_items WHERE project_id = ?",
        (project_id,),
    )
    max_so = cursor[0]["max_so"]
    sort_order = (max_so or 0) + 1

    await db.execute(
        """INSERT INTO workspace_items (id, project_id, item_type, status, title, subtitle, content, sort_order)
        VALUES (?, ?, ?, 'draft', ?, '', ?, ?)""",
        (item_id, project_id, body.item_type, title, result, sort_order),
    )
    await db.commit()

    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE id = ?", (item_id,),
    )
    return dict(cursor[0])
