import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db
from backend.agents.chronicle import update_chronicle

router = APIRouter()


class ChronicleUpdate(BaseModel):
    timeline: Optional[list] = None
    characters: Optional[list] = None
    key_events: Optional[list] = None
    unresolved_threads: Optional[list] = None
    raw_text: Optional[str] = None


def _empty_chronicle():
    return {
        "timeline": [],
        "characters": [],
        "key_events": [],
        "unresolved_threads": [],
        "raw_text": "",
    }


def _row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    for key in ("timeline", "characters", "key_events", "unresolved_threads"):
        if d.get(key):
            d[key] = json.loads(d[key])
        else:
            d[key] = []
    return d


@router.get("/{project_id}/chronicle")
async def get_chronicle(project_id: str):
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT * FROM chronicle WHERE project_id = ?", (project_id,)
    )
    if not cursor:
        return _empty_chronicle()
    return _row_to_dict(cursor[0])


@router.put("/{project_id}/chronicle")
async def put_chronicle(project_id: str, body: ChronicleUpdate):
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT * FROM chronicle WHERE project_id = ?", (project_id,)
    )
    existing = cursor[0] if cursor else None

    if existing is None:
        timeline = json.dumps(body.timeline, ensure_ascii=False) if body.timeline is not None else "[]"
        characters = json.dumps(body.characters, ensure_ascii=False) if body.characters is not None else "[]"
        key_events = json.dumps(body.key_events, ensure_ascii=False) if body.key_events is not None else "[]"
        unresolved_threads = json.dumps(body.unresolved_threads, ensure_ascii=False) if body.unresolved_threads is not None else "[]"
        raw_text = body.raw_text if body.raw_text is not None else ""
        await db.execute(
            """INSERT INTO chronicle (project_id, timeline, characters, key_events, unresolved_threads, raw_text, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (project_id, timeline, characters, key_events, unresolved_threads, raw_text),
        )
    else:
        fields = {}
        if body.timeline is not None:
            fields["timeline"] = json.dumps(body.timeline, ensure_ascii=False)
        if body.characters is not None:
            fields["characters"] = json.dumps(body.characters, ensure_ascii=False)
        if body.key_events is not None:
            fields["key_events"] = json.dumps(body.key_events, ensure_ascii=False)
        if body.unresolved_threads is not None:
            fields["unresolved_threads"] = json.dumps(body.unresolved_threads, ensure_ascii=False)
        if body.raw_text is not None:
            fields["raw_text"] = body.raw_text
        fields["updated_at"] = "datetime('now')"
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [project_id]
        await db.execute(
            f"UPDATE chronicle SET {set_clause} WHERE project_id = ?", values
        )

    await db.commit()
    return await get_chronicle(project_id)


@router.post("/{project_id}/chronicle/refresh")
async def refresh_chronicle(project_id: str):
    db = await get_db()

    project_cursor = await db.execute_fetchall(
        "SELECT id FROM projects WHERE id = ?", (project_id,)
    )
    if not project_cursor:
        raise HTTPException(status_code=404, detail="Project not found")

    world_cursor = await db.execute_fetchall(
        "SELECT content FROM workspace_items WHERE project_id = ? AND item_type = 'world_setting' AND status = 'locked'",
        (project_id,),
    )
    world_setting = "\n".join(dict(row)["content"] for row in world_cursor) if world_cursor else ""

    chapters_cursor = await db.execute_fetchall(
        "SELECT title, content, chapter_number FROM workspace_items WHERE project_id = ? AND item_type = 'chapter' AND status = 'finalized' ORDER BY chapter_number ASC",
        (project_id,),
    )
    chapters = [dict(row) for row in chapters_cursor]

    chronicle_cursor = await db.execute_fetchall(
        "SELECT * FROM chronicle WHERE project_id = ?", (project_id,)
    )
    if chronicle_cursor:
        current = _row_to_dict(chronicle_cursor[0])
    else:
        current = _empty_chronicle()

    for chapter in chapters:
        current = await update_chronicle(
            current_chronicle=current,
            chapter_title=chapter["title"] or f"第{chapter['chapter_number']}章",
            chapter_content=chapter["content"],
            world_setting=world_setting,
        )

    timeline = json.dumps(current.get("timeline", []), ensure_ascii=False)
    characters = json.dumps(current.get("characters", []), ensure_ascii=False)
    key_events = json.dumps(current.get("key_events", []), ensure_ascii=False)
    unresolved_threads = json.dumps(current.get("unresolved_threads", []), ensure_ascii=False)
    raw_text = current.get("raw_text", "")

    await db.execute(
        """INSERT INTO chronicle (project_id, timeline, characters, key_events, unresolved_threads, raw_text, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(project_id) DO UPDATE SET
            timeline = excluded.timeline,
            characters = excluded.characters,
            key_events = excluded.key_events,
            unresolved_threads = excluded.unresolved_threads,
            raw_text = excluded.raw_text,
            updated_at = excluded.updated_at""",
        (project_id, timeline, characters, key_events, unresolved_threads, raw_text),
    )
    await db.commit()

    return current
