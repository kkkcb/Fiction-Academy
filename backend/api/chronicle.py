import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one
from backend.agents.chronicle import update_chronicle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


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
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                d[key] = []
        else:
            d[key] = []
    return d


@router.get("/projects/{project_id}/chronicle")
async def get_chronicle(project_id: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT * FROM chronicle WHERE project_id = ?", (project_id,))
    if not row:
        return _empty_chronicle()
    return _row_to_dict(row)


@router.put("/projects/{project_id}/chronicle")
async def put_chronicle(project_id: str, body: ChronicleUpdate):
    db = await get_db()
    existing = await fetch_one(db, "SELECT * FROM chronicle WHERE project_id = ?", (project_id,))

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
        set_parts = []
        values = []
        if body.timeline is not None:
            set_parts.append("timeline = ?")
            values.append(json.dumps(body.timeline, ensure_ascii=False))
        if body.characters is not None:
            set_parts.append("characters = ?")
            values.append(json.dumps(body.characters, ensure_ascii=False))
        if body.key_events is not None:
            set_parts.append("key_events = ?")
            values.append(json.dumps(body.key_events, ensure_ascii=False))
        if body.unresolved_threads is not None:
            set_parts.append("unresolved_threads = ?")
            values.append(json.dumps(body.unresolved_threads, ensure_ascii=False))
        if body.raw_text is not None:
            set_parts.append("raw_text = ?")
            values.append(body.raw_text)
        set_parts.append("updated_at = datetime('now')")
        values.append(project_id)
        await db.execute(
            f"UPDATE chronicle SET {', '.join(set_parts)} WHERE project_id = ?",
            values,
        )

    await db.commit()
    return await get_chronicle(project_id)


@router.post("/projects/{project_id}/chronicle/refresh")
async def refresh_chronicle(project_id: str):
    db = await get_db()

    project = await fetch_one(db, "SELECT id FROM projects WHERE id = ?", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    world_rows = await fetch_all(
        db,
        "SELECT content FROM workspace_items WHERE project_id = ? AND item_type = 'world_setting' AND status IN ('locked', 'finalized')",
        (project_id,),
    )
    world_setting = "\n".join(r["content"] for r in world_rows[:3]) if world_rows else ""

    chapters = await fetch_all(
        db,
        "SELECT title, content, chapter_number FROM workspace_items WHERE project_id = ? AND item_type = 'chapter' AND status IN ('finalized', 'locked') ORDER BY chapter_number ASC",
        (project_id,),
    )

    chronicle_row = await fetch_one(db, "SELECT * FROM chronicle WHERE project_id = ?", (project_id,))
    if chronicle_row:
        current = _row_to_dict(chronicle_row)
    else:
        current = _empty_chronicle()

    last_processed = 0
    for chapter in chapters:
        try:
            current = await update_chronicle(
                current_chronicle=current,
                chapter_title=chapter["title"] or f"第{chapter['chapter_number']}章",
                chapter_content=chapter["content"],
                world_setting=world_setting,
            )
            last_processed += 1
        except Exception as e:
            logger.error("Chronicle update failed at chapter '%s': %s", chapter.get("title"), e, exc_info=True)
            break

    if not current.get("raw_text"):
        raw_parts = []
        for tl in current.get("timeline", []):
            if isinstance(tl, dict):
                raw_parts.append(f"[{tl.get('time', '')}] {tl.get('event', '')}")
            else:
                raw_parts.append(str(tl))
        current["raw_text"] = "\n".join(raw_parts)

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

    return {**current, "processed_chapters": last_processed, "total_chapters": len(chapters)}
