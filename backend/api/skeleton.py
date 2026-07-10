import json
import uuid
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one
from backend.agents.guide import (
    guide_step,
    detect_skeleton_completeness,
    check_write_readiness,
    POINT_ORDER,
    POINT_LABELS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

GUIDE_CONVERSATION_TITLE = "骨架引导"

SKELETON_ITEM_TYPES = set(POINT_ORDER)


class GuideRequest(BaseModel):
    point: Literal[
        "story_core", "world_setting", "character_setting",
        "outline_reverse", "outline",
    ] | None = None
    step: Literal["intro", "extract"] = "intro"
    user_reply: str = ""
    conversation_id: str | None = None


async def _get_or_create_guide_conversation(db, project_id: str) -> str:
    row = await fetch_one(
        db,
        "SELECT id FROM conversations WHERE project_id = ? AND title = ? ORDER BY updated_at DESC LIMIT 1",
        (project_id, GUIDE_CONVERSATION_TITLE),
    )
    if row:
        return row["id"]
    conv_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO conversations (id, project_id, title) VALUES (?, ?, ?)",
        (conv_id, project_id, GUIDE_CONVERSATION_TITLE),
    )
    await db.commit()
    return conv_id


async def _load_skeleton_points(db, project_id: str) -> dict:
    rows = await fetch_all(
        db,
        """SELECT item_type, title, content, metadata FROM workspace_items
           WHERE project_id = ? AND item_type IN (?, ?, ?, ?, ?)
           ORDER BY sort_order, created_at""",
        (project_id, *SKELETON_ITEM_TYPES),
    )
    points = {}
    for r in rows:
        meta = {}
        if r.get("metadata"):
            try:
                meta = json.loads(r["metadata"])
            except (json.JSONDecodeError, TypeError):
                meta = {}
        points[r["item_type"]] = {
            "title": r.get("title") or "",
            "content": r.get("content") or "",
            "metadata": meta,
        }
    return points


async def _load_guide_history(db, conversation_id: str, limit: int = 8) -> list[dict]:
    rows = await fetch_all(
        db,
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
        (conversation_id, limit),
    )
    rows.reverse()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def _determine_current_point(points_data: dict, requested: str | None) -> str:
    if requested:
        return requested
    for pt in POINT_ORDER:
        data = points_data.get(pt)
        if not data:
            return pt
        meta = data.get("metadata", {})
        content_len = len(data.get("content", "") or "")
        if content_len < 50 or not meta:
            return pt
    return POINT_ORDER[0]


async def _upsert_skeleton_item(db, project_id: str, point: str, extracted_fields: dict):
    if not extracted_fields:
        return None
    row = await fetch_one(
        db,
        "SELECT id, metadata, content, title FROM workspace_items WHERE project_id = ? AND item_type = ?",
        (project_id, point),
    )
    if row:
        existing_meta = {}
        if row.get("metadata"):
            try:
                existing_meta = json.loads(row["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        existing_meta.update(extracted_fields)
        await db.execute(
            "UPDATE workspace_items SET metadata = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(existing_meta, ensure_ascii=False), row["id"]),
        )
        await db.commit()
        return row["id"]
    else:
        item_id = str(uuid.uuid4())
        sort_row = await fetch_one(
            db,
            "SELECT MAX(sort_order) as mx FROM workspace_items WHERE project_id = ?",
            (project_id,),
        )
        sort_order = (sort_row["mx"] or 0) + 1 if sort_row else 1
        await db.execute(
            """INSERT INTO workspace_items (id, project_id, item_type, status, title, content, metadata, sort_order)
               VALUES (?, ?, ?, 'draft', ?, ?, ?, ?)""",
            (
                item_id, project_id, point,
                POINT_LABELS.get(point, point),
                json.dumps(extracted_fields, ensure_ascii=False),
                json.dumps(extracted_fields, ensure_ascii=False),
                sort_order,
            ),
        )
        await db.commit()
        return item_id


@router.get("/projects/{project_id}/skeleton")
async def get_skeleton(project_id: str):
    db = await get_db()
    proj = await fetch_one(db, "SELECT id FROM projects WHERE id = ?", (project_id,))
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    points_data = await _load_skeleton_points(db, project_id)
    completeness = await detect_skeleton_completeness(points_data)
    return {
        "project_id": project_id,
        "points": completeness,
        "current_point": await _determine_current_point(points_data, None),
    }


@router.post("/projects/{project_id}/skeleton/guide")
async def skeleton_guide(project_id: str, body: GuideRequest):
    db = await get_db()
    proj = await fetch_one(db, "SELECT id FROM projects WHERE id = ?", (project_id,))
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    points_data = await _load_skeleton_points(db, project_id)
    current_point = await _determine_current_point(points_data, body.point)

    conversation_id = body.conversation_id or await _get_or_create_guide_conversation(db, project_id)
    history = await _load_guide_history(db, conversation_id) if body.step == "extract" else []

    if body.step == "extract" and body.user_reply:
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', ?)",
            (str(uuid.uuid4()), conversation_id, body.user_reply),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        await db.commit()

    try:
        result = await guide_step(
            current_point=current_point,
            step=body.step,
            user_reply=body.user_reply,
            existing_points=points_data,
            conversation_history=history,
        )
    except Exception as e:
        logger.error("Guide step failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Guide failed: {str(e)[:100]}")

    if result.get("extracted_fields"):
        await _upsert_skeleton_item(db, project_id, current_point, result["extracted_fields"])

    await db.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'assistant', ?)",
        (str(uuid.uuid4()), conversation_id, result.get("reply", "")),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,),
    )
    await db.commit()

    points_data_updated = await _load_skeleton_points(db, project_id)
    completeness = await detect_skeleton_completeness(points_data_updated)

    return {
        "conversation_id": conversation_id,
        "current_point": current_point,
        "reply": result.get("reply", ""),
        "extracted_fields": result.get("extracted_fields", {}),
        "is_point_complete": result.get("is_complete", False),
        "next_point": await _determine_current_point(points_data_updated, None) if result.get("is_complete") else current_point,
        "completeness": completeness["_summary"],
    }


@router.get("/projects/{project_id}/skeleton/check-write")
async def check_write(project_id: str):
    db = await get_db()
    proj = await fetch_one(db, "SELECT id FROM projects WHERE id = ?", (project_id,))
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    points_data = await _load_skeleton_points(db, project_id)
    readiness = await check_write_readiness(points_data)
    return readiness
