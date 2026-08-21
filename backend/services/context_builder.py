"""统一上下文组装管道。

聊天注入 / Goal 执行 / 章纲审校共用同一批数据加载与拼装逻辑，
消除此前三套平行体系（wiki 页面、metadata 字段、goal 自拼摘要）的漂移：
同一份设定在所有场景下以同一形态进入 prompt。

预算策略：每个 Provider 自带内部预算；管道最后按 priority 从低到高
整段裁剪，直到总 token 不超限。priority=1 的段落（守则/点位/章纲）永不裁剪。
"""
import json
import logging
from dataclasses import dataclass

from backend.database import get_db, fetch_all, fetch_one
from backend.services import repo
from backend.services.wiki import (
    SceneType,
    detect_scene,
    parse_wiki_pages,
    query_wiki,
    apply_token_budget,
    assemble_context,
    estimate_tokens,
)

logger = logging.getLogger(__name__)

MAX_TOTAL_TOKENS = 8000
KG_MAX_TOKENS = 2000
SETTINGS_MAX_TOKENS = 4000
PREV_CHAPTER_BODY_LIMIT = 2000
CHAPTR_RAW_LIMIT = 3000


@dataclass
class ContextRequest:
    project_id: str
    scene: SceneType = "casual"
    user_content: str = ""
    point: str = ""
    chapter: int | None = None


@dataclass
class Section:
    tag: str
    content: str
    priority: int = 5  # 1 = 最高，预算不足时最后被裁剪


# ---------------------------------------------------------------------------
# 数据加载（各场景共用）

async def load_chronicle_text(db, project_id: str) -> str:
    row = await fetch_one(
        db,
        "SELECT raw_text, timeline, key_events, unresolved_threads FROM chronicle WHERE project_id = ?",
        (project_id,),
    )
    if not row:
        return ""
    raw = row.get("raw_text", "")
    if raw:
        return raw
    try:
        timeline = json.loads(row.get("timeline") or "[]")
        events = json.loads(row.get("key_events") or "[]")
        threads = json.loads(row.get("unresolved_threads") or "[]")
    except (json.JSONDecodeError, TypeError):
        return ""
    lines = []
    for x in timeline[:20]:
        if isinstance(x, dict):
            lines.append(f"- [{x.get('time', '')}] {x.get('event', '')}")
    for x in events[:10]:
        lines.append(f"- 关键事件: {x}" if not isinstance(x, dict) else f"- 关键事件: {x.get('event', x.get('title', ''))}")
    if threads:
        lines.append("- 未回收伏笔:")
        for x in threads[:10]:
            lines.append(f"  · {x}" if not isinstance(x, dict) else f"  · {x.get('content', x.get('hint', ''))}")
    return "\n".join(lines)


async def load_prev_chapters(db, project_id: str, limit: int = 5) -> list[dict]:
    rows = await fetch_all(
        db,
        """SELECT item_type, title, content, metadata, chapter_number FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter'
             AND status IN ('finalized', 'locked')
           ORDER BY chapter_number DESC LIMIT ?""",
        (project_id, limit),
    )
    pages = []
    for r in rows:
        title = r["title"] or f"第{r.get('chapter_number', '?')}章"
        content = r["content"] or ""
        meta = repo.parse_meta(r.get("metadata"))
        summary = (meta.get("summary") or "").strip()
        if summary:
            content = summary
            prefix = f"### {title}（前情摘要）\n"
        elif len(content) > CHAPTR_RAW_LIMIT:
            content = content[:CHAPTR_RAW_LIMIT] + "\n...(后续内容省略)"
            prefix = f"### {title}\n"
        else:
            prefix = f"### {title}\n"
        pages.append({"type": "chapter", "title": title,
                      "content": prefix + content, "keywords": set(), "score": 0})
    return pages


