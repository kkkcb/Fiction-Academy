"""共享数据访问助手：统一 metadata 解析、workspace upsert、背景加载等高频操作。"""
import json
import uuid

from backend.database import get_db, fetch_all, fetch_one, transaction


def parse_meta(metadata) -> dict:
    """安全解析 workspace_items.metadata JSON，坏数据返回空 dict。"""
    if not metadata:
        return {}
    if isinstance(metadata, dict):
        return metadata
    try:
        value = json.loads(metadata)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def touch_project(db, project_id: str):
    await db.execute(
        "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
        (project_id,),
    )


async def next_sort_order(db, project_id: str) -> int:
    row = await fetch_one(
        db,
        "SELECT MAX(sort_order) AS mx FROM workspace_items WHERE project_id = ?",
        (project_id,),
    )
    return (row["mx"] or 0) + 1 if row else 1


async def load_finalized_items(
    db, project_id: str, item_types: list[str], limit: int | None = None,
) -> list[dict]:
    """加载已定稿/锁定的 workspace 条目（metadata 已解析为 dict）。"""
    placeholders = ",".join("?" for _ in item_types)
    sql = f"""SELECT * FROM workspace_items
              WHERE project_id = ? AND item_type IN ({placeholders})
                AND status IN ('finalized', 'locked')
              ORDER BY sort_order, created_at"""
    params: tuple = (project_id, *item_types)
    if limit is not None:
        sql += " LIMIT ?"
        params = params + (limit,)
    rows = await fetch_all(db, sql, params)
    for r in rows:
        r["metadata"] = parse_meta(r.get("metadata"))
    return rows


async def upsert_workspace_item(
    db, project_id: str, item_type: str, *, title: str, content: str,
    metadata: dict | None = None, status: str = "finalized",
) -> str:
    """按 (project_id, item_type) upsert 一条 workspace 条目，返回 item_id。"""
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    async with transaction():
        existing = await fetch_one(
            db,
            "SELECT id FROM workspace_items WHERE project_id = ? AND item_type = ?",
            (project_id, item_type),
        )
        if existing:
            item_id = existing["id"]
            await db.execute(
                """UPDATE workspace_items
                   SET title = ?, content = ?, metadata = ?, status = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (title, content, metadata_json, status, item_id),
            )
        else:
            item_id = str(uuid.uuid4())
            sort_order = await next_sort_order(db, project_id)
            await db.execute(
                """INSERT INTO workspace_items
                   (id, project_id, item_type, status, title, content, metadata, chapter_number, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)""",
                (item_id, project_id, item_type, status, title, content, metadata_json, sort_order),
            )
        await touch_project(db, project_id)
    return item_id


def format_items_as_background(rows: list[dict], labels: dict[str, str]) -> str:
    """把 workspace 条目列表格式化为 LLM 背景文本。"""
    parts = []
    for r in rows:
        label = labels.get(r["item_type"], r["item_type"])
        parts.append(
            f"【{label}】{r.get('title') or ''}\n{r.get('content') or ''}\n"
            f"字段：{json.dumps(r.get('metadata') or {}, ensure_ascii=False)}"
        )
    return "\n\n".join(parts) if parts else "（无）"


async def conversation_project_id(db, conversation_id: str) -> str | None:
    """返回对话所属项目 ID；对话不存在返回 None。用于归属校验。"""
    row = await fetch_one(
        db, "SELECT project_id FROM conversations WHERE id = ?", (conversation_id,),
    )
    return row["project_id"] if row else None


async def save_message(db, conversation_id: str, role: str, content: str) -> str:
    msg_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, ?, ?)",
        (msg_id, conversation_id, role, content),
    )
    return msg_id


UNTITLED_NAME = "未命名作品"


async def maybe_apply_book_name(db, project_id: str, fields: dict) -> str | None:
    """故事核产出书名时，若项目还是占位名则自动命名为书名。返回新名字或 None。"""
    book_name = (fields.get("book_name") or "").strip() if isinstance(fields, dict) else ""
    book_name = book_name.strip("《》").strip()  # 模型常自带书名号，剥掉避免《《…》》
    if not book_name:
        return None
    row = await fetch_one(db, "SELECT name FROM projects WHERE id = ?", (project_id,))
    if not row or row["name"] != UNTITLED_NAME:
        return None
    await db.execute(
        "UPDATE projects SET name = ?, updated_at = datetime('now') WHERE id = ?",
        (book_name, project_id),
    )
    return book_name
