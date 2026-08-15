import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one, transaction
from backend.agents.base import chat_stream, LLMError
from backend.agents.personas import POINT_PERSONAS
from backend.config import CHAT_HISTORY_LIMIT, SYSTEM_PROMPT
from backend.services import repo
from backend.services.context_builder import ContextRequest, build_chat_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MSG_ORDER = "created_at ASC, rowid ASC"


class ChatRequest(BaseModel):
    content: str = ""
    assistant_id: str | None = None
    regenerate: bool = False


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
    async with transaction():
        await db.execute(
            "INSERT INTO conversations (id, project_id, title) VALUES (?, ?, ?)",
            (cid, project_id, title),
        )
        await repo.touch_project(db, project_id)
    return {"id": cid, "project_id": project_id, "title": title}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    db = await get_db()
    rows = await fetch_all(
        db,
        f"SELECT * FROM messages WHERE conversation_id = ? ORDER BY {MSG_ORDER}",
        (conversation_id,),
    )
    return rows


@router.delete("/messages/{message_id}")
async def delete_message(message_id: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT id, conversation_id FROM messages WHERE id = ?", (message_id,))
    if not row:
        raise HTTPException(status_code=404, detail="消息不存在")
    await db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    await db.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (row["conversation_id"],),
    )
    await db.commit()
    return {"ok": True}


@router.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, title: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT project_id FROM conversations WHERE id = ?", (conversation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    async with transaction():
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, conversation_id),
        )
        await repo.touch_project(db, row["project_id"])
    return {"id": conversation_id, "title": title}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT project_id FROM conversations WHERE id = ?", (conversation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    async with transaction():
        await db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        await repo.touch_project(db, row["project_id"])
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
            conv.get("point") or "",
        ),
        media_type="application/x-ndjson",
    )


async def _chat_stream_generator(
    conversation_id: str,
    project_id: str,
    user_content: str,
    assistant_id: str,
    regenerate: bool,
    point: str = "",
):
    db = await get_db()

    if regenerate:
        last_assistant = await fetch_one(
            db,
            f"SELECT id FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (conversation_id,),
        )
        last_user = await fetch_one(
            db,
            f"SELECT id, content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (conversation_id,),
        )
        async with transaction():
            if last_assistant:
                await db.execute("DELETE FROM messages WHERE id = ?", (last_assistant["id"],))
        # 重新生成复用已有 user 消息：不再追加，历史里已包含它
        user_content = last_user["content"] if last_user else ""
        if not user_content:
            yield json.dumps({"error": "没有可重新生成的消息"}, ensure_ascii=False) + "\n"
            return
    else:
        if not user_content.strip():
            yield json.dumps({"error": "消息不能为空"}, ensure_ascii=False) + "\n"
            return
        async with transaction():
            await repo.save_message(db, conversation_id, "user", user_content)
            await db.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )
            await repo.touch_project(db, project_id)

    history = await fetch_all(
        db,
        f"SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY {MSG_ORDER}",
        (conversation_id,),
    )
    recent_history = history[-CHAT_HISTORY_LIMIT:]
    while recent_history and recent_history[0]["role"] == "assistant":
        recent_history = recent_history[1:]

    system_prompt_override, assistant_model = await _get_assistant_prompt(db, assistant_id)
    req = ContextRequest(
        project_id=project_id,
        user_content=user_content,
        point=point,
    )
    context_body = await build_chat_context(req)

    # 基础人格优先级：显式选择的助理 > 点位专属角色 > 默认助手
    if system_prompt_override:
        base_prompt = system_prompt_override
    elif point in POINT_PERSONAS:
        base_prompt = POINT_PERSONAS[point][1]
    else:
        base_prompt = SYSTEM_PROMPT

    final_system_prompt = (base_prompt + "\n\n" + context_body) if context_body else base_prompt

    # 非 regenerate 时 user 消息刚写库、已在 recent_history 里，不重复追加
    messages = list(recent_history)
    if regenerate and user_content and (not messages or messages[-1]["role"] != "user"):
        messages.append({"role": "user", "content": user_content})

    logger.info("[stream] conversation=%s assistant=%s history=%d regenerate=%s",
                conversation_id, assistant_id or "default", len(messages), regenerate)

    full_reply = ""
    try:
        async for kind, chunk in chat_stream(messages, system_prompt=final_system_prompt, model=assistant_model):
            if kind == "reasoning":
                yield json.dumps({"thinking": chunk}, ensure_ascii=False) + "\n"
            else:
                full_reply += chunk
                yield json.dumps({"content": chunk}, ensure_ascii=False) + "\n"
    except LLMError as e:
        logger.error("[stream] LLM error for conversation=%s: %s", conversation_id, e)
        if full_reply:
            await repo.save_message(db, conversation_id, "assistant", full_reply + f"\n\n[生成中断: {e}]")
        yield json.dumps({"error": f"生成失败: {e}"}, ensure_ascii=False) + "\n"
        return
    except Exception as e:
        logger.error("[stream] unexpected error for conversation=%s: %s", conversation_id, e, exc_info=True)
        yield json.dumps({"error": f"生成失败: {e}"}, ensure_ascii=False) + "\n"
        return

    if full_reply.strip():
        async with transaction():
            await repo.save_message(db, conversation_id, "assistant", full_reply)
            await db.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )
            await repo.touch_project(db, project_id)

    yield json.dumps({"done": True}, ensure_ascii=False) + "\n"