async def load_chapter_plan(db, project_id: str) -> dict | None:
    row = await fetch_one(
        db,
        """SELECT content, metadata, chapter_number FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter_plan'
             AND status IN ('finalized', 'locked')
           ORDER BY chapter_number DESC LIMIT 1""",
        (project_id,),
    )
    if not row:
        return None
    return {
        "content": row["content"],
        "metadata": repo.parse_meta(row.get("metadata")),
        "chapter_number": row.get("chapter_number"),
    }


# ---------------------------------------------------------------------------
# Provider：每个返回一个 Section（或 None）

async def rules_section(req: ContextRequest) -> Section | None:
    from backend.services.rules import get_rules_injection
    inject = await get_rules_injection(req.project_id)
    return Section(tag="_rules", content=inject, priority=1) if inject else None


async def point_guide_section(req: ContextRequest) -> Section | None:
    from backend.agents.guide_prompts import POINT_CONFIGS  # 延迟导入避免循环依赖
    from backend.agents.guide import POINT_LABELS
    if not req.point or req.point not in POINT_CONFIGS:
        return None
    config = POINT_CONFIGS[req.point]
    label = POINT_LABELS.get(req.point, req.point)
    fields_text = "\n".join(f"- {k}: {v}" for k, v in config.get("fields", {}).items())
    content = f"""<point_guide priority="critical">
你正在引导作者确定【{label}】。这是一个专门的点位对话。

点位说明：
{config.get("intro", "")}

本轮需要确定的字段：
{fields_text}

请在对话中自然地引导作者逐一确定这些字段。基于已确定的背景做个性化引导。
</point_guide>
"""
    return Section(tag="_point_guide", content=content, priority=1)


async def chapter_plan_section(req: ContextRequest) -> Section | None:
    if req.scene not in ("write_chapter", "edit_chapter"):
        return None
    db = await get_db()
    plan = await load_chapter_plan(db, req.project_id)
    if not plan:
        return None
    num = plan["chapter_number"] or "?"
    if isinstance(plan["chapter_number"], int):
        req.chapter = plan["chapter_number"]
    content = (
        f"\n\n<chapter_plan priority=\"critical\">\n"
        f"你正在写【第{num}章】，必须严格遵循以下章纲：\n"
        f"{plan['content']}\n"
        f"</chapter_plan>\n"
        f"注意：核心冲突、爽点设计、断章钩子必须按章纲执行，不要即兴偏离。\n"
    )
    return Section(tag="_chapter_plan", content=content, priority=1)


async def kg_section(req: ContextRequest) -> Section | None:
    from backend.services.kg import build_kg_injection
    inject = await build_kg_injection(
        req.project_id, scene=req.scene, chapter=req.chapter,
        max_tokens=KG_MAX_TOKENS,
    )
    return Section(tag="_kg", content=inject, priority=2) if inject else None


async def settings_section(req: ContextRequest) -> Section | None:
    if req.point == "__studio__":
        return await _studio_skeleton_digest(req)
    db = await get_db()
    rows = await fetch_all(
        db,
        """SELECT item_type, title, content FROM workspace_items
           WHERE project_id = ? AND item_type IN (
               'story_core', 'world_setting', 'character_setting',
               'outline', 'outline_reverse', 'foreshadow'
           ) AND status IN ('locked', 'finalized')
           ORDER BY sort_order, created_at""",
        (req.project_id,),
    )
    if not rows:
        return None
    pages = []
    for r in rows:
        pages.extend(parse_wiki_pages(r["content"], r["item_type"], r["title"] or ""))
    selected = query_wiki(pages, req.user_content, req.scene, max_pages=10)
    selected, _, _ = apply_token_budget(selected, [], [], max_tokens=SETTINGS_MAX_TOKENS)
    content = assemble_context(selected, [], [])
    return Section(tag="_settings", content=content, priority=3) if content else None


async def chronicle_section(req: ContextRequest) -> Section | None:
    db = await get_db()
    text = await load_chronicle_text(db, req.project_id)
    if not text:
        return None
    return Section(tag="_chronicle", content=f"<编年史>\n{text}\n</编年史>", priority=3)


