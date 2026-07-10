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
    item_type TEXT NOT NULL CHECK(item_type IN (
        'story_core', 'world_setting', 'character_setting',
        'outline', 'outline_reverse', 'foreshadow',
        'chapter_plan', 'chapter'
    )),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'finalized', 'locked')),
    title TEXT,
    subtitle TEXT DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    chapter_number INTEGER,
    sort_order INTEGER DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',
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

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_conversations_project_id ON conversations(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_workspace_project_type_status ON workspace_items(project_id, item_type, status);
CREATE INDEX IF NOT EXISTS idx_workspace_project_sort ON workspace_items(project_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_chronicle_project_id ON chronicle(project_id);
"""

MIGRATIONS = [
    (1, "ALTER TABLE workspace_items ADD COLUMN subtitle TEXT DEFAULT ''"),
]

RECREATE_WORKSPACE_ITEMS_V2 = [
    (2, "recreate_workspace_items_v2", """
CREATE TABLE workspace_items_new (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK(item_type IN (
        'story_core', 'world_setting', 'character_setting',
        'outline', 'outline_reverse', 'foreshadow',
        'chapter_plan', 'chapter'
    )),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'finalized', 'locked')),
    title TEXT,
    subtitle TEXT DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    chapter_number INTEGER,
    sort_order INTEGER DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, item_type, chapter_number)
);
"""),
    (3, "migrate_workspace_items_data_v2", """
INSERT INTO workspace_items_new
    (id, project_id, item_type, status, title, subtitle, content,
     chapter_number, sort_order, metadata, created_at, updated_at)
SELECT
    id, project_id, item_type, status,
    COALESCE(title, ''), COALESCE(subtitle, ''), COALESCE(content, ''),
    chapter_number, COALESCE(sort_order, 0), '{}', created_at, updated_at
FROM workspace_items;
"""),
    (4, "replace_workspace_items_v2", "DROP TABLE workspace_items;"),
    (5, "rename_workspace_items_v2", "ALTER TABLE workspace_items_new RENAME TO workspace_items;"),
    (6, "reindex_workspace_items_v2", """
CREATE INDEX IF NOT EXISTS idx_workspace_project_type_status
    ON workspace_items(project_id, item_type, status);
CREATE INDEX IF NOT EXISTS idx_workspace_project_sort
    ON workspace_items(project_id, sort_order);
"""),
]

_db: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON")
        await _db.execute("PRAGMA journal_mode = WAL")
        await _db.execute("PRAGMA busy_timeout = 5000")
        await _db.executescript(SCHEMA)
        await _run_migrations(_db)
        await _db.commit()
    return _db

async def _run_migrations(db):
    cursor = await db.execute("SELECT MAX(version) as v FROM schema_migrations")
    row = await cursor.fetchone()
    current_version = row["v"] if row and row["v"] is not None else 0
    await cursor.close()

    for entry in MIGRATIONS + RECREATE_WORKSPACE_ITEMS_V2:
        version = entry[0]
        sql = entry[-1]
        if version > current_version:
            try:
                if ";" in sql.strip().rstrip(";"):
                    await db.executescript(sql)
                else:
                    await db.execute(sql)
                await db.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)",
                    (version,),
                )
            except Exception as e:
                print(f"[migration v{version}] failed: {e}")
    await db.commit()

async def fetch_all(db, sql: str, params: tuple = ()) -> list[dict]:
    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    await cursor.close()
    return [dict(row) for row in rows]

async def fetch_one(db, sql: str, params: tuple = ()) -> dict | None:
    cursor = await db.execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return dict(row) if row else None

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None
