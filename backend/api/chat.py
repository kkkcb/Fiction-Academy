import uuid
import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one
from backend.agents.base import chat_stream
from backend.config import CHAT_HISTORY_LIMIT, SYSTEM_PROMPT
from backend.services.wiki import (
    detect_scene,
    parse_wiki_pages,
    query_wiki,
    apply_token_budget,
    assemble_context,
    estimate_tokens,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    content: str = ""
    assistant_id: str | None = None
    regenerate: bool = False


async def _build_context_system_prompt(db, project_id: str, user_content: str = "") -> str:
    scene = detect_scene(user_content)
    logger.info("[context] project=%s scene=%s", project_id, scene)

    ws_rows = await fetch_all(
        db,
        """SELECT item_type, title, content, metadata FROM workspace_items
           WHERE project_id = ? AND item_type IN (
               'story_core', 'world_setting', 'character_setting',
               'outline', 'outline_reverse', 'foreshadow'
           ) AND status IN ('locked', 'finalized')
           ORDER BY sort_order, created_at""",
        (project_id,),
    )
    chapter_rows = []
    chapter_plan_row = None
    if scene in ("write_chapter", "edit_chapter"):
        chapter_rows = await fetch_all(
            db,
            "SELECT item_type, title, content, chapter_number FROM workspace_items WHERE project_id = ? AND item_type = 'chapter' AND status IN ('finalized', 'locked') ORDER BY chapter_number DESC LIMIT 3",
            (project_id,),
        )
        chapter_plan_row = await fetch_one(
            db,
            """SELECT content, metadata, chapter_number FROM workspace_items
               WHERE project_id = ? AND item_type = 'chapter_plan'
                     AND status IN ('finalized', 'locked')
               ORDER BY chapter_number DESC LIMIT 1""",
            (project_id,),
        )

    all_core_pages = []
    for r in ws_rows:
        pages = parse_wiki_pages(r["content"], r["item_type"], r["title"] or "")
        all_core_pages.extend(pages)

    chapter_pages = []
    for r in chapter_rows:
        title = r["title"] or f"第{r.get('chapter_number', '?')}章"
        content = r["content"] or ""
        if len(content) > 3000:
            content = content[:3000] + "\n...(后续内容省略)"
        chapter_pages.append({
            "type": "chapter",
            "title": title,
            "content": f"### {title}\n{content}",
            "keywords": set(),
            "score": 0,
        })

    chronicle_row = await fetch_one(
        db,
        "SELECT raw_text, timeline, key_events, unresolved_threads FROM chronicle WHERE project_id = ?",
        (project_id,),
    )
    chronicle_text = ""
    if chronicle_row:
        chronicle_text = chronicle_row.get("raw_text", "")
        if not chronicle_text:
            try:
                tl = json.loads(chronicle_row.get("timeline", "[]"))
                ce = json.loads(chronicle_row.get("key_events", "[]"))
                ur = json.loads(chronicle_row.get("unresolved_threads", "[]"))
                lines = []
                for x in tl[:20]:
                    if isinstance(x, dict):
                        lines.append(f"- [{x.get('time', '')}] {x.get('event', '')}")
                for x in ce[:10]:
                    lines.append(f"- 关键事件: {x}" if not isinstance(x, dict) else f"- 关键事件: {x.get('event', x.get('title', ''))}")
                if ur:
                    lines.append("- 未回收伏笔:")
                    for x in ur[:10]:
                        lines.append(f"  · {x}" if not isinstance(x, dict) else f"  · {x.get('content', x.get('hint', ''))}")
                chronicle_text = "\n".join(lines)
            except Exception:
                chronicle_text = ""

    layer1 = query_wiki(all_core_pages, user_content, scene, max_pages=10)
    layer2 = chapter_pages
    layer3: list[dict] = []

    layer1, layer2, layer3 = apply_token_budget(layer1, layer2, layer3)

    chapter_plan_prefix = ""
    if chapter_plan_row:
        plan_meta = {}
        if chapter_plan_row.get("metadata"):
            try:
                plan_meta = json.loads(chapter_plan_row["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        plan_num = chapter_plan_row.get("chapter_number", "?")
        chapter_plan_prefix = (
            f"\n\n<chapter_plan priority=\"critical\">\n"
            f"你正在写【第{plan_num}章】，必须严格遵循以下章纲：\n"
            f"{chapter_plan_row['content']}\n"
            f"</chapter_plan>\n"
            f"注意：核心冲突、爽点设计、断章钩子必须按章纲执行，不要即兴偏离。\n"
        )

    context_body = assemble_context(layer1, layer2, layer3, chronicle_text)
    context_body = chapter_plan_prefix + context_body

    total_tokens = estimate_tokens(context_body)
    logger.info(
        "[context] core=%d chapters=%d chronicle=%d tokens≈%d",
        len(layer1), len(layer2), bool(chronicle_text), total_tokens,
    )

    if context_body:
        return SYSTEM_PROMPT + "\n\n" + context_body
    return SYSTEM_PROMPT


async def _get_assistant_prompt(db, assistant_id: str | None) -> tuple[str, str]:
    if not assistant_id:
        return "", ""
    row = await fetch_one(db, "SELECT system_prompt, model FROM assistants WHERE id = ?", (assistant_id,))
    if row:
        return row["system_prompt"] or "", row["model"] or ""
    return "", ""


@router.get("/projects/{project_id}/conversations")
async def list_conversations(project_id: str):
    db = await get_db()
    rows = await fetch_all(
        db,
        "SELECT * FROM conversations WHERE project_id = ? ORDER BY updated_at DESC",
        (project_id,),
    )
    return rows


@router.post("/projects/{project_id}/conversations")
async def create_conversation(project_id: str, title: str = "新对话"):
    db = await get_db()
    cid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO conversations (id, project_id, title) VALUES (?, ?, ?)",
        (cid, project_id, title),
    )
    await db.execute(
        "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
        (project_id,),
    )
    await db.commit()
    return {"id": cid, "project_id": project_id, "title": title}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    db = await get_db()
    rows = await fetch_all(
        db,
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    )
    return rows


@router.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, title: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT project_id FROM conversations WHERE id = ?", (conversation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.execute(
        "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
        (title, conversation_id),
    )
    await db.execute(
        "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
        (row["project_id"],),
    )
    await db.commit()
    return {"id": conversation_id, "title": title}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT project_id FROM conversations WHERE id = ?", (conversation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    await db.execute(
        "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
        (row["project_id"],),
    )
    await db.commit()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/chat/stream")
