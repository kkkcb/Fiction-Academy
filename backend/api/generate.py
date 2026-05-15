import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from database import get_db
from agents.loader import load_character
from workflow.graph import chapter_graph

router = APIRouter()

async def _load_project_chars(project: dict) -> dict:
    char_map = {}
    for role, key in [
        ("writer", "writer_id"),
        ("peer", "peer_id"),
        ("operator", "operator_id"),
        ("content_reviewer", "content_reviewer_id"),
        ("compliance_reviewer", "compliance_reviewer_id"),
    ]:
        cid = project.get(key)
        if cid:
            db = await get_db()
            cursor = await db.execute_fetchall("SELECT * FROM characters WHERE id = ?", (cid,))
            if cursor:
                row = dict(cursor[0])
                char_map[f"{role}_char"] = load_character_file(row["file_path"])
    return char_map

from agents.loader import load_character_file

async def generate_chapter(project_id: str, chapter_number: int) -> AsyncGenerator[dict, None]:
    db = await get_db()
    cursor = await db.execute_fetchall("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not cursor:
        yield {"type": "error", "message": "Project not found"}
        return
    project = dict(cursor[0])

    try:
        char_map = {}
        for role, key in [
            ("writer", "writer_id"),
            ("peer", "peer_id"),
            ("operator", "operator_id"),
            ("content_reviewer", "content_reviewer_id"),
            ("compliance_reviewer", "compliance_reviewer_id"),
        ]:
            cid = project.get(key)
            if cid:
                cur = await db.execute_fetchall("SELECT * FROM characters WHERE id = ?", (cid,))
                if cur:
                    char_map[f"{role}_char"] = load_character_file(dict(cur[0])["file_path"])

        if "writer_char" not in char_map:
            yield {"type": "error", "message": "Project has no writer assigned"}
            return

        prev = await db.execute_fetchall(
            "SELECT chapter_number, summary FROM chapters WHERE project_id = ? ORDER BY chapter_number DESC LIMIT 5",
            (project_id,),
        )
        prev_summaries = "\n".join(
            f"第{r['chapter_number']}章: {r['summary'] or '(无摘要)'}"
            for r in reversed(prev)
        ) if prev else "这是第一章，无前情提要"

        reader_cid = project.get("reader_ids")
        if reader_cid:
            cur = await db.execute_fetchall("SELECT * FROM characters WHERE id = ?", (reader_cid,))
            if cur:
                char_map["reader_char"] = load_character_file(dict(cur[0])["file_path"])

        state = {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "chapter_outline": project.get("outline", ""),
            "world_setting": project.get("world_setting", ""),
            "character_setting": project.get("character_setting", ""),
            "prev_summaries": prev_summaries,
            "revision_count": 0,
            "max_revisions": 2,
            "events": [],
            **char_map,
        }

        config = {"configurable": {"thread_id": f"{project_id}_ch{chapter_number}"}}

        async for event in chapter_graph.astream(state, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if "events" in node_output:
                    for e in node_output["events"]:
                        yield e

                if "decision" in node_output:
                    decision = node_output["decision"]
                    if decision in ("pass", "force_pass"):
                        cid = str(uuid.uuid4())
                        final = node_output.get("final_content", state.get("chapter_content", ""))
                        await db.execute(
                            """INSERT OR REPLACE INTO chapters
                            (id, project_id, chapter_number, content, peer_feedback, operator_feedback,
                             content_review, compliance_review, reader_feedback,
                             revision_notes, revision_count, decision, final_content)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (cid, project_id, chapter_number,
                             json.dumps(state.get("chapter_content", ""), ensure_ascii=False),
                             json.dumps(state.get("peer_feedback"), ensure_ascii=False),
                             json.dumps(state.get("operator_feedback"), ensure_ascii=False),
                             json.dumps(state.get("content_result"), ensure_ascii=False),
                             json.dumps(state.get("compliance_result"), ensure_ascii=False),
                             json.dumps(state.get("reader_result"), ensure_ascii=False),
                             state.get("revision_notes", ""),
                             state.get("revision_count", 0),
                             decision,
                             final),
                        )
                        await db.commit()
                        yield {"type": "chapter_saved", "chapter": chapter_number, "decision": decision}

                if "revision_count" in node_output:
                    new_count = node_output["revision_count"]
                    if new_count > state["revision_count"]:
                        yield {"type": "revision", "count": new_count, "notes": state.get("revision_notes", "")}

    except Exception as e:
        yield {"type": "error", "message": str(e)}

@router.get("/{project_id}/generate/{chapter_number}/stream")
async def stream_generate(project_id: str, chapter_number: int):
    return EventSourceResponse(
        generate_chapter(project_id, chapter_number),
        media_type="text/event-stream",
    )
