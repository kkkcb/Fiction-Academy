"""章纲 API —— 三段式写章的「备稿」环节。"""
import json
import uuid
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one
from backend.agents.chapter_plan import generate_chapter_plan, format_chapter_plan_markdown
from backend.agents.guide import POINT_LABELS
from backend.agents.reviewer import review_chapter, should_retry, build_revision_feedback

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

SKELETON_TYPES = ("story_core", "world_setting", "character_setting", "outline", "outline_reverse")


class ChapterPlanRequest(BaseModel):
    user_hint: str = ""
    regenerate: bool = False


def _format_skeleton_for_plan(rows: list[dict]) -> str:
    """把骨架点位格式化为章纲生成的约束摘要。"""
    parts = []
    for r in rows:
        label = POINT_LABELS.get(r["item_type"], r["item_type"])
        content = r.get("content", "") or ""
        meta = {}
        if r.get("metadata"):
            try:
                meta = json.loads(r["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass

        if r["item_type"] == "story_core":
            one_liner = meta.get("one_liner", "")
            trope = meta.get("trope", "")
            parts.append(f"### 故事核\n核心：{one_liner}\n套路：{trope}")
        elif r["item_type"] == "world_setting":
            power = meta.get("power_system", "")
            limit = meta.get("power_limit", "")
            golden = meta.get("golden_finger", "")
            parts.append(
                f"### 世界观\n力量体系：{power}\n硬限制：{limit}\n金手指：{golden}"
            )
        elif r["item_type"] == "character_setting":
            name = meta.get("name", "")
            desire = meta.get("core_desire", "")
            red_lines = meta.get("red_lines", [])
            red_text = "；".join(red_lines) if isinstance(red_lines, list) else str(red_lines)
            parts.append(f"### 主角\n姓名：{name}\n核心欲望：{desire}\n红线（绝不做）：{red_text}")
        elif r["item_type"] == "outline_reverse":
            endpoint = meta.get("endpoint_state", "")
            turns = meta.get("key_turning_points", [])
            turns_text = " → ".join(turns) if isinstance(turns, list) else str(turns)
            parts.append(f"### 倒推因果链\n终点：{endpoint}\n关键转折：{turns_text}")
        elif r["item_type"] == "outline":
            act1 = meta.get("act1", "")
            parts.append(f"### 正向大纲\n第一幕：{act1}")

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
        meta = {}
        if r.get("metadata"):
            try:
                meta = json.loads(r["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
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

    item_id = str(uuid.uuid4())
    sort_row = await fetch_one(
        db,
        "SELECT MAX(sort_order) as mx FROM workspace_items WHERE project_id = ?",
        (project_id,),
    )
    sort_order = (sort_row["mx"] or 0) + 1 if sort_row else 1

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
    meta = {}
    if row.get("metadata"):
        try:
            meta = json.loads(row["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass
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
    """加载审校所需的全部约束。"""
    plan_row = await fetch_one(
        db,
        """SELECT content, metadata FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter_plan' AND chapter_number = ?""",
        (project_id, chapter_number),
    )
    plan_meta = {}
    if plan_row and plan_row.get("metadata"):
        try:
            plan_meta = json.loads(plan_row["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass

    char_row = await fetch_one(
        db,
        """SELECT metadata FROM workspace_items
           WHERE project_id = ? AND item_type = 'character_setting'
                 AND status IN ('finalized', 'locked')
           ORDER BY sort_order LIMIT 1""",
        (project_id,),
    )
    char_meta = {}
    if char_row and char_row.get("metadata"):
        try:
            char_meta = json.loads(char_row["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass

    world_row = await fetch_one(
        db,
        """SELECT metadata FROM workspace_items
           WHERE project_id = ? AND item_type = 'world_setting'
                 AND status IN ('finalized', 'locked')""",
        (project_id,),
    )
    world_meta = {}
    if world_row and world_row.get("metadata"):
        try:
            world_meta = json.loads(world_row["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass

    outline_rev_row = await fetch_one(
        db,
        """SELECT metadata FROM workspace_items
           WHERE project_id = ? AND item_type = 'outline_reverse'
                 AND status IN ('finalized', 'locked')""",
        (project_id,),
    )
    outline_rev_meta = {}
    if outline_rev_row and outline_rev_row.get("metadata"):
        try:
            outline_rev_meta = json.loads(outline_rev_row["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass

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
