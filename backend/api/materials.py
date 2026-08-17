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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

HOT_SOURCES = {
    "douyin": "抖音热点",
    "weibo": "微博热搜",
    "zhihu": "知乎热榜",
}

# 热榜缓存：源 → (过期时间戳, 数据)。TTL 10 分钟，规避公共实例限频（429）。
_HOT_CACHE: dict[str, tuple[float, list[dict]]] = {}
_HOT_TTL = 600
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FictionAcademy/1.0"


class MaterialCreate(BaseModel):
    title: str
    source: str = ""
    url: str = ""
    hot: str = ""
    note: str = ""


async def _fetch_hot(source: str) -> list[dict]:
    """拉取单个热榜源并归一化为 [{title, hot, url}]。"""
    async with httpx.AsyncClient(timeout=15, trust_env=False,
                                 headers={"User-Agent": _UA}) as client:
        r = await client.get(f"{HOT_API_BASE}/{source}")
        r.raise_for_status()
        body = r.json()
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
        items.append({
            "title": title,
            "hot": hot,
            "url": it.get("link") or it.get("detail") or "",
        })
    return items[:50]


@router.get("/hot")
async def get_hot(source: str = "douyin"):
    if source not in HOT_SOURCES:
        raise HTTPException(status_code=400, detail=f"不支持的热榜源：{source}")
    cached = _HOT_CACHE.get(source)
    if cached and cached[0] > time.time():
        return {"source": source, "label": HOT_SOURCES[source], "cached": True, "items": cached[1]}
    try:
        items = await _fetch_hot(source)
    except Exception as e:
        logger.warning("[hot] fetch %s failed: %s", source, e)
        if cached:
            return {"source": source, "label": HOT_SOURCES[source], "cached": True,
                    "items": cached[1], "stale": True}
        raise HTTPException(status_code=502, detail=f"热榜获取失败：{str(e)[:80]}")
    _HOT_CACHE[source] = (time.time() + _HOT_TTL, items)
    return {"source": source, "label": HOT_SOURCES[source], "cached": False, "items": items}


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
