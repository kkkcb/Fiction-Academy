import json
import uuid
import time
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.database import get_db
from backend.agents.base import chat_stream, SYSTEM_PROMPT

router = APIRouter()
logger = logging.getLogger("chat")

class ConversationCreate(BaseModel):
    title: str

class ConversationRename(BaseModel):
    title: str

class ChatRequest(BaseModel):
    content: str
    assistant_id: str = ""
    regenerate: bool = False

@router.get("/projects/{project_id}/conversations")
async def list_conversations(project_id: str):
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT * FROM conversations WHERE project_id = ? ORDER BY updated_at DESC",
        (project_id,),
    )
    return [dict(row) for row in cursor]

@router.post("/projects/{project_id}/conversations")
async def create_conversation(project_id: str, body: ConversationCreate):
    db = await get_db()
    cid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO conversations (id, project_id, title) VALUES (?, ?, ?)",
        (cid, project_id, body.title),
    )
    await db.commit()
    cursor = await db.execute_fetchall(
        "SELECT * FROM conversations WHERE id = ?", (cid,)
    )
    return dict(cursor[0])

@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    )
    return [dict(row) for row in cursor]

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    db = await get_db()
    await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    cursor = await db.execute(
        "DELETE FROM conversations WHERE id = ?", (conversation_id,)
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.commit()
    return {"ok": True}

@router.put("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: str, body: ConversationRename):
    db = await get_db()
    cursor = await db.execute(
        "UPDATE conversations SET title = ? WHERE id = ?", (body.title, conversation_id)
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.commit()
    return {"ok": True}

async def _chat_stream_generator(conversation_id: str, user_content: str, assistant_id: str = "", regenerate: bool = False):
    db = await get_db()

    if regenerate:
        last_msgs = await db.execute_fetchall(
            "SELECT id FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 2",
            (conversation_id,),
        )
        for m in last_msgs:
            await db.execute("DELETE FROM messages WHERE id = ?", (m["id"],))
        await db.commit()

    cursor = await db.execute_fetchall(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
    )
    if not cursor:
        yield json.dumps({"error": "Conversation not found"}, ensure_ascii=False) + "\n"
        return

    conversation = dict(cursor[0])
    project_id = conversation["project_id"]

    assistant_model = ""
    if assistant_id:
        ac = await db.execute_fetchall("SELECT * FROM assistants WHERE id = ?", (assistant_id,))
        if ac:
            assistant = dict(ac[0])
            if assistant.get("system_prompt"):
                SYSTEM_PROMPT_OVERRIDE = assistant["system_prompt"]
            else:
                SYSTEM_PROMPT_OVERRIDE = SYSTEM_PROMPT
            assistant_model = assistant.get("model", "") or ""
        else:
            SYSTEM_PROMPT_OVERRIDE = SYSTEM_PROMPT
    else:
        SYSTEM_PROMPT_OVERRIDE = SYSTEM_PROMPT

    cursor = await db.execute_fetchall(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    )
    history = [{"role": row["role"], "content": row["content"]} for row in cursor]

    cursor = await db.execute_fetchall(
        "SELECT title, content FROM workspace_items WHERE project_id = ? AND status = 'locked' AND item_type = 'world_setting'",
        (project_id,),
    )
    world_settings = "\n\n".join(
        f"【{row['title']}】\n{row['content']}" for row in cursor
    ) if cursor else ""

    cursor = await db.execute_fetchall(
        "SELECT * FROM chronicle WHERE project_id = ?", (project_id,)
    )
    chronicle_text = ""
    if cursor:
        row = dict(cursor[0])
        chronicle_text = row.get("raw_text", "")
        if not chronicle_text:
            parts = []
            for field in ("timeline", "key_events", "unresolved_threads"):
                val = row.get(field, "[]")
                if val and val != "[]":
                    parsed = json.loads(val) if isinstance(val, str) else val
                    if parsed:
                        parts.append(f"【{field}】\n" + "\n".join(str(v) for v in parsed))
            chronicle_text = "\n".join(parts)

    context_parts = []
    if world_settings:
        context_parts.append(f"【世界观设定】\n{world_settings}")
    if chronicle_text:
        context_parts.append(f"【编年记录】\n{chronicle_text}")

    fixed_context = "\n\n".join(context_parts)

    system_prompt = SYSTEM_PROMPT_OVERRIDE
    if fixed_context:
        system_prompt = f"{SYSTEM_PROMPT_OVERRIDE}\n\n{fixed_context}"

    recent_history = history[-40:]
    messages = recent_history + [{"role": "user", "content": user_content}]

    logger.info("[stream] conversation=%s, assistant=%s, history=%d, user_content=%r", conversation_id, assistant_id or "default", len(recent_history), user_content[:50])
    full_reply = ""
    yield_count = 0
    t0 = time.time()
    async for chunk in chat_stream(messages, system_prompt, model=assistant_model):
        full_reply += chunk
        yield_count += 1
        yield json.dumps({"content": chunk}, ensure_ascii=False) + "\n"
    t1 = time.time()
    logger.info("[stream] yield done: %d yields, %d chars, %.2fs", yield_count, len(full_reply), t1 - t0)

    user_msg_id = str(uuid.uuid4())
    assistant_msg_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', ?)",
        (user_msg_id, conversation_id, user_content),
    )
    await db.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'assistant', ?)",
        (assistant_msg_id, conversation_id, full_reply),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,),
    )
    await db.commit()

    yield json.dumps({"done": True}, ensure_ascii=False) + "\n"

@router.post("/conversations/{conversation_id}/chat/stream")
async def stream_chat(conversation_id: str, body: ChatRequest):
    return StreamingResponse(
        _chat_stream_generator(conversation_id, body.content, body.assistant_id, body.regenerate),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
