"""知乎开放平台 API（移植自 zhihu-cli skill 的 HTTP 协议）。

鉴权：Authorization: Bearer <secret> + X-Request-Timestamp（秒级时间戳）
未配置 ZHIHU_ACCESS_SECRET 时抛 ZhihuNotConfigured，调用方回退 60s 源。
"""
import logging
import re
import time

import httpx

from backend.config import ZHIHU_ACCESS_SECRET

logger = logging.getLogger(__name__)

_BASE = "https://developer.zhihu.com/api/v1/content"


class ZhihuNotConfigured(Exception):
    pass


def _headers() -> dict:
    if not ZHIHU_ACCESS_SECRET:
        raise ZhihuNotConfigured("未配置 ZHIHU_ACCESS_SECRET")
    return {
        "Authorization": f"Bearer {ZHIHU_ACCESS_SECRET}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json",
    }


async def _get(path: str, params: dict | None = None) -> dict:
    url = f"{_BASE}/{path}"
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                r = await client.get(url, params=params, headers=_headers())
            body = r.json()
            if r.status_code == 200 and body.get("Code") == 0:
                return body.get("Data") or {}
            # 时间戳过期等可重试错误：刷新时间戳再来一次
            if attempt == 0:
                continue
            raise RuntimeError(f"知乎API错误 HTTP{r.status_code} Code={body.get('Code')} {body.get('Message', '')[:80]}")
        except ZhihuNotConfigured:
            raise
        except Exception as e:
            if attempt == 1:
                raise
            logger.info("[zhihu] retry %s: %s", path, e)
    raise RuntimeError("unreachable")


async def fetch_hot(limit: int = 30) -> list[dict]:
    """官方知乎热榜：自带真实摘要（Summary）。"""
    data = await _get("hot_list", {"Limit": max(1, min(limit, 30))})
    items = []
    for it in data.get("Items") or []:
        title = (it.get("Title") or "").strip()
        if not title:
            continue
        items.append({
            "title": title,
            "hot": "",
            "url": it.get("Url") or "",
            "summary": (it.get("Summary") or "").strip()[:80],
        })
    return items


def _strip_em(text: str) -> str:
    return re.sub(r"</?em>", "", text or "")


async def search_answers(query: str, count: int = 6) -> list[dict]:
    """按关键词搜知乎回答/文章：真实内容摘录+赞同数+作者+精选评论。"""
    data = await _get("zhihu_search", {"Query": query, "Count": max(1, min(count, 20))})
    out = []
    for it in data.get("Items") or []:
        text = _strip_em(it.get("ContentText") or "").strip()
        if not text:
            continue
        comments = [_strip_em(c.get("Content") or "") for c in (it.get("CommentInfoList") or [])][:2]
        out.append({
            "title": it.get("Title") or "",
            "author": it.get("AuthorName") or "知乎用户",
            "votes": it.get("VoteUpCount") or 0,
            "excerpt": text[:500],
            "comments": [c for c in comments if c],
            "url": it.get("Url") or "",
        })
    out.sort(key=lambda x: -x["votes"])
    return out
