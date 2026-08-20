"""热点素材库：聚合热榜（抖音/微博/知乎）+ 收藏管理。

数据源默认走开源项目 60s API（github.com/vikiboss/60s）的公共实例，
可通过环境变量 HOT_API_BASE 指向自托管实例（Docker/Deno/CF Workers 均可）。
"""
import json
import time
import uuid
import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import HOT_API_BASE
from backend.database import get_db, fetch_all, fetch_one
from backend.agents.base import chat_json, chat_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

HOT_SOURCES = {
    "douyin": "抖音热点",
    "weibo": "微博热搜",
    "zhihu": "知乎热榜",
    "news60": "今日要闻",  # 60秒读懂世界：每条自带完整新闻内容
}

# 热榜缓存：源 → (过期时间戳, 数据)。TTL 10 分钟，规避公共实例限频（429）。
_HOT_CACHE: dict[str, tuple[float, list[dict]]] = {}
_HOT_TTL = 24 * 3600  # 一天一更：讨论区才是重点，热榜刷新太勤会烧掉公共实例配额（429）
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FictionAcademy/1.0"


class MaterialCreate(BaseModel):
    title: str
    source: str = ""
    url: str = ""
    hot: str = ""
    note: str = ""


async def _fetch_hot(source: str) -> list[dict]:
    """拉取单个热榜源并归一化为 [{title, hot, url, summary}]。"""
    # 知乎：官方开放平台 API 优先（真实摘要），未配置/失败则回退 60s
    if source == "zhihu":
        try:
            from backend.services.zhihu_api import fetch_hot as _zh_hot, ZhihuNotConfigured
            return await _zh_hot(30)
        except ZhihuNotConfigured:
            pass
        except Exception as e:
            logger.warning("[hot] zhihu official api failed, fallback 60s: %s", e)

    async with httpx.AsyncClient(timeout=15, trust_env=False,
                                 headers={"User-Agent": _UA}) as client:
        r = await client.get(f"{HOT_API_BASE}/{'60s' if source == 'news60' else source}")
        r.raise_for_status()
        body = r.json()

    if source == "news60":
        # 60秒读懂世界：news 列表每条就是一句完整新闻
        data = body.get("data") or {}
        news = data.get("news") or []
        return [{
            "title": (n if isinstance(n, str) else str(n.get("title") or ""))[:80],
            "hot": "",
            "url": data.get("link") or "",
            "summary": "",
        } for n in news if n][:20]

    items = []
    for it in body.get("data") or []:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        hot = it.get("hot_value") or it.get("hot_value_desc") or ""
        try:
            hot = f"{int(hot) / 10000:.0f}万热度" if isinstance(hot, (int, float)) else str(hot)
        except (ValueError, TypeError):
            hot = str(hot)
        # 知乎条目自带话题详情：截断做概要，完整版留给「看讨论」
        full_detail = (it.get("detail") or "").strip()
        summary = full_detail[:80]
        items.append({
            "title": title,
            "hot": hot,
            "url": it.get("link") or "",
            "summary": summary,
            "detail": full_detail[:600],
        })
    return items[:50]


@router.get("/hot")
async def get_hot(source: str = "douyin"):
    if source not in HOT_SOURCES:
        raise HTTPException(status_code=400, detail=f"不支持的热榜源：{source}")
    cached = _HOT_CACHE.get(source)
    fresh = cached and cached[0] > time.time()
    if fresh:
        return {"source": source, "label": HOT_SOURCES[source], "cached": True, "items": cached[1]}

    if cached:
        # 有旧缓存：立即返回旧数据，后台刷新（切页秒开，不阻塞在外网请求上）
        _spawn_refresh(source)
        return {"source": source, "label": HOT_SOURCES[source], "cached": True,
                "items": cached[1], "stale": True}

    try:
        items = await _fetch_hot(source)
    except Exception as e:
        logger.warning("[hot] fetch %s failed: %s", source, e)
        raise HTTPException(status_code=502, detail=f"热榜获取失败：{str(e)[:80]}")
    _store_hot(source, items)
    return {"source": source, "label": HOT_SOURCES[source], "cached": False, "items": items}


_refreshing: set[str] = set()


