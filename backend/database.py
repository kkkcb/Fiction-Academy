import os
import aiosqlite

from backend.config import DATABASE_PATH

os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    genre TEXT,
    chapter_name_template TEXT DEFAULT '第{n}章 {title}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workspace_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK(item_type IN ('world_setting', 'character_setting', 'outline', 'chapter')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'finalized', 'locked')),
    title TEXT,
    content TEXT NOT NULL DEFAULT '',
    chapter_number INTEGER,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, item_type, chapter_number)
);

CREATE TABLE IF NOT EXISTS chronicle (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    timeline TEXT DEFAULT '[]',
    characters TEXT DEFAULT '[]',
    key_events TEXT DEFAULT '[]',
    unresolved_threads TEXT DEFAULT '[]',
    raw_text TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assistants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    is_builtin INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

_db: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.executescript(SCHEMA)
        await _run_migrations(_db)
        await _db.commit()
    return _db

async def _run_migrations(db):
    cols = await db.execute_fetchall("PRAGMA table_info(workspace_items)")
    col_names = [c["name"] for c in cols]
    if "subtitle" not in col_names:
        await db.execute("ALTER TABLE workspace_items ADD COLUMN subtitle TEXT DEFAULT ''")

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None
