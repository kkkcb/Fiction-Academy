"""提示词覆盖存取 —— 提示词库「编辑」的后端。

设计：
- 代码里的常量是默认值（唯一真身），用户在提示词库里的编辑存 prompt_overrides 表
- 调用方统一走 `await prompt(key, DEFAULT)`：有覆盖用覆盖，没有用默认——改完即时生效，无需重启
- 单进程 uvicorn，进程内缓存 + 写时更新即可
"""
import asyncio
import logging

from backend.database import get_db, fetch_all

logger = logging.getLogger(__name__)

_cache: dict[str, str] = {}
_loaded = False
_load_lock = asyncio.Lock()


async def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    async with _load_lock:
        if _loaded:
            return
        try:
            db = await get_db()
            rows = await fetch_all(db, "SELECT key, text FROM prompt_overrides")
            for r in rows:
                _cache[r["key"]] = r["text"]
            _loaded = True
        except Exception:
            # 表还没建好（极早期调用）时静默走默认值，下次再试
            logger.warning("[prompt_store] 加载覆盖失败，全部使用默认提示词", exc_info=True)


async def prompt(key: str, default: str) -> str:
    """取提示词：用户覆盖优先，否则代码默认值。所有 LLM 调用点都应走这里。"""
    await _ensure_loaded()
    return _cache.get(key, default)


async def set_override(key: str, text: str) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO prompt_overrides (key, text, updated_at) VALUES (?, ?, datetime('now'))
           ON CONFLICT(key) DO UPDATE SET text=excluded.text, updated_at=datetime('now')""",
        (key, text),
    )
    await db.commit()
    _cache[key] = text


async def clear_override(key: str) -> bool:
    db = await get_db()
    cur = await db.execute("DELETE FROM prompt_overrides WHERE key = ?", (key,))
    await db.commit()
    _cache.pop(key, None)
    return cur.rowcount > 0


async def all_overrides() -> dict[str, str]:
    await _ensure_loaded()
    return dict(_cache)


# ---- 历史版本：每次保存/恢复前把旧版入档，随时可回滚 ----

_HISTORY_KEEP = 100  # 每个 key 最多留的版本数


async def add_history(key: str, text: str) -> None:
    db = await get_db()
    await db.execute("INSERT INTO prompt_history (key, text) VALUES (?, ?)", (key, text))
    # 修剪：只留最近 N 版（按 id 倒序）
    await db.execute(
        """DELETE FROM prompt_history WHERE key = ? AND id NOT IN (
               SELECT id FROM prompt_history WHERE key = ? ORDER BY id DESC LIMIT ?
           )""",
        (key, key, _HISTORY_KEEP),
    )
    await db.commit()


async def get_history(key: str, limit: int = 50) -> list[dict]:
    db = await get_db()
    rows = await fetch_all(
        db,
        "SELECT id, text, created_at FROM prompt_history WHERE key = ? ORDER BY id DESC LIMIT ?",
        (key, limit),
    )
    return rows
