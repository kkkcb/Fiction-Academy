"""章纲 API —— 三段式写章的「备稿」环节 + 一键执笔流式端点。"""
import json
import uuid
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one
from backend.agents.base import chat_stream, LLMError
from backend.agents.chapter_plan import generate_chapter_plan, format_chapter_plan_markdown
from backend.agents.guide import POINT_LABELS
from backend.agents.reviewer import review_chapter, should_retry, build_revision_feedback
from backend.services.repo import parse_meta, next_sort_order

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

SKELETON_TYPES = ("story_core", "world_setting", "character_setting", "outline", "outline_reverse")


class ChapterPlanRequest(BaseModel):
    user_hint: str = ""
    regenerate: bool = False


def _format_skeleton_for_plan(rows: list[dict]) -> str:
    """把骨架点位格式化为章纲/执笔的约束摘要（结构化字段 + 设定正文摘录）。"""
    parts = []
    for r in rows:
        label = POINT_LABELS.get(r["item_type"], r["item_type"])
        content = (r.get("content") or "").strip()
        meta = parse_meta(r.get("metadata"))

        block_parts = []
        if r["item_type"] == "story_core":
            block_parts.append(f"核心：{meta.get('one_liner', '')}\n套路：{meta.get('trope', '')}")
        elif r["item_type"] == "world_setting":
            block_parts.append(
                f"力量体系：{meta.get('power_system', '')}\n硬限制：{meta.get('power_limit', '')}\n金手指：{meta.get('golden_finger', '')}"
            )
        elif r["item_type"] == "character_setting":
            red_lines = meta.get("red_lines", [])
            red_text = "；".join(red_lines) if isinstance(red_lines, list) else str(red_lines)
            block_parts.append(f"姓名：{meta.get('name', '')}\n核心欲望：{meta.get('core_desire', '')}\n红线（绝不做）：{red_text}")
        elif r["item_type"] == "outline_reverse":
            turns = meta.get("key_turning_points", [])
            turns_text = " → ".join(turns) if isinstance(turns, list) else str(turns)
            block_parts.append(f"终点：{meta.get('endpoint_state', '')}\n关键转折：{turns_text}")
        elif r["item_type"] == "outline":
            block_parts.append(f"第一幕：{meta.get('act1', '')}")

        # 设定正文比字段更完整，截取摘录补充给模型
        if content:
            block_parts.append(f"设定摘录：{content[:400]}")

        parts.append(f"### {label}\n" + "\n".join(p for p in block_parts if p))

    return "\n\n".join(parts) if parts else "（骨架尚未完善）"


async def _load_recent_chapter_summary(db, project_id: str, limit: int = 3) -> str:
    rows = await fetch_all(
        db,
        """SELECT title, content, chapter_number FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter'
                 AND status IN ('finalized', 'locked')
           ORDER BY chapter_number DESC LIMIT ?""",
        (project_id, limit),
    )
    if not rows:
        return ""
    lines = []
    for r in reversed(rows):
        content = (r.get("content") or "")[:500]
        num = r.get("chapter_number", "?")
        title = r.get("title", "")
        lines.append(f"第{num}章 {title}：{content}...")
    return "\n\n".join(lines)


async def _load_pending_foreshadows(db, project_id: str, chapter_number: int) -> list[dict]:
    rows = await fetch_all(
        db,
        """SELECT title, content, metadata FROM workspace_items
           WHERE project_id = ? AND item_type = 'foreshadow' AND status IN ('finalized', 'locked')""",
        (project_id,),
    )
    pending = []
    for r in rows:
        meta = parse_meta(r.get("metadata"))
        status = meta.get("status", "open")
        payoff = meta.get("payoff_chapter")
        if status == "open" and payoff is not None and int(payoff) <= chapter_number:
            pending.append({
                "content": r.get("content") or r.get("title", ""),
                "setup_chapter": meta.get("setup_chapter"),
                "payoff_chapter": payoff,
            })
    return pending