async def prev_chapters_section(req: ContextRequest) -> Section | None:
    if req.scene not in ("write_chapter", "edit_chapter"):
        return None
    db = await get_db()
    pages = await load_prev_chapters(db, req.project_id)
    if not pages:
        return None
    _, pages, _ = apply_token_budget([], pages, [])
    body = "\n\n".join(p["content"][:PREV_CHAPTER_BODY_LIMIT] for p in pages)
    content = f"<previous_chapters>\n{body}\n</previous_chapters>"
    return Section(tag="_prev_chapters", content=content, priority=4)


# ---------------------------------------------------------------------------
# 组装

async def build_chat_context(req: ContextRequest) -> str:
    """聊天场景的系统提示词增量（拼在 SYSTEM_PROMPT / 助理 prompt 之后）。"""
    if not req.scene or req.scene == "casual":
        req.scene = detect_scene(req.user_content)

    providers = [
        rules_section, point_guide_section, chapter_plan_section,
        kg_section, settings_section, chronicle_section, prev_chapters_section,
    ]
    sections = []
    for provider in providers:
        try:
            sec = await provider(req)
        except Exception as e:  # 单个 Provider 失败不拖垮整个上下文
            logger.warning("[context] provider %s failed: %s", provider.__name__, e)
            continue
        if sec and sec.content.strip():
            sections.append(sec)

    # KG 自带预算；settings/prev_chapters 在各自内部已收敛。最后整体兜底。
    total = sum(estimate_tokens(s.content) for s in sections)
    if total > MAX_TOTAL_TOKENS:
        for sec in sorted(sections, key=lambda s: -s.priority):
            if total <= MAX_TOTAL_TOKENS:
                break
            if sec.priority == 1:
                continue
            logger.info("[context] dropping section %s (%d tokens) for budget", sec.tag, estimate_tokens(sec.content))
            sections.remove(sec)
            total -= estimate_tokens(sec.content)

    body = "\n".join(s.content for s in sections)
    logger.info(
        "[context] project=%s scene=%s sections=%s tokens≈%d",
        req.project_id, req.scene, [s.tag for s in sections], total,
    )
    return body


async def build_workspace_digest(project_id: str, per_item_limit: int = 800,
                                 include_drafts: bool = True) -> str:
    """工作台全量摘要（Goal 模式用）：所有条目的截断视图。"""
    db = await get_db()
    rows = await fetch_all(
        db,
        "SELECT item_type, title, content, status FROM workspace_items WHERE project_id = ? ORDER BY sort_order, created_at",
        (project_id,),
    )
    parts = []
    for r in rows:
        if not include_drafts and r["status"] == "draft":
            continue
        status_tag = f"[{r['status']}]" if r["status"] != "draft" else ""
        title = r["title"] or r["item_type"]
        content = (r["content"] or "")[:per_item_limit]
        parts.append(f"【{title}】{status_tag}\n{content}")
    return "\n\n".join(parts) if parts else "（项目尚无工作台条目）"


async def _studio_skeleton_digest(req: ContextRequest) -> Section | None:
    """studio 对话的骨架摘要：只给已定稿内容的精简版，不用引导性格式。"""
    db = await get_db()
    from backend.agents.guide import POINT_LABELS
    rows = await fetch_all(
        db,
        "SELECT item_type, content FROM workspace_items WHERE project_id = ? AND item_type IN ('story_core','world_setting','character_setting','outline','outline_reverse','foreshadow') AND status IN ('locked','finalized') ORDER BY sort_order",
        (req.project_id,),
    )
    if not rows:
        return None
    parts = []
    for r in rows:
        label = POINT_LABELS.get(r["item_type"], r["item_type"])
        parts.append("【" + label + "】（已定稿）\n" + (r["content"] or "")[:500])
    content = "## 已确定的设定（以下是事实，不是引导）\n\n" + "\n\n".join(parts)
    return Section(tag="_settings", content=content, priority=3)