def _spawn_refresh(source: str) -> None:
    if source in _refreshing:
        return

    async def _do():
        try:
            _refreshing.add(source)
            items = await _fetch_hot(source)
            _store_hot(source, items)
            logger.info("[hot] refreshed %s (%d items)", source, len(items))
        except Exception as e:
            logger.warning("[hot] background refresh %s failed: %s", source, e)
        finally:
            _refreshing.discard(source)

    import asyncio
    task = asyncio.create_task(_do())
    _refresh_tasks.add(task)
    task.add_done_callback(_refresh_tasks.discard)


_refresh_tasks: set = set()


def _is_paraphrase(title: str, summary: str) -> bool:
    """复读判定：摘要的字符二元组几乎全部来自标题（≥0.8）→ 无增量信息。"""
    import re as _re
    strip = r"[\s，。！？、：；·,!?::~“”‘’]"
    t = _re.sub(strip, "", title)
    s = _re.sub(strip, "", summary)
    if len(s) < 6:
        return True
    if s in t:
        return True
    t_bigrams = {t[i:i + 2] for i in range(len(t) - 1)}
    s_bigrams = {s[i:i + 2] for i in range(len(s) - 1)}
    if not s_bigrams:
        return True
    return len(s_bigrams & t_bigrams) / len(s_bigrams) >= 0.65


SUMMARY_PROMPT = """你是资深新闻编辑。给每条热点标题写一句"补充信息"（35字内），目标是让不了解的人看懂这是什么事：
- 优先补充标题之外的背景：涉事主体是谁（公司/人物的身份和知名度）、事件的语境或意义
- 可以使用你确信的常识性背景（如"宇树科技"是机器人独角兽）；禁止编造标题与常识都无法支撑的具体数字、日期、人名
- 如果除了复述标题外没有任何可补充的，返回空字符串——宁缺毋滥，不要复读标题
输出 JSON：{"summaries": {"标题原文": "补充信息或空串", ...}}，输入列表里的每条标题都要有对应键。"""


async def _summarize_source(source: str, items: list[dict]) -> None:
    """后台为缺概要的条目批量生成一句话摘要（LLM，单源并发=1）。"""
    key = f"summ:{source}"
    if key in _refreshing:
        return
    _refreshing.add(key)
    try:
        targets = [it for it in items[:20] if not it.get("summary")]
        if not targets:
            return
        titles = [it["title"] for it in targets]
        result = await chat_json(
            messages=[{"role": "user", "content": "标题列表：" + json.dumps(titles, ensure_ascii=False)}],
            system_prompt=SUMMARY_PROMPT,
            temperature=0.3,
        )
        mapping = result.get("summaries") or {}
        if not isinstance(mapping, dict):
            return
        by_title = {it["title"]: it for it in items}
        for title, summ in mapping.items():
            it = by_title.get(title)
            text = str(summ or "").strip()
            if it and text and not _is_paraphrase(title, text):
                it["summary"] = text[:60]
        logger.info("[hot] summarized %s (%d/%d)", source, len(mapping), len(titles))
    except Exception as e:
        logger.warning("[hot] summarize %s failed: %s", source, e)
    finally:
        _refreshing.discard(key)


def _store_hot(source: str, items: list[dict]) -> None:
    """写入缓存并触发后台摘要生成。"""
    _HOT_CACHE[source] = (time.time() + _HOT_TTL, items)
    import asyncio
    task = asyncio.create_task(_summarize_source(source, items))
    _refresh_tasks.add(task)
    task.add_done_callback(_refresh_tasks.discard)


async def warm_hot_cache() -> None:
    """启动预热：把三个源都拉一遍，用户首次切到素材库时秒开。
    源之间错峰 8s——公共实例对连续请求限频（429）。"""
    import asyncio
    for i, source in enumerate(HOT_SOURCES):
        if i:
            await asyncio.sleep(8)
        if not _HOT_CACHE.get(source):
            try:
                items = await _fetch_hot(source)
                _store_hot(source, items)
                logger.info("[hot] warmed %s (%d items)", source, len(items))
            except Exception as e:
                logger.warning("[hot] warm %s failed: %s", source, e)


@router.post("/materials")
async def create_material(body: MaterialCreate):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    db = await get_db()
    dup = await fetch_one(
        db, "SELECT id FROM materials WHERE title = ? AND source = ?", (title, body.source))
    if dup:
        raise HTTPException(status_code=409, detail="已收藏过该素材")
    mid = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO materials (id, title, source, url, hot, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (mid, title, body.source, body.url, body.hot, body.note),
    )
    await db.commit()
    row = await fetch_one(db, "SELECT * FROM materials WHERE id = ?", (mid,))
    return row


