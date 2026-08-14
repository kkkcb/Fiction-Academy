import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one, transaction
from backend.agents.base import chat_json, LLMError
from backend.agents.guide_prompts import POINT_CONFIGS
from backend.agents.guide import POINT_ORDER, POINT_LABELS
from backend.agents.expert_panel import run_expert_panel
from backend.services import repo
from backend.services.rules import get_rules_injection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _validate_point(point: str) -> None:
    if point not in POINT_CONFIGS or point not in POINT_ORDER:
        raise HTTPException(status_code=400, detail=f"Invalid point: {point}")


class SummarizeBody(BaseModel):
    conversation_id: str


SUMMARIZE_POINT_SYSTEM_PROMPT = """你是一位资深网文策划。请根据作者与策划的对话内容，提炼出该点位的结构化设定总结。
要求：
1. summary 是一段 200-500 字的连贯设定描述，可直接作为设定文档使用
2. fields 是结构化字段键值对，只填写对话中已明确的内容，不编造"""


@router.get("/projects/{project_id}/points")
async def list_points(project_id: str):
    db = await get_db()

    conv_rows = await fetch_all(
        db,
        """SELECT c.point, c.id AS conversation_id, COUNT(m.id) AS message_count
           FROM conversations c
           LEFT JOIN messages m ON m.conversation_id = c.id
           WHERE c.project_id = ? AND c.point IS NOT NULL
           GROUP BY c.id
           ORDER BY c.updated_at DESC""",
        (project_id,),
    )
    point_conv: dict = {}
    for r in conv_rows:
        if r["point"] not in point_conv:
            point_conv[r["point"]] = r

    placeholders = ",".join("?" for _ in POINT_ORDER)
    archive_rows = await fetch_all(
        db,
        f"SELECT item_type FROM workspace_items WHERE project_id = ? AND item_type IN ({placeholders}) AND status IN ('finalized', 'locked')",
        (project_id, *POINT_ORDER),
    )
    archived_points = {r["item_type"] for r in archive_rows}

    points = []
    for pt in POINT_ORDER:
        conv = point_conv.get(pt)
        conv_id = conv["conversation_id"] if conv else None
        message_count = conv["message_count"] if conv else 0
        has_archive = pt in archived_points
        if has_archive:
            status = "done"
        elif conv_id:
            status = "active"
        else:
            status = "pending"
        points.append({
            "point": pt,
            "label": POINT_LABELS.get(pt, pt),
            "status": status,
            "conversation_id": conv_id,
            "message_count": message_count,
            "has_archive": has_archive,
        })

    current_point = POINT_ORDER[-1]
    for p in points:
        if p["status"] != "done":
            current_point = p["point"]
            break

    return {"points": points, "current_point": current_point}


