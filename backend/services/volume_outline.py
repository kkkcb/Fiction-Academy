"""卷纲：每一卷写什么（结构化、可生成、写作时注入章纲上下文）。"""
import json
import logging
import uuid

from backend.agents.base import chat_json
from backend.database import get_db, fetch_one

logger = logging.getLogger(__name__)

VOLUME_PROMPT = """你是资深网文编辑。基于整本书的骨架，产出每一卷的卷纲（网文标准 40 章/卷 的分卷规划）。

要求：
- 卷数 3-5 卷为宜，每卷约 40 章（可按总纲调整）
- 每卷包含：卷名（有钩子感）、主题定位（这卷写什么）、起止章、核心冲突、关键节点（4-6 个，按顺序）、本卷高潮、收束/悬念（引下卷）
- 严格遵守骨架约束（倒推因果链的终点、人物红线、力量体系），各卷共同指向全书结局

输出 JSON：
{"volumes": [
  {"vol": 1, "name": "卷名", "chapters": "1-40", "premise": "本卷主题定位（30字内）",
   "core_conflict": "核心冲突", "key_nodes": ["节点1", "..."], "climax": "本卷高潮",
   "hook_to_next": "收束与悬念"}
] , "total_chapters": 160}
只返回 JSON。"""


async def generate_volume_outline(project_id: str) -> dict:
    """从骨架（大纲/倒推/故事核）生成结构化卷纲并落库。"""
    db = await get_db()
    from backend.database import fetch_all
    from backend.api.chapter_writing import _format_skeleton_for_plan, SKELETON_TYPES

    rows = await fetch_all(
        db,
        f"""SELECT item_type, title, content, metadata FROM workspace_items
            WHERE project_id = ? AND item_type IN ({','.join('?' * len(SKELETON_TYPES))})
              AND status IN ('finalized', 'locked')""",
        (project_id, *SKELETON_TYPES),
    )
    if not rows:
        raise ValueError("骨架尚未建立，无法生成卷纲")

    skeleton = _format_skeleton_for_plan(rows)
    result = await chat_json(
        messages=[{"role": "user", "content": "骨架约束如下，请产出全书卷纲：\n\n" + skeleton}],
        system_prompt=VOLUME_PROMPT,
        temperature=0.7,
    )
    volumes = result.get("volumes") or []
    if not isinstance(volumes, list) or not volumes:
        raise ValueError("卷纲生成结果为空")

    # 落库：单条 volume_outline，结构存 metadata
    content_lines = []
    for v in volumes:
        nodes = " → ".join(v.get("key_nodes") or [])
        content_lines.append(
            f"# 第{v.get('vol')}卷《{v.get('name', '')}》（{v.get('chapters', '')}）\n"
            f"- 主题：{v.get('premise', '')}\n- 核心冲突：{v.get('core_conflict', '')}\n"
            f"- 关键节点：{nodes}\n- 本卷高潮：{v.get('climax', '')}\n- 收束/悬念：{v.get('hook_to_next', '')}"
        )
    content = "\n\n".join(content_lines)
    meta = {"volumes": volumes, "total_chapters": result.get("total_chapters")}

    existing = await fetch_one(
        db, "SELECT id FROM workspace_items WHERE project_id = ? AND item_type = 'volume_outline'", (project_id,))
    if existing:
        await db.execute(
            "UPDATE workspace_items SET content = ?, metadata = ?, status = 'finalized', updated_at = datetime('now') WHERE id = ?",
            (content, json.dumps(meta, ensure_ascii=False), existing["id"]),
        )
        item_id = existing["id"]
    else:
        from backend.services.repo import next_sort_order
        item_id = str(uuid.uuid4())
        sort_order = await next_sort_order(db, project_id)
        await db.execute(
            """INSERT INTO workspace_items
               (id, project_id, item_type, status, title, content, metadata, sort_order)
               VALUES (?, ?, 'volume_outline', 'finalized', '卷纲', ?, ?, ?)""",
            (item_id, project_id, content, json.dumps(meta, ensure_ascii=False), sort_order),
        )
    await db.commit()
    return {"id": item_id, "volumes": volumes, "total_chapters": result.get("total_chapters")}


def _parse_range(chapters: str) -> tuple[int, int]:
    import re
    m = re.search(r"(\d+)\s*-\s*(\d+)", chapters or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


async def get_volume_outline(project_id: str) -> dict:
    db = await get_db()
    row = await fetch_one(
        db, "SELECT content, metadata FROM workspace_items WHERE project_id = ? AND item_type = 'volume_outline'",
        (project_id,))
    if not row:
        return {"exists": False, "volumes": []}
    try:
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
    except (TypeError, ValueError):
        meta = {}
    return {"exists": True, "content": row["content"], "volumes": meta.get("volumes") or [],
            "total_chapters": meta.get("total_chapters")}


async def volume_context_for_chapter(project_id: str, chapter_number: int) -> str:
    """写章时注入的本卷卷纲摘要（含前后卷衔接提示）。"""
    data = await get_volume_outline(project_id)
    vols = data.get("volumes") or []
    if not vols:
        return ""
    cur = None
    prev = None
    nxt = None
    for i, v in enumerate(vols):
        lo, hi = _parse_range(v.get("chapters", ""))
        if lo <= chapter_number <= hi:
            cur = v
            prev = vols[i - 1] if i > 0 else None
            nxt = vols[i + 1] if i + 1 < len(vols) else None
            break
    if not cur:
        # 超出范围：给最后一卷
        cur = vols[-1]
    parts = [
        f"当前在第{cur.get('vol')}卷《{cur.get('name', '')}》（{cur.get('chapters', '')}）：{cur.get('premise', '')}",
        f"本卷核心冲突：{cur.get('core_conflict', '')}",
        f"本卷关键节点：{' → '.join(cur.get('key_nodes') or [])}",
        f"本卷高潮：{cur.get('climax', '')}（本章应为高潮蓄力，不可提前引爆）",
    ]
    if nxt:
        parts.append(f"下卷《{nxt.get('name', '')}》悬念方向：{nxt.get('premise', '')}——本章可埋引线，不展开")
    return "\n".join(parts)
