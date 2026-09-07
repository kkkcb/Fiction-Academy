import json
import asyncio
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
    attach: bool = False  # True = 只接入进行中的生成（不发起）；没有则 409


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


class ConversationTitleBody(BaseModel):
    title: str


@router.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, body: ConversationTitleBody):
    db = await get_db()
    row = await fetch_one(db, "SELECT project_id FROM conversations WHERE id = ?", (conversation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    async with transaction():
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (body.title, conversation_id),
        )
        await repo.touch_project(db, row["project_id"])
    return {"id": conversation_id, "title": body.title}


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


@router.post("/projects/{project_id}/studio/ensure")
async def ensure_studio_conversation(project_id: str):
    """创建/获取项目的统一创作对话（单一对话框，作者驱动，覆盖全部点位）。"""
    db = await get_db()
    # 找已有的 studio 对话
    row = await fetch_one(
        db,
        "SELECT id FROM conversations WHERE project_id = ? AND point = '__studio__'",
        (project_id,),
    )
    if row:
        return {"conversation_id": row["id"]}
    import uuid as _uuid
    cid = str(_uuid.uuid4())
    await db.execute(
        "INSERT INTO conversations (id, project_id, title, point) VALUES (?, ?, ?, '__studio__')",
        (cid, project_id, "创作对话"),
    )
    await db.commit()
    return {"conversation_id": cid}


@router.post("/projects/{project_id}/studio/distill")
async def studio_distill(project_id: str):
    """总结创作对话的新增内容，自动分拣归入对应点位（增量：只处理上次分拣后的新消息）。"""
    import uuid as _uuid
    from backend.agents.base import chat_json
    from backend.agents.guide import POINT_LABELS
    from backend.services import repo as _repo

    db = await get_db()
    conv = await fetch_one(
        db,
        "SELECT id, distilled_rowid FROM conversations WHERE project_id = ? AND point = '__studio__'",
        (project_id,),
    )
    if not conv:
        raise HTTPException(status_code=404, detail="没有创作对话，请先和作者聊聊你的故事")

    watermark = conv["distilled_rowid"] or 0
    msgs = await fetch_all(
        db,
        "SELECT rowid, role, content FROM messages WHERE conversation_id = ? AND rowid > ? ORDER BY rowid ASC LIMIT 60",
        (conv["id"], watermark),
    )
    if len(msgs) < 2:
        raise HTTPException(status_code=400, detail="没有新的对话内容需要分拣，多聊几句再来")

    new_text = "\n".join(
        ("用户：" if m["role"] == "user" else "作者：") + (m["content"] or "")[:600] for m in msgs
    )

    # 现有点位内容（定稿优先），作为合并基底
    distill_points = ("story_core", "world_setting", "character_setting", "outline_reverse", "outline", "foreshadow")
    rows = await fetch_all(
        db,
        "SELECT id, item_type, status, content FROM workspace_items WHERE project_id = ? AND item_type IN ("
        + ",".join("?" * len(distill_points)) + ") "
        "ORDER BY CASE status WHEN 'finalized' THEN 0 WHEN 'locked' THEN 0 ELSE 1 END, sort_order",
        (project_id, *distill_points),
    )
    existing = {r["item_type"]: r for r in rows}
    if rows:
        background = "\n\n".join(
            "【" + POINT_LABELS.get(r["item_type"], r["item_type"]) + "】\n" + (r["content"] or "")[:800]
            for r in rows
        )
    else:
        background = "（全部为空，首次沉淀）"

    catalog = "\n".join("- " + pt + " " + POINT_LABELS.get(pt, pt) for pt in distill_points)
    prompt = (
        "你是设定分拣编辑。作者和用户刚聊完一轮，请把新讨论自动归入对应的设定点位。\n\n"
        "## 点位清单（point 只能取以下值）\n" + catalog + "\n\n"
        "## 现有各点位内容（合并基底）\n" + background + "\n\n"
        "## 本轮新对话\n" + new_text[:9000] + "\n\n"
        "## 分拣规则\n"
        "1. 找出新对话里值得沉淀的信息：人物设定、世界观/力量体系、情节走向、伏笔、大纲调整、故事核修正\n"
        "2. 对每个有新信息的点位输出【合并后的完整内容】：现有内容 + 新信息有机融合成一个连贯版本，不是简单拼接；没有新信息的点位不要输出\n"
        "3. 寒暄、重复、纯讨论过程不沉淀\n"
        "4. leftover 放无法归类但以后可能有用的一句话备忘，没有就空字符串\n\n"
        '输出 JSON：{"updates": [{"point": "world_setting", "note": "本次融合了什么", '
        '"content": "该点位合并后的完整内容"}], "leftover": ""}'
    )
    result = await chat_json(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="你是严谨的设定分拣编辑，只依据对话事实分拣，不自行发明设定。",
        temperature=0.3,
    )

    applied = []
    updates = result.get("updates") or []
    if not isinstance(updates, list):
        updates = []
    for u in updates:
        if not isinstance(u, dict):
            continue
        pt = u.get("point")
        if pt not in distill_points or not u.get("changed", True):
            continue
        content = (u.get("content") or "").strip()
        if len(content) < 20:
            continue
        note = (u.get("note") or "").strip()
        if pt in existing:
            await db.execute(
                "UPDATE workspace_items SET content = ?, updated_at = datetime('now') WHERE id = ?",
                (content, existing[pt]["id"]),
            )
            action = "merged"
        else:
            item_id = str(_uuid.uuid4())
            sort_order = await _repo.next_sort_order(db, project_id)
            await db.execute(
                "INSERT INTO workspace_items (id, project_id, item_type, status, title, content, sort_order) "
                "VALUES (?, ?, ?, 'draft', ?, ?, ?)",
                (item_id, project_id, pt, POINT_LABELS.get(pt, pt), content, sort_order),
            )
            action = "created"
        applied.append({"point": pt, "label": POINT_LABELS.get(pt, pt), "action": action,
                        "note": note, "chars": len(content)})
    leftover = (result.get("leftover") or "").strip()

    if applied:
        lines = ["✅【" + a["label"] + "】" + (a["note"] or (str(a["chars"]) + " 字")) for a in applied]
        text = "已把本轮讨论分拣进设定：\n\n" + "\n".join(lines)
    else:
        text = "本轮对话没有需要沉淀的新设定（寒暄和重复内容已忽略）。"
    if leftover:
        text += "\n\n📝 备忘（暂无归属）：" + leftover[:200]
    await _repo.save_message(db, conv["id"], "assistant", text)

    # 水位推进到汇报消息之后，本轮内容和汇报本身都不会进下一批
    cursor = await db.execute(
        "SELECT MAX(rowid) AS m FROM messages WHERE conversation_id = ?", (conv["id"],)
    )
    max_row = await cursor.fetchone()
    await cursor.close()
    await db.execute(
        "UPDATE conversations SET distilled_rowid = ?, updated_at = datetime('now') WHERE id = ?",
        (max_row["m"] or watermark, conv["id"]),
    )
    await db.commit()
    return {"ok": True, "applied": applied, "leftover": leftover, "message": text}


@router.post("/projects/{project_id}/studio/build")
async def studio_build_skeleton(project_id: str):
    """从创作对话历史一键生成全部骨架点位（故事核→世界观→人物→倒推→正向）。"""
    import asyncio as _aio
    import uuid as _uuid
    from backend.agents.chapter_plan import generate_chapter_plan, format_chapter_plan_markdown
    from backend.services import repo as _repo

    db = await get_db()

    # 1. 取 studio 对话全文作为上下文
    conv = await fetch_one(db, "SELECT id FROM conversations WHERE project_id = ? AND point = '__studio__'", (project_id,))
    if not conv:
        raise HTTPException(status_code=404, detail="没有创作对话，请先和作者聊聊你的故事")
    msgs = await fetch_all(
        db,
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC",
        (conv["id"],),
    )
    if len(msgs) < 2:
        raise HTTPException(status_code=400, detail="对话内容太少，多聊几句再生成")
    conversation_text = "\n".join(
        ("用户：" if m["role"] == "user" else "作者：") + (m["content"] or "")[:300] for m in msgs[-30:]
    )

    # 2. 已定稿的点位跳过
    existing = await fetch_all(
        db,
        "SELECT item_type FROM workspace_items WHERE project_id = ? AND status IN ('finalized','locked') AND item_type IN ('story_core','world_setting','character_setting','outline_reverse','outline')",
        (project_id,),
    )
    done = {r["item_type"] for r in existing}

    # 3. 逐个生成（带对话上下文）
    POINT_SEQUENCES = ["story_core", "world_setting", "character_setting", "outline_reverse", "outline"]
    generated = []
    errors = []

    from backend.agents.base import chat_json
    from backend.api.points import AUTO_GENERATE_SYSTEM_PROMPT
    from backend.agents.guide import POINT_LABELS
    from backend.agents.guide_prompts import POINT_CONFIGS

    for pt in POINT_SEQUENCES:
        if pt in done:
            continue
        label = POINT_LABELS.get(pt, pt)
        config = POINT_CONFIGS.get(pt, {})
        fields_hint = json.dumps(config.get("fields", {}), ensure_ascii=False, indent=2)

        # 前序已生成的内容作为背景
        bg_parts = []
        bg_rows = await fetch_all(
            db,
            "SELECT item_type, content, metadata FROM workspace_items WHERE project_id = ? AND item_type IN ('story_core','world_setting','character_setting','outline_reverse','outline') AND status IN ('finalized','locked') ORDER BY sort_order",
            (project_id,),
        )
        for r in bg_rows:
            bg_parts.append(
                "【" + POINT_LABELS.get(r["item_type"], r["item_type"]) + "】\n" + (r["content"] or "")[:400]
            )
        background = "\n\n".join(bg_parts) if bg_parts else "（无前序设定）"

        prompt = (
            "以下是作者和用户关于这部小说的完整对话记录，请从中抽离出【" + label + "】的结构化设定。\n\n"
            "## 对话记录\n" + conversation_text[:6000] + "\n\n"
            "## 已确定的其他设定（保持一致）\n" + background + "\n\n"
            "## 该点位需要生成的字段\n" + fields_hint + "\n\n"
            "请基于对话内容直接生成。对话中用户明确表达的偏好必须遵守；用户没提到的部分你补全。"
            "大胆创作，让内容有网文味、有冲突、有爽点。\n\n"
            '输出 JSON：{"summary": "300-600字连贯设定", "fields": {}}'
        )

        try:
            result = await chat_json(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=AUTO_GENERATE_SYSTEM_PROMPT,
                temperature=0.8,
            )
            summary = result.get("summary", "")
            fields = result.get("fields", {})
            if not isinstance(fields, dict):
                fields = {}

            item_id = str(_uuid.uuid4())
            sort_order = await _repo.next_sort_order(db, project_id)
            await db.execute(
                """INSERT INTO workspace_items
                   (id, project_id, item_type, status, title, content, metadata, sort_order)
                   VALUES (?, ?, ?, 'finalized', ?, ?, ?, ?)""",
                (item_id, project_id, pt, label, summary, json.dumps(fields, ensure_ascii=False), sort_order),
            )
            await db.commit()

            # 自动命名
            if pt == "story_core":
                new_name = await _repo.maybe_apply_book_name(db, project_id, fields)
                if new_name:
                    logger.info("[studio-build] auto-named to %r", new_name)

            generated.append({"point": pt, "label": label, "chars": len(summary)})
        except Exception as e:
            logger.error("[studio-build] %s failed: %s", pt, e)
            errors.append(f"{label}: {str(e)[:80]}")

    # 4. 写入一条总结消息到对话
    if generated:
        summary_lines = ["✅ " + g["label"] + "（" + str(g["chars"]) + "字）" for g in generated]
        text = "骨架生成完成！\n\n" + "\n".join(summary_lines)
        if errors:
            text += "\n\n⚠ " + "; ".join(errors)
        text += "\n\n可以去「小说写作」开始第一章了。"
        await _repo.save_message(db, conv["id"], "assistant", text)
        await db.execute("UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conv["id"],))
        await db.commit()

    return {"ok": True, "generated": generated, "skipped": list(done), "errors": errors}


@router.post("/conversations/{conversation_id}/chat/stream")
async def stream_chat(conversation_id: str, body: ChatRequest):
    """聊天流。生成在服务端后台任务中运行，本连接只是订阅者：
    刷新/断线不中断生成，重连（attach=true 或再次 POST）即可回放继续观看。"""
    db = await get_db()
    conv = await fetch_one(db, "SELECT * FROM conversations WHERE id = ?", (conversation_id,))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    session = _chat_live.get(conversation_id)
    if session and not session.done:
        # 已在生成（可能是刷新后重连）：直接订阅观看
        return StreamingResponse(session.subscribe(), media_type="application/x-ndjson")
    if body.attach:
        raise HTTPException(status_code=409, detail="当前没有进行中的生成")

    session = LiveChatSession()
    _chat_live[conversation_id] = session
    session.task = asyncio.ensure_future(_run_chat_live(
        session, conversation_id, conv["project_id"], body.content,
        body.assistant_id or "", body.regenerate, conv.get("point") or ""))
    return StreamingResponse(session.subscribe(), media_type="application/x-ndjson")


@router.post("/conversations/{conversation_id}/chat/stop")
async def stop_chat(conversation_id: str):
    """停止后台生成：已生成部分保留。"""
    session = _chat_live.get(conversation_id)
    if session and not session.done:
        session.cancelled = True
        return {"ok": True, "stopped": True}
    return {"ok": True, "stopped": False}


class LiveChatSession:
    """服务端后台聊天会话：事件留档可回放，订阅者断线不影响生成。"""

    def __init__(self):
        self.events: list[dict] = []
        self.queues: set[asyncio.Queue] = set()
        self.cancelled = False
        self.done = False
        self.task: asyncio.Task | None = None

    def publish(self, ev: dict) -> None:
        self.events.append(ev)
        for q in list(self.queues):
            q.put_nowait(ev)

    def finish(self) -> None:
        self.done = True
        for q in list(self.queues):
            q.put_nowait(None)

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        self.queues.add(q)
        try:
            for ev in list(self.events):
                yield json.dumps(ev, ensure_ascii=False) + "\n"
                if ev.get("done") or ev.get("error") or ev.get("stopped"):
                    return
            if self.done:
                return
            while True:
                ev = await q.get()
                if ev is None:
                    return
                yield json.dumps(ev, ensure_ascii=False) + "\n"
                if ev.get("done") or ev.get("error") or ev.get("stopped"):
                    return
        finally:
            self.queues.discard(q)


_chat_live: dict[str, LiveChatSession] = {}


async def _run_chat_live(session: LiveChatSession, conversation_id: str, project_id: str,
                         user_content: str, assistant_id: str, regenerate: bool, point: str):
    try:
        async for ev in _chat_events(conversation_id, project_id, user_content,
                                     assistant_id, regenerate, point, live=session):
            session.publish(ev)
    except Exception as e:  # 后台任务无请求方接异常，必须兜底
        logger.error("[chat-live] conversation=%s crashed: %s", conversation_id, e, exc_info=True)
        session.publish({"error": f"生成异常: {str(e)[:120]}"})
    finally:
        _chat_live.pop(conversation_id, None)
        session.finish()


class PunctuateBody(BaseModel):
    text: str = ""


@router.post("/punctuate")
async def punctuate(body: PunctuateBody):
    """给语音转写加标点：只加标点不改字，失败时原样返回（不阻塞输入）。"""
    text = (body.text or "").strip()
    if not text or len(text) > 2000:
        return {"text": body.text or ""}
    try:
        out = ""
        async for kind, chunk in chat_stream(
            [{"role": "user", "content": text}],
            system_prompt=(
                "给下面这段中文口述转写添加标点符号。规则：只加标点（，。！？；：、""''——……），"
                "不增加字、不删除字、不修改任何字，不输出任何解释。直接输出加好标点的原文。"
            ),
            temperature=0.0,
            disable_thinking=True,
        ):
            if kind == "content":
                out += chunk
        out = out.strip().strip('"').strip("'").strip('"').strip('"')
        if out:
            return {"text": out}
    except Exception as e:
        logger.warning("[punctuate] failed: %s", e)
    return {"text": body.text or ""}


class PunctuateBody(BaseModel):
    text: str = ""


@router.post("/projects/{project_id}/outline-studio/distill")
async def outline_studio_distill(project_id: str):
    """把大纲语音对话（point='__outline__'）落成倒推大纲+正向大纲草稿（可反复生成覆盖草稿）。"""
    import uuid as _uuid
    from backend.agents.base import chat_json
    from backend.api.points import AUTO_GENERATE_SYSTEM_PROMPT
    from backend.agents.guide import POINT_LABELS
    from backend.agents.guide_prompts import POINT_CONFIGS
    from backend.services import repo as _repo

    db = await get_db()
    conv = await fetch_one(
        db, "SELECT id FROM conversations WHERE project_id = ? AND point = '__outline__'", (project_id,))
    if not conv:
        raise HTTPException(status_code=404, detail="还没有大纲对话，先进「大纲语音对话」聊几句")
    msgs = await fetch_all(
        db,
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC",
        (conv["id"],),
    )
    if len(msgs) < 2:
        raise HTTPException(status_code=400, detail="对话内容太少，多聊几问再生成")
    conversation_text = "\n".join(
        ("用户：" if m["role"] == "user" else "主持：") + (m["content"] or "")[:300] for m in msgs[-40:]
    )

    # 已定稿的不覆盖；已有的草稿会被新版覆盖（访谈反复迭代）
    existing = await fetch_all(
        db,
        """SELECT item_type, id FROM workspace_items WHERE project_id = ?
           AND item_type IN ('outline_reverse', 'outline') AND status IN ('finalized','locked')""",
        (project_id,),
    )
    done = {r["item_type"]: r["id"] for r in existing}

    bg_rows = await fetch_all(
        db,
        """SELECT item_type, content FROM workspace_items WHERE project_id = ?
           AND item_type IN ('story_core','world_setting','character_setting') AND status IN ('finalized','locked')
           ORDER BY sort_order""",
        (project_id,),
    )
    background = "\n\n".join(
        "【" + POINT_LABELS.get(r["item_type"], r["item_type"]) + "】\n" + (r["content"] or "")[:400]
        for r in bg_rows
    ) or "（无前序设定）"

    generated, errors = [], []
    for pt in ("outline_reverse", "outline"):
        if pt in done:
            continue
        label = POINT_LABELS.get(pt, pt)
        fields_hint = json.dumps(POINT_CONFIGS.get(pt, {}).get("fields", {}), ensure_ascii=False, indent=2)
        prompt = (
            "以下是访谈主持人和用户为确定这部小说大纲的对话记录。请从中抽离出【" + label + "】的结构化内容。\n\n"
            "## 对话记录\n" + conversation_text[:6000] + "\n\n"
            "## 已确定的设定（必须保持一致）\n" + background + "\n\n"
            "## 该点位需要的字段\n" + fields_hint + "\n\n"
            "只依据对话中用户确认过的内容；没覆盖到的部分按对话走向合理补全。输出 JSON：{\"summary\": \"300-600字连贯设定\", \"fields\": {}}"
        )
        try:
            result = await chat_json(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=AUTO_GENERATE_SYSTEM_PROMPT,
                temperature=0.8,
            )
            summary = result.get("summary", "")
            fields = result.get("fields", {}) if isinstance(result.get("fields"), dict) else {}
            draft = await fetch_one(
                db,
                """SELECT id FROM workspace_items WHERE project_id = ? AND item_type = ? AND status = 'draft'""",
                (project_id, pt),
            )
            if draft:
                await db.execute(
                    "UPDATE workspace_items SET content = ?, metadata = ?, updated_at = datetime('now') WHERE id = ?",
                    (summary, json.dumps(fields, ensure_ascii=False), draft["id"]),
                )
                item_id = draft["id"]
            else:
                item_id = str(_uuid.uuid4())
                sort_order = await _repo.next_sort_order(db, project_id)
                await db.execute(
                    """INSERT INTO workspace_items
                       (id, project_id, item_type, status, title, content, metadata, sort_order)
                       VALUES (?, ?, ?, 'draft', ?, ?, ?, ?)""",
                    (item_id, project_id, pt, label, summary, json.dumps(fields, ensure_ascii=False), sort_order),
                )
            await db.commit()
            generated.append({"point": pt, "label": label, "chars": len(summary)})
        except Exception as e:
            logger.error("[outline-distill] %s failed: %s", pt, e)
            errors.append(f"{label}: {str(e)[:80]}")

    if generated:
        text = "大纲草稿已生成：\n\n" + "\n".join(
            "✅ " + g["label"] + "（" + str(g["chars"]) + "字）" for g in generated
        ) + "\n\n草稿在工作区【大纲】点位，确认后定稿。聊了新内容随时可以重新生成覆盖。"
        if errors:
            text += "\n\n⚠ " + "; ".join(errors)
        await _repo.save_message(db, conv["id"], "assistant", text)
        await db.execute("UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conv["id"],))
        await db.commit()

    return {"ok": True, "generated": generated, "skipped": list(done.keys()), "errors": errors}


async def _chat_events(
    conversation_id: str,
    project_id: str,
    user_content: str,
    assistant_id: str,
    regenerate: bool,
    point: str = "",
    live: "LiveChatSession | None" = None,
):
    """纯事件生成器：yield dict。由后台任务驱动，与客户端连接解耦。"""
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
            yield {"error": "没有可重新生成的消息"}
            return
    else:
        if not user_content.strip():
            yield {"error": "消息不能为空"}
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
    elif point == "__outline__":
        # 大纲语音对话：访谈主持人，一次一个问题把大纲敲定（用户多为语音输入）
        base_prompt = (
            "你是一位老练的网文大纲访谈主持人。用户正在用语音跟你对话，目标是把这部小说的大纲敲定。"
            "语音转文字常无标点、有口语碎片和错别字，你要自然理解并归纳，不要逐字较真，也不要提'语音识别'。\n\n"
            "## 访谈清单（按顺序逐项敲定）\n"
            "倒推五问：① 终局画面——全书最后一幕是什么？② 真相底牌——故事背后藏着的最大秘密是什么？"
            "③ 中段低谷——主角最惨的一刻是什么？④ 身份揭穿——主角的底牌何时、如何被揭开？"
            "⑤ 日常起点——故事从什么样的日常开场？\n"
            "正向三问：⑥ 三幕划分——开局/中段/收官各写什么？⑦ 卷设计——每卷的核心冲突与爽点升级；"
            "⑧ 结局落点——结局停在哪个画面、留什么余韵。\n\n"
            "## 你的行为方式\n"
            "- **一次只问一个问题**，问得具体（给2-3个方向让用户挑，不空问'你想要什么'）\n"
            "- 用户答完，先用一句话复述你听懂的版本让他确认，再进入下一问；他说'对/行/嗯'就算确认\n"
            "- 用户说'跳过/下一个'就跳过当前问题；说'随便/你定'时你直接给出你最推荐的方向并继续\n"
            "- 回复要短（两三句），适合念出来听——用户在听，不是在读\n"
            "- 与已有设定（见下方上下文）冲突时立刻指出，请用户拍板\n"
            "- 八问都覆盖后，明确说：'大纲聊完了，点【生成大纲草稿】我给你落成稿子。'\n"
        )
    elif point == "__studio__":
        # 统一创作对话：自然自由聊天，不引导点位顺序，聊完一键抽离骨架
        from backend.agents.authors import get_author
        proj = await fetch_one(db, "SELECT author_key FROM projects WHERE id = ?", (project_id,))
        _author_key = (proj or {}).get("author_key") or ""
        if not _author_key:
            # 作者人格是必选项：没有它就没有文风，不悄悄回退默认作者
            yield {"error": "还没选择作者人格。请先在项目里选一位作者（决定对话和执笔的文风），选完再回来聊。"}
            return
        author = get_author(_author_key)
        base_prompt = (
            author["style_dna"]
            + "\n\n你现在是作者「" + author["name"] + "」，正在和用户聊一个想写的故事。"
            + "这不是填表，是一场自然的天马行空的创作对话。\n\n"
            + "## 你的行为方式\n"
            + "- **像朋友聊天**：用户说想法时你接梗、发散、补充，不像审稿人在过流程\n"
            + '- **不提「点位」「骨架」「故事核」这些系统术语**——就聊故事本身：主角是谁、世界什么样、冲突在哪、结局怎么收\n'
            + "- **聊天中自然覆盖**：随着对话深入，故事的核、世界观、人物、情节线会自然浮现，不需要按顺序\n"
            + "- **给选项不给问卷**：聊到关键设定时给2-3个截然不同的方向让用户挑，而不是空问'你想要什么'\n"
            + "- **用户说'随便'时直接推你最推荐的方向**，不追问\n"
            + "- **觉得故事差不多了时**，主动说'我觉得骨架差不多了，要不要我帮你生成结构化的骨架？'——用户同意后提示他输入 /build；平时聊出了不少新设定，也可以提醒他输入 /distill 把新内容自动归档到对应设定\n"
            + "\n当前骨架状态见下方上下文（已定稿的点位无需重复讨论）。\n"
        )
    elif point in POINT_PERSONAS:
        base_prompt = POINT_PERSONAS[point][1]
    else:
        base_prompt = SYSTEM_PROMPT

    # studio 对话：追加骨架进度总览（哪些点位定稿了，哪些还缺）
    if point == "__studio__":
        ws_rows = await fetch_all(
            db,
            """SELECT item_type FROM workspace_items
               WHERE project_id = ? AND item_type IN ('story_core','world_setting','character_setting','outline_reverse','outline')
                 AND status IN ('finalized','locked')""",
            (project_id,),
        )
        done_types = {r["item_type"] for r in ws_rows}
        all_types = ["story_core", "world_setting", "character_setting", "outline_reverse", "outline"]
        labels = {"story_core": "故事核", "world_setting": "世界观", "character_setting": "核心人物",
                  "outline_reverse": "倒推大纲", "outline": "正向大纲"}
        status_lines = ["- " + labels[t] + "：" + ("✅ 已定稿" if t in done_types else "⬜ 未完成") for t in all_types]
        skeleton_overview = "## 当前骨架进度\n" + "\n".join(status_lines)
        context_body = (context_body + "\n\n" + skeleton_overview) if context_body else skeleton_overview

    final_system_prompt = (base_prompt + "\n\n" + context_body) if context_body else base_prompt

    # 非 regenerate 时 user 消息刚写库、已在 recent_history 里，不重复追加
    messages = list(recent_history)
    if regenerate and user_content and (not messages or messages[-1]["role"] != "user"):
        messages.append({"role": "user", "content": user_content})

    logger.info("[stream] conversation=%s assistant=%s history=%d regenerate=%s",
                conversation_id, assistant_id or "default", len(messages), regenerate)

    full_reply = ""
    # 开写即建行、边写边落库：刷新/断线后已生成部分不丢
    _msg_id = await repo.save_message(db, conversation_id, "assistant", "")
    _saved_len = 0
    import time as _t
    _last_save = _t.time()
    try:
        async for kind, chunk in chat_stream(messages, system_prompt=final_system_prompt, model=assistant_model):
            if live is not None and live.cancelled:
                break
            if kind == "reasoning":
                yield {"thinking": chunk}
            else:
                full_reply += chunk
                yield {"content": chunk}
                if len(full_reply) - _saved_len >= 120 or _t.time() - _last_save >= 1.0:
                    _saved_len = len(full_reply)
                    _last_save = _t.time()
                    await db.execute("UPDATE messages SET content = ? WHERE id = ?", (full_reply, _msg_id))
    except LLMError as e:
        logger.error("[stream] LLM error for conversation=%s: %s", conversation_id, e)
        if full_reply:
            full_reply += f"\n\n[生成中断: {e}]"
        yield {"error": f"生成失败: {e}"}
        return
    except Exception as e:
        logger.error("[stream] unexpected error for conversation=%s: %s", conversation_id, e, exc_info=True)
        yield {"error": f"生成失败: {e}"}
        return
    finally:
        # 完成落最终版；取消/异常时兜底保存已生成部分；空回复删行
        if full_reply.strip():
            await db.execute("UPDATE messages SET content = ? WHERE id = ?", (full_reply, _msg_id))
            await db.commit()
            async with transaction():
                await db.execute("UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conversation_id,))
                await repo.touch_project(db, project_id)
        else:
            await db.execute("DELETE FROM messages WHERE id = ?", (_msg_id,))
            await db.commit()

    if live is not None and live.cancelled:
        yield {"stopped": True}
        return

    yield {"done": True}