@router.post("/projects/{project_id}/points/{point}/ensure-conversation")
async def ensure_conversation(project_id: str, point: str):
    _validate_point(point)

    db = await get_db()

    conv = await fetch_one(
        db,
        "SELECT id FROM conversations WHERE project_id = ? AND point = ? ORDER BY updated_at DESC LIMIT 1",
        (project_id, point),
    )
    if conv:
        conversation_id = conv["id"]
    else:
        conversation_id = str(uuid.uuid4())
        async with transaction():
            await db.execute(
                "INSERT INTO conversations (id, project_id, title, point) VALUES (?, ?, ?, ?)",
                (conversation_id, project_id, POINT_LABELS.get(point, point), point),
            )

    count_row = await fetch_one(
        db,
        "SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    )
    msg_count = count_row["cnt"] if count_row else 0

    if msg_count == 0:
        intro = POINT_CONFIGS[point].get("intro", "")
        if intro:
            async with transaction():
                await repo.save_message(db, conversation_id, "assistant", intro)
                await db.execute(
                    "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                    (conversation_id,),
                )

    messages = await fetch_all(
        db,
        "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC",
        (conversation_id,),
    )

    return {
        "conversation_id": conversation_id,
        "point": point,
        "messages": messages,
    }


async def _load_prior_background(db, project_id: str, point: str) -> str:
    """读取已归档的前序设定作为背景（点位顺序按 POINT_ORDER）。"""
    point_index = POINT_ORDER.index(point)
    prior_points = POINT_ORDER[:point_index]
    if not prior_points:
        return "（无）"
    rows = await repo.load_finalized_items(db, project_id, prior_points)
    return repo.format_items_as_background(rows, POINT_LABELS)


async def _load_conversation_messages(db, project_id: str, conversation_id: str) -> list[dict]:
    """加载对话消息，并校验对话属于该项目。"""
    owner = await repo.conversation_project_id(db, conversation_id)
    if owner != project_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return await fetch_all(
        db,
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC",
        (conversation_id,),
    )


@router.post("/projects/{project_id}/points/{point}/summarize")
async def summarize_point(project_id: str, point: str, body: SummarizeBody):
    _validate_point(point)

    db = await get_db()
    messages = await _load_conversation_messages(db, project_id, body.conversation_id)
    if not messages:
        raise HTTPException(status_code=400, detail="对话中没有消息可总结")

    background_text = await _load_prior_background(db, project_id, point)

    config = POINT_CONFIGS[point]
    label = POINT_LABELS.get(point, point)
    intro = config.get("intro", "")
    fields_hint = json.dumps(config.get("fields", {}), ensure_ascii=False, indent=2)

    conversation_text = "\n".join(
        f"{'作者' if m['role'] == 'user' else '策划'}：{m['content']}"
        for m in messages
    )

    prompt = f"""请将以下【{label}】点位的对话整理为一段连贯的设定描述，并提取结构化字段。

## 已确定的背景
{background_text}

## 该点位说明
{intro}

## 需要提取的字段
{fields_hint}

## 对话内容
{conversation_text}

请输出 JSON：
{{
  "summary": "一段200-500字的连贯设定描述",
  "fields": {{ "字段名": "字段值" }}
}}"""

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SUMMARIZE_POINT_SYSTEM_PROMPT,
            temperature=0.4,
        )
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"AI 总结失败：{str(e)[:150]}")

    summary = result.get("summary", "")
    fields_data = result.get("fields", {})
    if not isinstance(fields_data, dict):
        fields_data = {}

    item_id = await repo.upsert_workspace_item(
        db, project_id, point,
        title=POINT_LABELS.get(point, point),
        content=summary, metadata=fields_data, status="finalized",
    )

    new_name = await repo.maybe_apply_book_name(db, project_id, fields_data)
    if new_name:
        logger.info("[summarize] project=%s auto-named to %r", project_id, new_name)

    return {
        "point": point,
        "content": summary,
        "metadata": fields_data,
        "item_id": item_id,
        "project_name": new_name,
    }


class ExpertConsultBody(BaseModel):
    idea: str
    conversation_id: str | None = ""


@router.post("/projects/{project_id}/points/{point}/expert-consult")
async def expert_consult(project_id: str, point: str, body: ExpertConsultBody):
    """专家圆桌会诊：五位专家多轮讨论 + 主编汇总，流式返回，最终保存。"""
    _validate_point(point)
    if not body.idea.strip():
        raise HTTPException(status_code=400, detail="想法不能为空")

    db = await get_db()
    background = await _load_prior_background(db, project_id, point)
    rules_inject = await get_rules_injection(project_id)
    if rules_inject:
        background = rules_inject + background
    config = POINT_CONFIGS[point]
    label = POINT_LABELS.get(point, point)
    intro = config.get("intro", "")

    conversation_id = ""
    if body.conversation_id:
        owner = await repo.conversation_project_id(db, body.conversation_id)
        if owner == project_id:
            conversation_id = body.conversation_id

    async def _generator():
        summary_content = ""
        record_obj = None
        try:
            if conversation_id:
                async with transaction():
                    await repo.save_message(db, conversation_id, "user", f"/consult {body.idea}")
                    await db.execute(
                        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                        (conversation_id,),
                    )
                    await repo.touch_project(db, project_id)

            async for event in run_expert_panel(body.idea, background, intro, label, rounds=2):
                if event["phase"] == "summary":
                    summary_content = event["content"]
                elif event["phase"] == "record":
                    record_obj = event["record"]
                yield json.dumps(event, ensure_ascii=False) + "\n"

            assistant_text = json.dumps(record_obj, ensure_ascii=False) if record_obj else summary_content
            if conversation_id and assistant_text.strip():
                async with transaction():
                    await repo.save_message(db, conversation_id, "assistant", assistant_text)
                    await db.execute(
                        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                        (conversation_id,),
                    )

            if summary_content.strip():
                item_id = await repo.upsert_workspace_item(
                    db, project_id, point,
                    title=f"{label}（专家会诊）",
                    content=summary_content, status="draft",
                )
                yield json.dumps({"phase": "saved", "item_id": item_id, "point": point}, ensure_ascii=False) + "\n"

        except Exception as e:
            logger.error("[expert-consult] failed: %s", e, exc_info=True)
            yield json.dumps({"phase": "error", "message": str(e)}, ensure_ascii=False) + "\n"

    return StreamingResponse(_generator(), media_type="application/x-ndjson")