async def _get_next_chapter_number(db, project_id: str) -> int:
    row = await fetch_one(
        db,
        "SELECT MAX(chapter_number) as mx FROM workspace_items WHERE project_id = ? AND item_type = 'chapter'",
        (project_id,),
    )
    if row and row["mx"]:
        return int(row["mx"]) + 1
    return 1


@router.post("/projects/{project_id}/chapter-plan/generate")
async def create_chapter_plan(project_id: str, body: ChapterPlanRequest):
    """生成章纲（备稿阶段）。"""
    db = await get_db()
    proj = await fetch_one(db, "SELECT id FROM projects WHERE id = ?", (project_id,))
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    skeleton_rows = await fetch_all(
        db,
        f"""SELECT item_type, title, content, metadata FROM workspace_items
            WHERE project_id = ? AND item_type IN ({','.join('?' * len(SKELETON_TYPES))})
                  AND status IN ('finalized', 'locked')""",
        (project_id, *SKELETON_TYPES),
    )

    if not skeleton_rows:
        raise HTTPException(
            status_code=409,
            detail="骨架尚未建立，请先完成骨架引导再生成章纲",
        )

    chapter_number = await _get_next_chapter_number(db, project_id)

    existing = None
    if not body.regenerate:
        existing = await fetch_one(
            db,
            """SELECT id FROM workspace_items
               WHERE project_id = ? AND item_type = 'chapter_plan'
                     AND chapter_number = ?""",
            (project_id, chapter_number),
        )
    if existing:
        return {"id": existing["id"], "chapter_number": chapter_number, "message": "章纲已存在"}

    skeleton_context = _format_skeleton_for_plan(skeleton_rows)
    recent_summary = await _load_recent_chapter_summary(db, project_id)
    pending_foreshadows = await _load_pending_foreshadows(db, project_id, chapter_number)

    try:
        plan = await generate_chapter_plan(
            chapter_number=chapter_number,
            skeleton_context=skeleton_context,
            recent_summary=recent_summary,
            pending_foreshadows=pending_foreshadows,
            user_hint=body.user_hint,
        )
    except Exception as e:
        logger.error("Chapter plan generation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"章纲生成失败: {str(e)[:100]}")

    content, metadata = format_chapter_plan_markdown(plan, chapter_number)

    from backend.services import repo
    item_id = str(uuid.uuid4())
    sort_order = await repo.next_sort_order(db, project_id)

    await db.execute(
        """INSERT INTO workspace_items
           (id, project_id, item_type, status, title, content, metadata, chapter_number, sort_order)
           VALUES (?, ?, 'chapter_plan', 'draft', ?, ?, ?, ?, ?)""",
        (
            item_id, project_id,
            metadata.get("chapter_title", f"第{chapter_number}章"),
            content, json.dumps(metadata, ensure_ascii=False),
            chapter_number, sort_order,
        ),
    )
    await db.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
    await db.commit()

    return {
        "id": item_id,
        "chapter_number": chapter_number,
        "content": content,
        "metadata": metadata,
    }


@router.get("/projects/{project_id}/chapter-plan/{chapter_number}")
async def get_chapter_plan(project_id: str, chapter_number: int):
    """获取指定章节的章纲。"""
    db = await get_db()
    row = await fetch_one(
        db,
        """SELECT id, title, content, metadata, status FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter_plan' AND chapter_number = ?""",
        (project_id, chapter_number),
    )
    if not row:
        raise HTTPException(status_code=404, detail="章纲不存在")
    meta = parse_meta(row.get("metadata"))
    return {
        "id": row["id"],
        "chapter_number": chapter_number,
        "title": row["title"],
        "content": row["content"],
        "metadata": meta,
        "status": row["status"],
    }


@router.put("/projects/{project_id}/chapter-plan/{chapter_number}/confirm")
async def confirm_chapter_plan(project_id: str, chapter_number: int):
    """确认章纲，标记为 finalized。确认后才能进入执笔阶段。"""
    db = await get_db()
    row = await fetch_one(
        db,
        "SELECT id, status FROM workspace_items WHERE project_id = ? AND item_type = 'chapter_plan' AND chapter_number = ?",
        (project_id, chapter_number),
    )
    if not row:
        raise HTTPException(status_code=404, detail="章纲不存在")

    await db.execute(
        "UPDATE workspace_items SET status = 'finalized', updated_at = datetime('now') WHERE id = ?",
        (row["id"],),
    )
    await db.commit()
    return {"id": row["id"], "status": "finalized", "chapter_number": chapter_number}


class ReviewRequest(BaseModel):
    chapter_content: str
    max_retries: int = 3


async def _load_constraints_for_review(db, project_id: str, chapter_number: int) -> tuple:
    """加载审校所需的全部约束（统一走 repo，metadata 与设定正文节选一起给）。"""
    from backend.services import repo

    plan_row = await fetch_one(
        db,
        """SELECT content, metadata FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter_plan' AND chapter_number = ?""",
        (project_id, chapter_number),
    )
    plan_meta = repo.parse_meta(plan_row.get("metadata")) if plan_row else {}

    async def _first_meta(item_type: str) -> dict:
        rows = await repo.load_finalized_items(db, project_id, [item_type], limit=1)
        if not rows:
            return {}
        meta = dict(rows[0]["metadata"])
        meta["content_excerpt"] = (rows[0].get("content") or "")[:400]
        return meta

    char_meta = await _first_meta("character_setting")
    world_meta = await _first_meta("world_setting")
    outline_rev_meta = await _first_meta("outline_reverse")

    pending_foreshadows = await _load_pending_foreshadows(db, project_id, chapter_number)

    return plan_meta, char_meta, world_meta, outline_rev_meta, pending_foreshadows


@router.post("/projects/{project_id}/chapters/{chapter_number}/review")
async def review_chapter_api(project_id: str, chapter_number: int, body: ReviewRequest):
    """独立审校一章内容（Loop 验证器）。"""
    db = await get_db()
    proj = await fetch_one(db, "SELECT id FROM projects WHERE id = ?", (project_id,))
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    plan_meta, char_meta, world_meta, outline_rev_meta, pending_fs = await _load_constraints_for_review(
        db, project_id, chapter_number
    )

    try:
        review_result = await review_chapter(
            chapter_content=body.chapter_content,
            chapter_plan=plan_meta,
            character_constraints=char_meta,
            world_constraints=world_meta,
            outline_reverse=outline_rev_meta,
            pending_foreshadows=pending_fs,
        )
    except Exception as e:
        logger.error("Chapter review failed: %s", e)
        raise HTTPException(status_code=502, detail=f"审校失败: {str(e)[:100]}")

    needs_revision = should_retry(review_result, body.max_retries)
    revision_feedback = build_revision_feedback(review_result) if needs_revision else ""

    return {
        "chapter_number": chapter_number,
        "overall": review_result.get("overall", "warn"),
        "issues": review_result.get("issues", []),
        "summary": review_result.get("summary", ""),
        "needs_revision": needs_revision,
        "revision_feedback": revision_feedback,
    }


# ============================================================
# 一键执笔：章纲（自动确保）→ 流式写正文 → 存档 → 编年史/摘要钩子
# ============================================================

CHAPTER_WRITER_SYSTEM_PROMPT = """你是一位顶尖网文作者，正在为番茄小说平台连载一部作品。

写作铁律：
1. 严格按【本章章纲】执行：核心冲突、爽点、断章钩子一个都不能丢
2. 严格遵守【骨架约束】：力量体系与硬限制不能崩、主角红线（绝不做的事）不能破、行为要符合人设锚点
3. 【近章剧情】是已经发生的事，不能矛盾、不能重复交代
4. 【既定设定】中的事实（身份/关系/境界/地名）必须保持一致
5. 开篇直接进场景，禁止总结式开场（"上回说到"、"且说"都禁止）
6. 字数硬性要求：以章纲标注的【目标字数】为准（默认 3200 字），允许上下浮动 10%；不足下限视为未完成。段落自然，对话推动剧情，叙述与描写交替
7. 结尾必须落在断章钩子上，戛然而止，让读者忍不住点下一章
8. 输出正文本身，不要章节号、不要标题、不要任何解释性文字

文风铁律（参考职业写手的反AI味守则）：
- 禁止翻译腔、禁止AI味：不用"仿佛在诉说着什么"“空气中弥漫着”“不禁”这类空洞套话
- 禁止降智推进：反派和配角不犯蠢，冲突靠利益与信息差推动
- 多用具体名词和动作，少用形容词堆叠；对话要有口语的毛边，不要人人腔调相同
- 像一个老练的网文作者在码字，而不是AI在完成任务"""


class WriteChapterRequest(BaseModel):
    user_hint: str = ""
    regenerate: bool = False  # True = 重写最新一章（旧稿在成功后被替换）
    fast: bool = False  # True = 关闭思考快速成稿（约1分钟）；默认精细模式（思考充分，约4-5分钟）


async def _load_chronicle_digest(db, project_id: str) -> str:
    row = await fetch_one(db, "SELECT timeline, key_events, unresolved_threads FROM chronicle WHERE project_id = ?", (project_id,))
    if not row:
        return ""
    parts = []
    for col, label in (("timeline", "时间线"), ("key_events", "已发生大事"), ("unresolved_threads", "未解决的悬念")):
        try:
            data = json.loads(row[col]) if row[col] else []
        except (TypeError, ValueError):
            data = []
        if data:
            items = data[:12] if isinstance(data, list) else [data]
            lines = []
            for it in items:
                if isinstance(it, dict):
                    lines.append(f"- {it.get('time', '')} {it.get('event', '')}".strip())
                else:
                    lines.append(f"- {it}")
            parts.append(f"### {label}\n" + "\n".join(lines))
    return "\n\n".join(parts)


@router.post("/projects/{project_id}/chapters/write-stream")
async def write_chapter_stream(project_id: str, body: WriteChapterRequest):
    """一键写下一章。NDJSON 流：{"phase":...} → {"content":...}* → {"done":..., item_id}"""
    proj_exists = await fetch_one(await get_db(), "SELECT id FROM projects WHERE id = ?", (project_id,))
    if not proj_exists:
        raise HTTPException(status_code=404, detail="Project not found")
    return StreamingResponse(
        _write_chapter_generator(project_id, body.user_hint, body.regenerate, body.fast),
        media_type="application/x-ndjson",
    )


# 写作进度登记：project_id -> {"chapter": N, "title": str, "since": ts}
_writing_progress: dict[str, dict] = {}


async def _write_chapter_generator(project_id: str, user_hint: str, regenerate: bool, fast: bool = False):
    import time as _time
    db = await get_db()

    def emit(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False) + "\n"

    skeleton_rows = await fetch_all(
        db,
        f"""SELECT item_type, title, content, metadata FROM workspace_items
            WHERE project_id = ? AND item_type IN ({','.join('?' * len(SKELETON_TYPES))})
                  AND status IN ('finalized', 'locked')""",
        (project_id, *SKELETON_TYPES),
    )
    if not skeleton_rows:
        yield emit({"error": "骨架尚未建立，请先完成点位创作"})
        return

    chapter_number = await _get_next_chapter_number(db, project_id)
    old_chapter_id = None
    if regenerate and chapter_number > 1:
        chapter_number -= 1
        old = await fetch_one(
            db,
            """SELECT id FROM workspace_items WHERE project_id = ? AND item_type = 'chapter'
               AND chapter_number = ?""",
            (project_id, chapter_number),
        )
        old_chapter_id = old["id"] if old else None

    # --- 1. 章纲：没有就生成，草稿则直接定稿（写作流里章纲即确认） ---
    plan_row = await fetch_one(
        db,
        """SELECT id, title, content, metadata, status FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter_plan' AND chapter_number = ?""",
        (project_id, chapter_number),
    )
    if plan_row:
        plan_content = plan_row["content"] or ""
        plan_meta = parse_meta(plan_row["metadata"])
        if plan_row["status"] == "draft":
            await db.execute("UPDATE workspace_items SET status = 'finalized' WHERE id = ?", (plan_row["id"],))
            await db.commit()
    else:
        yield emit({"phase": "plan", "message": f"正在生成第{chapter_number}章章纲…"})
        try:
            plan = await generate_chapter_plan(
                chapter_number=chapter_number,
                skeleton_context=_format_skeleton_for_plan(skeleton_rows),
                recent_summary=await _load_recent_chapter_summary(db, project_id),
                pending_foreshadows=await _load_pending_foreshadows(db, project_id, chapter_number),
                user_hint=user_hint,
            )
        except Exception as e:
            logger.error("write-stream plan failed: %s", e)
            yield emit({"error": f"章纲生成失败: {str(e)[:100]}"})
            return
        plan_content, plan_meta = format_chapter_plan_markdown(plan, chapter_number)
        item_id = str(uuid.uuid4())
        sort_order = await next_sort_order(db, project_id)
        await db.execute(
            """INSERT INTO workspace_items
               (id, project_id, item_type, status, title, content, metadata, chapter_number, sort_order)
               VALUES (?, ?, 'chapter_plan', 'finalized', ?, ?, ?, ?, ?)""",
            (item_id, project_id, plan_meta.get("chapter_title", f"第{chapter_number}章"),
             plan_content, json.dumps(plan_meta, ensure_ascii=False), chapter_number, sort_order),
        )
        await db.commit()

    chapter_title = plan_meta.get("chapter_title", f"第{chapter_number}章")
    _writing_progress[project_id] = {"chapter": chapter_number, "title": chapter_title,
                                     "since": _time.time(), "fast": fast}
    yield emit({"phase": "writing", "chapter_number": chapter_number, "chapter_title": chapter_title,
                "plan": plan_content})

    # --- 2. 组装执笔上下文 ---
    from backend.services.kg import build_kg_injection
    kg_digest = await build_kg_injection(project_id, scene="write_chapter", chapter=chapter_number)
    chronicle_digest = await _load_chronicle_digest(db, project_id)
    recent_summary = await _load_recent_chapter_summary(db, project_id)

    context_blocks = [
        "## 骨架约束\n" + _format_skeleton_for_plan(skeleton_rows),
        f"## 本章章纲（第{chapter_number}章：{chapter_title}）\n{plan_content}",
    ]
    if recent_summary:
        context_blocks.append("## 近章剧情（已发生，勿矛盾勿重复）\n" + recent_summary)
    if kg_digest:
        context_blocks.append("## 既定设定（知识图谱）\n" + kg_digest)
    if chronicle_digest:
        context_blocks.append("## 编年史\n" + chronicle_digest)
    hint_block = f"\n\n## 作者对本章的额外要求\n{user_hint}" if user_hint else ""

    messages = [{
        "role": "user",
        "content": "请依据以上全部约束，写出本章正文。" + hint_block,
    }]

    # --- 3. 流式执笔（网关攒包下思考可能吃光 token 导致正文为空 → 自动重试） ---
    full_text = ""
    for attempt in range(3):
        try:
            async for kind, chunk in chat_stream(
                messages,
                system_prompt=CHAPTER_WRITER_SYSTEM_PROMPT + "\n\n" + "\n\n".join(context_blocks),
                temperature=1.0,
                disable_thinking=fast,  # fast=快速模式关思考；默认精细模式（上限32k后思考不再耗尽）
            ):
                if kind == "reasoning":
                    # 思考流实时转发：等待期可见构思过程，也避免前端空闲误判
                    yield emit({"thinking": chunk})
                    continue
                full_text += chunk
                yield emit({"content": chunk})
            if full_text.strip():
                break
        except LLMError as e:
            if full_text.strip():
                await _save_chapter(db, project_id, chapter_number, chapter_title, full_text + "\n\n[本章生成中断]", "draft")
                yield emit({"error": f"生成失败: {e}"})
                return
            if attempt == 2:
                yield emit({"error": f"生成失败: {e}"})
                return
        min_words = int(plan_meta.get("estimated_words") or 3200) * 85 // 100
        too_short = 0 < len(full_text.strip()) < min_words
        if (not full_text.strip() or too_short) and attempt < 2:
            why = f"正文为空，重试第 {attempt + 1}/2 次…" if not full_text.strip() else (
                f"字数不足（{len(full_text.strip())}/{min_words} 下限），重写第 {attempt + 1}/2 次…")
            full_text = ""
            yield emit({"phase": "writing", "chapter_number": chapter_number, "chapter_title": chapter_title, "message": why})

    if not full_text.strip():
        yield emit({"error": "多次重试后模型仍未返回正文，请稍后再试"})
        return

    # --- 4. 存档 + 钩子（编年史/摘要，后台异步） ---
    from backend.api.workspace import _spawn_bg, _trigger_chronicle_update, _generate_chapter_summary
    item_id = await _save_chapter(db, project_id, chapter_number, chapter_title, full_text, "finalized")
    if old_chapter_id and old_chapter_id != item_id:
        await db.execute("DELETE FROM workspace_items WHERE id = ?", (old_chapter_id,))
        await db.commit()
    _spawn_bg(_trigger_chronicle_update(project_id, chapter_title, full_text))
    _spawn_bg(_generate_chapter_summary(item_id, chapter_title, full_text))
    from backend.services.story_web import summarize_chapter as _sw_summarize
    _spawn_bg(_sw_summarize(item_id, chapter_title, full_text))

    _writing_progress.pop(project_id, None)
    yield emit({"done": True, "item_id": item_id, "chapter_number": chapter_number,
                "chapter_title": chapter_title, "word_count": len(full_text)})


async def _save_chapter(db, project_id: str, chapter_number: int, title: str,
                        content: str, status: str) -> str:
    item_id = str(uuid.uuid4())
    sort_order = await next_sort_order(db, project_id)
    await db.execute(
        """INSERT INTO workspace_items
           (id, project_id, item_type, status, title, content, metadata, chapter_number, sort_order)
           VALUES (?, ?, 'chapter', ?, ?, ?, ?, ?, ?)""",
        (item_id, project_id, status, title, content,
         json.dumps({"word_count": len(content)}, ensure_ascii=False), chapter_number, sort_order),
    )
    await db.execute("UPDATE projects SET updated_at = datetime('now') WHERE id = ?", (project_id,))
    await db.commit()
    return item_id


@router.get("/projects/{project_id}/writing/status")
async def writing_status(project_id: str):
    """写作进度：是否在写、当前章、章节总数与总字数（供界面实时显示）。"""
    import time as _time
    db = await get_db()
    row = await fetch_one(
        db,
        """SELECT COUNT(*) n, COALESCE(SUM(LENGTH(content)), 0) words,
                  MAX(chapter_number) mx FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter'""",
        (project_id,),
    )
    prog = _writing_progress.get(project_id)
    in_progress = bool(prog and _time.time() - prog["since"] < 900)  # 15分钟无更新视为过期
    return {
        "in_progress": in_progress,
        "current_chapter": (prog or {}).get("chapter"),
        "current_title": (prog or {}).get("title"),
        "fast": (prog or {}).get("fast", False),
        "chapters": row["n"],
        "max_chapter": row["mx"],
        "total_words": row["words"],
    }


@router.get("/projects/{project_id}/story-web")
async def get_story_web(project_id: str):
    """章节脉络网：章节轴（含概要/类型）+ 人物线/伏笔线交织。"""
    from backend.services.story_web import build_story_web
    return await build_story_web(project_id)


class BackfillBody(BaseModel):
    limit: int = 3


@router.post("/projects/{project_id}/story-web/backfill")
async def backfill_story_web(project_id: str, body: BackfillBody):
    """为缺脉络数据的章节批量补生成（每调一次处理 limit 章，循环到 remaining=0）。"""
    from backend.services.story_web import backfill as _backfill
    return await _backfill(project_id, max(1, min(body.limit, 5)))