@router.get("/materials")
async def list_materials():
    db = await get_db()
    return await fetch_all(db, "SELECT * FROM materials ORDER BY created_at DESC, rowid DESC LIMIT 200")


@router.delete("/materials/{material_id}")
async def delete_material(material_id: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT id FROM materials WHERE id = ?", (material_id,))
    if not row:
        raise HTTPException(status_code=404, detail="素材不存在")
    await db.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    await db.commit()
    return {"ok": True}


# ============================================================
# 看讨论：读取热点网页正文，概括大家在讨论什么
# ============================================================
_discuss_cache: dict[str, tuple[float, dict]] = {}
_DISCUSS_TTL = 1800


def _extract_page_text(html: str) -> str:
    """提取网页可读文本：优先 meta 摘要，否则去标签取正文。"""
    import re as _re
    for pattern in (
        r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
    ):
        m = _re.search(pattern, html)
        if m and len(m.group(1).strip()) >= 30:
            import html as _html
            return _html.unescape(m.group(1)).strip()[:2000]
    text = _re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=_re.S | _re.I)
    text = _re.sub(r"<[^>]+>", " ", text)
    import html as _html
    text = _html.unescape(text)
    return _re.sub(r"\s+", " ", text).strip()[:3000]


async def _weibo_discuss(keyword: str) -> dict:
    """微博讨论读取（双层回退，模式源自 weibo-rss / RSSHub）：
    1) 用户配置 WEIBO_COOKIE → m.weibo.cn 搜索 API 直读真实微博
    2) 用户自托管 RSSHub → /weibo/keyword 路由
    都没配 → 诚实失败（平台需登录）"""
    import re as _re
    from urllib.parse import quote as _quote
    from backend.config import WEIBO_COOKIE, RSSHUB_BASE

    posts: list[str] = []

    if WEIBO_COOKIE:
        try:
            cid = _quote(f"100103type=1&q={keyword}")
            async with httpx.AsyncClient(timeout=12, trust_env=False, headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Cookie": WEIBO_COOKIE,
            }) as client:
                r = await client.get(
                    f"https://m.weibo.cn/api/container/getIndex?containerid={cid}&page_type=searchall",
                    headers={"X-Requested-With": "XMLHttpRequest",
                             "Referer": f"https://m.weibo.cn/search?containerid={cid}"},
                )
                data = r.json()
            for card in data.get("data", {}).get("cards", []):
                mb = card.get("mblog")
                if mb:
                    text = _re.sub(r"<[^>]+>", "", mb.get("text", "")).strip()
                    if text:
                        posts.append(f"@{mb.get('user', {}).get('screen_name', '')}：{text[:180]}")
                if len(posts) >= 8:
                    break
        except Exception as e:
            logger.info("[hot/discuss] weibo cookie api failed: %s", e)

    if not posts and RSSHUB_BASE:
        try:
            async with httpx.AsyncClient(timeout=12, trust_env=False,
                                         headers={"User-Agent": _UA}) as client:
                r = await client.get(f"{RSSHUB_BASE}/weibo/keyword/{_quote(keyword)}")
                r.raise_for_status()
            import html as _html
            for m in _re.findall(r"<description><!\[CDATA\[(.*?)\]\]></description>", r.text, _re.S)[:8]:
                text = _re.sub(r"<[^>]+>", "", _html.unescape(m)).strip()
                if text:
                    posts.append(text[:180])
        except Exception as e:
            logger.info("[hot/discuss] rsshub failed: %s", e)

    if not posts:
        return {"ok": False, "reason": "js_or_login",
                "hint": "可选配置：.env.local 中设置 WEIBO_COOKIE（浏览器登录 m.weibo.cn 后复制 Cookie）或自托管 RSSHub 后设置 RSSHUB_BASE，即可读取真实微博讨论"}

    try:
        prompt = (
            f"热点标题：{keyword}\n\n以下是网友的相关微博：\n" + "\n".join(posts) +
            "\n\n用2-3句话概括网友们主要在讨论什么（核心观点/争议/情绪）。只依据内容，不要编造。"
        )
        summary = await chat_text(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是新闻编辑，擅长提炼网络讨论的核心。",
            temperature=0.3,
        )
    except Exception as e:
        logger.warning("[hot/discuss] weibo llm failed: %s", e)
        return {"ok": False, "reason": "llm_failed"}

    text = (summary or "").strip()[:500]
    if not text:
        return {"ok": False, "reason": "llm_failed"}
    return {"ok": True, "kind": "weibo_posts", "summary": text}