AUTO_GENERATE_SYSTEM_PROMPT = """你是一位资深网文策划，擅长根据一个模糊的创意想法，快速构建出完整的网文设定。
要求：
1. summary 是一段 300-600 字的连贯设定描述，要有网文味、有爽点、可直接作为设定文档
2. fields 是结构化字段键值对，内容要具体、有画面感、有冲突张力
3. 充分利用作者的原始想法，同时大胆补全细节，让设定丰满有趣
4. 如果有已确定的前序设定，必须保持一致和连贯"""


class AutoGenerateBody(BaseModel):
    idea: str
    conversation_id: str | None = ""


@router.post("/projects/{project_id}/points/{point}/auto-generate")
async def auto_generate_point(project_id: str, point: str, body: AutoGenerateBody):
    _validate_point(point)

    db = await get_db()

    conversation_id = ""
    if body.conversation_id:
        owner = await repo.conversation_project_id(db, body.conversation_id)
        if owner == project_id:
            conversation_id = body.conversation_id

    background_text = await _load_prior_background(db, project_id, point)

    rules_inject = await get_rules_injection(project_id)
    rules_section = rules_inject if rules_inject else ""

    config = POINT_CONFIGS[point]
    label = POINT_LABELS.get(point, point)
    intro = config.get("intro", "")
    fields_hint = json.dumps(config.get("fields", {}), ensure_ascii=False, indent=2)

    prompt = f"""作者想创作一部网文，现在需要确定【{label}】。
{rules_section}
## 作者的原始想法
{body.idea}

## 已确定的前序设定（必须保持一致）
{background_text}

## 该点位说明
{intro}

## 需要生成的字段
{fields_hint}

请基于作者的想法和已确定的前序设定，直接生成完整的【{label}】设定。
大胆创作，让内容有网文味、有冲突、有爽点。

请输出 JSON：
{{
  "summary": "一段300-600字的连贯设定描述",
  "fields": {{ "字段名": "字段值" }}
}}"""

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=AUTO_GENERATE_SYSTEM_PROMPT,
            temperature=0.8,
        )
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{str(e)[:150]}")

    summary = result.get("summary", "")
    fields_data = result.get("fields", {})
    if not isinstance(fields_data, dict):
        fields_data = {}

    item_id = await repo.upsert_workspace_item(
        db, project_id, point,
        title=POINT_LABELS.get(point, point),
        content=summary, metadata=fields_data, status="finalized",
    )

    new_name = await repo.maybe_apply_book_name(db, project_id, fields_data)
    if new_name:
        logger.info("[auto-generate] project=%s auto-named to %r", project_id, new_name)

    if conversation_id:
        async with transaction():
            await repo.save_message(db, conversation_id, "user", f"/gen {body.idea}")
            fields_lines = [f"- **{k}**: {v}" for k, v in fields_data.items() if v]
            fields_block = "\n\n**结构化字段：**\n" + "\n".join(fields_lines) if fields_lines else ""
            await repo.save_message(db, conversation_id, "assistant", summary + fields_block)
            await db.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )

    logger.info("[auto-generate] project=%s point=%s idea=%s", project_id, point, body.idea[:50])

    return {
        "point": point,
        "content": summary,
        "metadata": fields_data,
        "item_id": item_id,
        "project_name": new_name,
    }
