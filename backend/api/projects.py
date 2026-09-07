import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one
from backend.services.repo import UNTITLED_NAME

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str = ""  # 可留空：先创作，AI 在确定故事核（book_name 字段）时自动命名
    genre: Optional[str] = None
    chapter_name_template: Optional[str] = None
    rules_text: Optional[str] = None
    author_key: Optional[str] = None  # 作者人格（创作对话的文风），创建时应显式选择


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    genre: Optional[str] = None
    chapter_name_template: Optional[str] = None
    rules_text: Optional[str] = None
    author_key: Optional[str] = None


_PROJECT_ALLOWED_FIELDS = {"name", "genre", "chapter_name_template", "rules_text", "author_key"}


def _validate_author_key(key: Optional[str]) -> None:
    if key is None:
        return
    from backend.agents.authors import AUTHORS
    if key != "" and key not in AUTHORS:
        raise HTTPException(status_code=400, detail=f"未知的作者人格：{key}")


@router.get("")
async def list_projects():
    db = await get_db()
    rows = await fetch_all(db, "SELECT * FROM projects ORDER BY updated_at DESC")
    return rows


@router.get("/{project_id}")
async def get_project(project_id: str):
    db = await get_db()
    project = await fetch_one(db, "SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conv_row = await fetch_one(
        db,
        "SELECT COUNT(*) as cnt FROM conversations WHERE project_id = ?",
        (project_id,),
    )
    ws_row = await fetch_one(
        db,
        "SELECT COUNT(*) as cnt FROM workspace_items WHERE project_id = ?",
        (project_id,),
    )
    has_world = await fetch_one(
        db,
        "SELECT 1 FROM workspace_items WHERE project_id = ? AND item_type = 'world_setting' LIMIT 1",
        (project_id,),
    )
    has_chronicle = await fetch_one(
        db,
        "SELECT 1 FROM chronicle WHERE project_id = ? LIMIT 1",
        (project_id,),
    )

    project["stats"] = {
        "conversation_count": conv_row["cnt"] if conv_row else 0,
        "workspace_item_count": ws_row["cnt"] if ws_row else 0,
        "has_world_setting": has_world is not None,
        "has_chronicle": has_chronicle is not None,
    }

    return project


@router.post("")
async def create_project(body: ProjectCreate):
    db = await get_db()
    _validate_author_key(body.author_key)
    pid = str(uuid.uuid4())
    name = body.name.strip() or UNTITLED_NAME
    await db.execute(
        """INSERT INTO projects (id, name, genre, chapter_name_template, rules_text, author_key)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (pid, name, body.genre, body.chapter_name_template, body.rules_text, body.author_key or ""),
    )
    await db.commit()
    return await get_project(pid)


@router.put("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate):
    db = await get_db()
    row = await fetch_one(db, "SELECT 1 FROM projects WHERE id = ?", (project_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    _validate_author_key(body.author_key)

    fields = {
        k: v for k, v in body.model_dump().items()
        if v is not None and k in _PROJECT_ALLOWED_FIELDS
    }
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts = [f"{k} = ?" for k in fields]
    set_parts.append("updated_at = datetime('now')")
    values = list(fields.values()) + [project_id]
    await db.execute(
        f"UPDATE projects SET {', '.join(set_parts)} WHERE id = ?",
        values,
    )
    await db.commit()
    return await get_project(project_id)


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT 1 FROM projects WHERE id = ?", (project_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()
    return {"ok": True}
