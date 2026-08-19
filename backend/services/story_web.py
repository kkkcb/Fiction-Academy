"""章节脉络网：每章结构化总结（剧情/人物/伏笔埋收），交织成书专属的网。

数据结构（存于 chapter 元数据 web 字段）：
  {"plot": "80-150字剧情概要", "characters": ["顾平安", ...],
   "foreshadows_setup": ["伏笔A"], "foreshadows_payoff": ["伏笔A"], "emotion": "压抑"}
"""
import json
import logging
import re

from backend.agents.base import chat_json
from backend.database import get_db, fetch_all, fetch_one

logger = logging.getLogger(__name__)

WEB_PROMPT = """你是小说编辑。阅读章节内容，输出结构化总结 JSON：
{{
  "plot": "剧情概要（80-150字，说清本章谁做了什么、结果如何）",
  "characters": ["本章出场的重要人物名（3-6个，用文中出现的名字）"],
  "foreshadows_setup": ["本章埋下的伏笔（短句概括，如'老槐树下的铁盒'；无则空数组）"],
  "foreshadows_payoff": ["本章回收/呼应的前文伏笔（用与埋设时相近的说法；无则空数组）"],
  "emotion": "本章情绪基调（一个词：如 压抑/松弛/燃/虐/暖）"
}}
只依据章节内容，不要编造。只返回 JSON。"""


async def summarize_chapter(item_id: str, chapter_title: str, chapter_content: str) -> bool:
    """生成单章结构化总结并入元数据。返回是否成功。"""
    text = (chapter_content or "").strip()
    if len(text) < 50:
        return False
    try:
        data = await chat_json(
            messages=[{"role": "user", "content": f"章节标题：{chapter_title}\n\n章节内容：\n{text[:9000]}"}],
            system_prompt=WEB_PROMPT,
            temperature=0.3,
        )
    except Exception as e:
        logger.warning("[story-web] summarize %s failed: %s", item_id, e)
        return False
    plot = (data.get("plot") or "").strip()
    if not plot:
        return False
    web = {
        "plot": plot[:300],
        "characters": [str(c).strip() for c in (data.get("characters") or []) if str(c).strip()][:8],
        "foreshadows_setup": [str(f).strip() for f in (data.get("foreshadows_setup") or []) if str(f).strip()][:6],
        "foreshadows_payoff": [str(f).strip() for f in (data.get("foreshadows_payoff") or []) if str(f).strip()][:6],
        "emotion": (data.get("emotion") or "").strip()[:8],
    }
    db = await get_db()
    row = await fetch_one(db, "SELECT metadata FROM workspace_items WHERE id = ?", (item_id,))
    if not row:
        return False
    meta = json.loads(row["metadata"]) if row["metadata"] else {}
    meta["web"] = web
    if not meta.get("summary"):
        meta["summary"] = web["plot"]
    await db.execute(
        "UPDATE workspace_items SET metadata = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(meta, ensure_ascii=False), item_id),
    )
    await db.commit()
    logger.info("[story-web] summarized chapter item %s", item_id)
    return True


async def backfill(project_id: str, limit: int = 3) -> dict:
    """为缺少脉络数据的章节补生成（每次最多 limit 章，前端循环调用直到 remaining=0）。"""
    db = await get_db()
    rows = await fetch_all(
        db,
        """SELECT id, title, content, metadata FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter' AND status IN ('finalized', 'locked')
           ORDER BY chapter_number""",
        (project_id,),
    )
    todo = []
    for r in rows:
        try:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
        except (TypeError, ValueError):
            meta = {}
        if "web" not in meta:
            todo.append(r)
    done = 0
    for r in todo[:limit]:
        if await summarize_chapter(r["id"], r["title"] or "", r["content"] or ""):
            done += 1
    return {"updated": done, "remaining": max(len(todo) - done, 0)}


def _norm(text: str) -> str:
    return re.sub(r"[\s，。！？、：；'\"“”‘’]", "", text)[:12]


async def build_story_web(project_id: str) -> dict:
    """组装脉络网：章节轴 + 人物线/伏笔线（服务端纯组装，无 LLM）。"""
    db = await get_db()
    rows = await fetch_all(
        db,
        """SELECT chapter_number, title, content, metadata FROM workspace_items
           WHERE project_id = ? AND item_type = 'chapter' AND status IN ('finalized', 'locked')
           ORDER BY chapter_number""",
        (project_id,),
    )
    chapters = []
    char_map: dict[str, list[int]] = {}
    fscadow_threads: list[dict] = []  # {name, norm, setup_ch, chapters:[]}

    for r in rows:
        try:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
        except (TypeError, ValueError):
            meta = {}
        web = meta.get("web") or {}
        plan_meta = {}
        chapters.append({
            "chapter": r["chapter_number"],
            "title": r["title"] or "",
            "words": len(r["content"] or ""),
            "types": meta.get("chapter_types") or [],
            "plot": web.get("plot") or meta.get("summary") or "",
            "emotion": web.get("emotion") or "",
        })
        for name in web.get("characters") or []:
            char_map.setdefault(name, []).append(r["chapter_number"])
        for setup in web.get("foreshadows_setup") or []:
            fscadow_threads.append({"name": setup, "norm": _norm(setup),
                                    "setup_ch": r["chapter_number"], "chapters": [r["chapter_number"]]})
        for payoff in web.get("foreshadows_payoff") or []:
            pn = _norm(payoff)
            hit = next((t for t in fscadow_threads if t["norm"] == pn or (pn and pn in t["norm"]) or (t["norm"] and t["norm"] in pn)), None)
            if hit:
                hit["chapters"].append(r["chapter_number"])
                hit.setdefault("payoff_chs", []).append(r["chapter_number"])
            else:
                fscadow_threads.append({"name": payoff, "norm": pn, "setup_ch": None,
                                        "chapters": [r["chapter_number"]],
                                        "payoff_chs": [r["chapter_number"]]})

    # 人物线按出现次数排序，保留主要人物；伏笔线只保留跨章或有回收的
    threads = [{"kind": "character", "name": n, "chapters": chs}
               for n, chs in sorted(char_map.items(), key=lambda kv: -len(kv[1]))[:12]]
    threads += [{"kind": "foreshadow", "name": t["name"],
                 "setup_ch": t["setup_ch"], "payoff_chs": t.get("payoff_chs", []),
                 "chapters": sorted(set(t["chapters"]))}
                for t in fscadow_threads if len(set(t["chapters"])) > 1 or t.get("payoff_chs")]

    missing = sum(1 for c in chapters if not c["plot"])
    return {"chapters": chapters, "threads": threads, "missing_web": missing}
