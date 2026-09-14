import asyncio
import logging
import os
from contextlib import asynccontextmanager

import aiosqlite

from backend.config import DATABASE_PATH

logger = logging.getLogger(__name__)

os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

KG_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL CHECK(entity_type IN (
        'character', 'location', 'faction', 'item', 'event'
    )),
    name TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    properties TEXT DEFAULT '{}',
    knowledge_layer TEXT NOT NULL DEFAULT 'truth' CHECK(knowledge_layer IN (
        'truth', 'revealed', 'foreshadow'
    )),
    chapter_from INTEGER,
    chapter_to INTEGER,
    source TEXT DEFAULT 'ai',
    confidence REAL DEFAULT 1.0,
    summary TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, entity_type, name)
);

CREATE TABLE IF NOT EXISTS kg_relations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    direction TEXT DEFAULT 'directed' CHECK(direction IN ('directed', 'bidirectional')),
    properties TEXT DEFAULT '{}',
    knowledge_layer TEXT NOT NULL DEFAULT 'truth' CHECK(knowledge_layer IN (
        'truth', 'revealed', 'foreshadow'
    )),
    chapter_from INTEGER,
    chapter_to INTEGER,
    confidence REAL DEFAULT 1.0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, subject_id, predicate, object_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_entities_project_type ON kg_entities(project_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_kg_entities_project_layer ON kg_entities(project_id, knowledge_layer);
CREATE INDEX IF NOT EXISTS idx_kg_relations_project ON kg_relations(project_id);
CREATE INDEX IF NOT EXISTS idx_kg_relations_subject ON kg_relations(subject_id);
CREATE INDEX IF NOT EXISTS idx_kg_relations_object ON kg_relations(object_id);
"""

GOALS_SQL = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    goal_type TEXT NOT NULL DEFAULT 'custom',
    status TEXT NOT NULL DEFAULT 'planning' CHECK(status IN (
        'planning', 'executing', 'completed', 'cancelled'
    )),
    analysis TEXT NOT NULL DEFAULT '{}',
    rules TEXT NOT NULL DEFAULT '',
    kg_summary TEXT NOT NULL DEFAULT '',
    current_step INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS goal_steps (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    dimension TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    step_type TEXT NOT NULL DEFAULT 'generate',
    questions TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
        'pending', 'completed', 'skipped'
    )),
    result TEXT NOT NULL DEFAULT '',
    saved_item_id TEXT,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(goal_id, step_index)
);

CREATE INDEX IF NOT EXISTS idx_goals_project ON goals(project_id);
CREATE INDEX IF NOT EXISTS idx_goal_steps_goal ON goal_steps(goal_id);
"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    genre TEXT,
    chapter_name_template TEXT DEFAULT '第{{n}}章 {{title}}',
    rules_text TEXT DEFAULT '',
    author_key TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    point TEXT,
    distilled_rowid INTEGER NOT NULL DEFAULT 0,
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
        'chapter_plan', 'chapter',
        'plot', 'theme', 'character', 'setting', 'summary',
        'volume_outline'
    )),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'finalized', 'locked')),
    title TEXT,
    subtitle TEXT DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    chapter_number INTEGER,
    sort_order INTEGER DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{{}}',
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

CREATE TABLE IF NOT EXISTS prompt_overrides (
    key TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT DEFAULT '',
    url TEXT DEFAULT '',
    hot TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(title, source)
);

CREATE INDEX IF NOT EXISTS idx_conversations_project_id ON conversations(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_workspace_project_type_status ON workspace_items(project_id, item_type, status);
CREATE INDEX IF NOT EXISTS idx_workspace_project_sort ON workspace_items(project_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_chronicle_project_id ON chronicle(project_id);
{KG_TABLES_SQL}
{GOALS_SQL}
"""

# 顺序迁移：version 递增。运行失败会阻止服务启动（fail-fast）。
# 注意：SCHEMA 是全新安装的最终形态；此处迁移只服务已有数据库的升级。
MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "workspace_items_add_subtitle",
     "ALTER TABLE workspace_items ADD COLUMN subtitle TEXT DEFAULT ''"),
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
    (7, "add_conversations_point_column", "ALTER TABLE conversations ADD COLUMN point TEXT"),
    (8, "add_projects_rules_text", "ALTER TABLE projects ADD COLUMN rules_text TEXT DEFAULT ''"),
    (9, "add_knowledge_graph_tables", KG_TABLES_SQL),
    (10, "add_goals_tables", GOALS_SQL),
    (11, "expand_workspace_item_types", """
CREATE TABLE workspace_items_v11 (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK(item_type IN (
        'story_core', 'world_setting', 'character_setting',
        'outline', 'outline_reverse', 'foreshadow',
        'chapter_plan', 'chapter',
        'plot', 'theme', 'character', 'setting', 'summary',
        'volume_outline'
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
INSERT INTO workspace_items_v11
    (id, project_id, item_type, status, title, subtitle, content,
     chapter_number, sort_order, metadata, created_at, updated_at)
SELECT
    id, project_id, item_type, status,
    COALESCE(title, ''), COALESCE(subtitle, ''), COALESCE(content, ''),
    chapter_number, COALESCE(sort_order, 0), COALESCE(metadata, '{}'), created_at, updated_at
FROM workspace_items;
DROP TABLE workspace_items;
ALTER TABLE workspace_items_v11 RENAME TO workspace_items;
CREATE INDEX IF NOT EXISTS idx_workspace_project_type_status
    ON workspace_items(project_id, item_type, status);
CREATE INDEX IF NOT EXISTS idx_workspace_project_sort
    ON workspace_items(project_id, sort_order);
"""),
    (13, "add_volume_outline_type", """
CREATE TABLE workspace_items_v13 (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK(item_type IN (
        'story_core', 'world_setting', 'character_setting',
        'outline', 'outline_reverse', 'foreshadow',
        'chapter_plan', 'chapter',
        'plot', 'theme', 'character', 'setting', 'summary',
        'volume_outline'
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
INSERT INTO workspace_items_v13
    (id, project_id, item_type, status, title, subtitle, content,
     chapter_number, sort_order, metadata, created_at, updated_at)
SELECT
    id, project_id, item_type, status,
    COALESCE(title, ''), COALESCE(subtitle, ''), COALESCE(content, ''),
    chapter_number, COALESCE(sort_order, 0), COALESCE(metadata, '{}'), created_at, updated_at
FROM workspace_items;
DROP TABLE workspace_items;
ALTER TABLE workspace_items_v13 RENAME TO workspace_items;
CREATE INDEX IF NOT EXISTS idx_workspace_project_type_status
    ON workspace_items(project_id, item_type, status);
CREATE INDEX IF NOT EXISTS idx_workspace_project_sort
    ON workspace_items(project_id, sort_order);
"""),
    (12, "add_materials_table", """
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT DEFAULT '',
    url TEXT DEFAULT '',
    hot TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(title, source)
);
"""),
    (14, "add_conversations_distilled_rowid",
     "ALTER TABLE conversations ADD COLUMN distilled_rowid INTEGER NOT NULL DEFAULT 0"),
    (15, "add_projects_author_key",
     "ALTER TABLE projects ADD COLUMN author_key TEXT DEFAULT ''"),
    (16, "add_prompt_overrides",
     """CREATE TABLE IF NOT EXISTS prompt_overrides (
    key TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
)"""),
]

