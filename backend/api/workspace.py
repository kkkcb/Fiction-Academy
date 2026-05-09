import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db
from backend.agents.chronicle import update_chronicle

router = APIRouter()


class WorkspaceItemCreate(BaseModel):
    item_type: str
    title: str
    content: str = ""
    chapter_number: Optional[int] = None


class WorkspaceItemUpdate(BaseModel):
    title: Optional[str] = None
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
        """INSERT INTO workspace_items (id, project_id, item_type, status, title, content, chapter_number, sort_order)
        VALUES (?, ?, ?, 'draft', ?, ?, ?, ?)""",
        (item_id, project_id, body.item_type, body.title, body.content, chapter_number, sort_order),
    )
    await db.commit()

    cursor = await db.execute_fetchall(
        "SELECT * FROM workspace_items WHERE id = ?", (item_id,),
    )
    return dict(cursor[0])


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

    if item["item_type"] == "world_setting" and body.status != "locked":
        raise HTTPException(status_code=400, detail="world_setting can only be locked")

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