@router.get("/hot/discuss")
async def hot_discuss(url: str = "", title: str = "", source: str = ""):
    """读取热点链接页面并概括讨论内容。
    知乎走本地缓存的话题详情；能抓到正文的开源页用 LLM 概括；
    需登录/JS 渲染的平台诚实返回不可读。"""
    import time as _time

    # 知乎：官方API搜真实回答（赞同数排序+精选评论），LLM 概括讨论
    if source == "zhihu" and title:
        try:
            from backend.services.zhihu_api import search_answers as _zh_search, ZhihuNotConfigured
            answers = await _zh_search(title, 6)
            if answers:
                raw = "\n".join(
                    f"@{a['author']}（{a['votes']}赞）：{a['excerpt'][:200]}"
                    + ("" if not a["comments"] else " 评论区：" + "；".join(a["comments"][:1]))
                    for a in answers[:6])
                try:
                    prompt = (
                        f"热点标题：{title}\n\n以下是知乎上的真实回答摘录：\n{raw}\n\n"
                        "用2-3句话概括知乎网友的主要观点分歧与共识（谁在反对什么、什么被普遍认同）。只依据内容，不要编造。"
                    )
                    summary = await chat_text(
                        messages=[{"role": "user", "content": prompt}],
                        system_prompt="你是新闻编辑，擅长提炼社区讨论的核心分歧。",
                        temperature=0.3,
                    )
                    text = (summary or "").strip()[:500]
                    if text:
                        return {"ok": True, "kind": "zhihu_answers", "summary": text}
                except Exception as e:
                    logger.warning("[hot/discuss] zhihu llm failed: %s", e)
                top = answers[0]
                return {"ok": True, "kind": "zhihu_answers",
                        "summary": f"@{top['author']}（{top['votes']}赞）：{top['excerpt'][:300]}"}
        except ZhihuNotConfigured:
            pass  # 未配置 secret：回退本地 detail
        except Exception as e:
            logger.info("[hot/discuss] zhihu search failed: %s", e)

    # 知乎回退：本地缓存里可能有话题详情（60s 源时代的缓存）
    if source == "zhihu" and title:
        cached = _HOT_CACHE.get("zhihu")
        if cached:
            for it in cached[1]:
                if it["title"] == title and it.get("detail"):
                    return {"ok": True, "kind": "excerpt", "summary": it["detail"]}
        return {"ok": False, "reason": "no_content"}

    if source == "weibo" and title:
        return await _weibo_discuss(title)

    if source == "douyin" and title:
        from backend.services.douyin import douyin_discuss
        return await douyin_discuss(title, chat_text)

    if not url:
        return {"ok": False, "reason": "no_url"}

    hit = _discuss_cache.get(url)
    if hit and hit[0] > _time.time():
        return hit[1]

    try:
        async with httpx.AsyncClient(timeout=12, trust_env=False, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as client:
            r = await client.get(url)
        r.raise_for_status()
        text = _extract_page_text(r.text[:262144])
    except Exception as e:
        logger.info("[hot/discuss] fetch failed %s: %s", url[:60], e)
        return {"ok": False, "reason": "fetch_failed"}

    if len(text) < 40:
        return {"ok": False, "reason": "js_or_login"}

    try:
        prompt = (
            f"热点标题：{title}\n\n"
            f"网页内容：{text}\n\n"
            "用2-3句话概括这个页面里大家在讨论什么（核心观点/争议点/情绪倾向）。"
            "只依据页面内容，不要编造。"
        )
        summary = await chat_text(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是新闻编辑，擅长提炼网络讨论的核心。",
            temperature=0.3,
        )
    except Exception as e:
        logger.warning("[hot/discuss] llm failed: %s", e)
        return {"ok": False, "reason": "llm_failed"}

    result = {"ok": True, "kind": "page", "summary": (summary or "").strip()[:500]}
    if result["summary"]:
        _discuss_cache[url] = (_time.time() + _DISCUSS_TTL, result)
    return result