_db: aiosqlite.Connection | None = None
_write_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        fresh_install = not os.path.exists(DATABASE_PATH)
        # isolation_level=None（autocommit）：单条语句独立提交，避免并发请求共享
        # 隐式事务时一方的 commit 把另一方写了一半的数据带出去。
        # 多语句原子写用 transaction()。必须在 connect 时传入（aiosqlite 在
        # 工作线程内创建底层连接，事后赋值会触发跨线程错误）。
        _db = await aiosqlite.connect(DATABASE_PATH, isolation_level=None)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON")
        await _db.execute("PRAGMA journal_mode = WAL")
        await _db.execute("PRAGMA busy_timeout = 5000")
        await _db.executescript(SCHEMA)
        await _run_migrations(_db, fresh_install)
    return _db


async def _has_column(db, table: str, column: str) -> bool:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    await cursor.close()
    return any(r[1] == column for r in rows)


async def _record_version(db, version: int):
    await db.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)", (version,))


async def _run_migrations(db, fresh_install: bool):
    cursor = await db.execute("SELECT MAX(version) as v FROM schema_migrations")
    row = await cursor.fetchone()
    await cursor.close()
    current_version = row["v"] if row and row["v"] is not None else 0

    if fresh_install:
        # 全新安装：SCHEMA 已是最终形态，直接登记全部版本
        for version, _, _ in MIGRATIONS:
            await _record_version(db, version)
        return

    for version, name, sql in MIGRATIONS:
        if version <= current_version:
            continue
        # 幂等保护：加列前先确认列不存在（数据库可能已手工修过）
        if version == 1 and await _has_column(db, "workspace_items", "subtitle"):
            await _record_version(db, version)
            continue
        if version == 7 and await _has_column(db, "conversations", "point"):
            await _record_version(db, version)
            continue
        if version == 14 and await _has_column(db, "conversations", "distilled_rowid"):
            await _record_version(db, version)
            continue
        if version == 8 and await _has_column(db, "projects", "rules_text"):
            await _record_version(db, version)
            continue
        if version == 13:
            cursor = await db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='workspace_items'")
            row = await cursor.fetchone()
            await cursor.close()
            if row and "volume_outline" in (row[0] or ""):
                await _record_version(db, version)
                continue
        if version == 11:
            # 幂等：表定义已含新类型则跳过
            cursor = await db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='workspace_items'")
            row = await cursor.fetchone()
            await cursor.close()
            if row and "'plot'" in (row[0] or ""):
                await _record_version(db, version)
                continue
        try:
            await db.executescript(f"BEGIN;{sql};COMMIT;")
        except Exception as e:
            # fail-fast：迁移失败必须阻止服务启动，避免 schema 漂移
            raise RuntimeError(f"Migration v{version} ({name}) failed: {e}") from e
        await _record_version(db, version)
        logger.info("Applied migration v%d (%s)", version, name)


@asynccontextmanager
async def transaction():
    """多语句原子写。全局串行，事务内不要进行耗时 IO（如 LLM 调用）。"""
    db = await get_db()
    async with _write_lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            yield db
        except BaseException:
            await db.execute("ROLLBACK")
            raise
        else:
            await db.execute("COMMIT")


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