async def stream_chat(conversation_id: str, body: ChatRequest):
    db = await get_db()
    conv = await fetch_one(db, "SELECT * FROM conversations WHERE id = ?", (conversation_id,))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return StreamingResponse(
        _chat_stream_generator(
            conversation_id,
            conv["project_id"],
            body.content,
            body.assistant_id or "",
            body.regenerate,
        ),
        media_type="application/x-ndjson",
    )


async def _chat_stream_generator(
    conversation_id: str,
    project_id: str,
    user_content: str,
    assistant_id: str,
    regenerate: bool,
):
    db = await get_db()

    if regenerate:
        last_assistant = await fetch_one(
            db,
            "SELECT id FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        )
        if last_assistant:
            await db.execute("DELETE FROM messages WHERE id = ?", (last_assistant["id"],))
            await db.commit()
        last_user = await fetch_one(
            db,
            "SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        )
        user_content = last_user["content"] if last_user else ""
    else:
        if not user_content.strip():
            yield json.dumps({"error": "消息不能为空"}, ensure_ascii=False) + "\n"
            return
        user_msg_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', ?)",
            (user_msg_id, conversation_id, user_content),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        await db.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        await db.commit()

    history = await fetch_all(
        db,
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    )
    recent_history = history[-CHAT_HISTORY_LIMIT:]
    while recent_history and recent_history[0]["role"] == "assistant":
        recent_history = recent_history[1:]

    system_prompt_override, assistant_model = await _get_assistant_prompt(db, assistant_id)
    fixed_context = await _build_context_system_prompt(db, project_id, user_content)

    if system_prompt_override:
        final_system_prompt = system_prompt_override + "\n\n" + fixed_context
    else:
        final_system_prompt = fixed_context

    messages = recent_history + [{"role": "user", "content": user_content}]

    logger.info("[stream] conversation=%s, assistant=%s, history=%d", conversation_id, assistant_id or "default", len(recent_history))

    full_reply = ""
    try:
        async for chunk in chat_stream(messages, system_prompt=final_system_prompt, model=assistant_model):
            full_reply += chunk
            yield json.dumps({"content": chunk}, ensure_ascii=False) + "\n"
    except Exception as e:
        logger.error("[stream] LLM error for conversation=%s: %s", conversation_id, e, exc_info=True)
        if full_reply:
            assistant_msg_id = str(uuid.uuid4())
            db2 = await get_db()
            await db2.execute(
                "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'assistant', ?)",
                (assistant_msg_id, conversation_id, full_reply + f"\n\n[生成中断: {e}]"),
            )
            await db2.commit()
        yield json.dumps({"error": f"生成失败: {e}"}, ensure_ascii=False) + "\n"
        return

    if full_reply.strip():
        assistant_msg_id = str(uuid.uuid4())
        db3 = await get_db()
        await db3.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'assistant', ?)",
            (assistant_msg_id, conversation_id, full_reply),
        )
        await db3.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        await db3.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        await db3.commit()

    yield json.dumps({"done": True}, ensure_ascii=False) + "\n"
