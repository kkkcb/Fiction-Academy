import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    genre: Optional[str] = None
    chapter_name_template: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    genre: Optional[str] = None
    chapter_name_template: Optional[str] = None


@router.get("")
async def list_projects():
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT * FROM projects ORDER BY updated_at DESC"
    )
    return [dict(row) for row in cursor]


@router.get("/{project_id}")
async def get_project(project_id: str):
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    )
    if not cursor:
        raise HTTPException(status_code=404, detail="Project not found")

    project = dict(cursor[0])

    conv_count = await db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM conversations WHERE project_id = ?",
        (project_id,),
    )
    workspace_count = await db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM workspace_items WHERE project_id = ?",
        (project_id,),
    )
    has_world = await db.execute_fetchall(
        "SELECT 1 FROM workspace_items WHERE project_id = ? AND item_type = 'world_setting' LIMIT 1",
        (project_id,),
    )
    has_chronicle = await db.execute_fetchall(
        "SELECT 1 FROM chronicle WHERE project_id = ? LIMIT 1",
        (project_id,),
    )

    project["stats"] = {
        "conversation_count": dict(conv_count[0])["cnt"],
        "workspace_item_count": dict(workspace_count[0])["cnt"],
        "has_world_setting": len(has_world) > 0,
        "has_chronicle": len(has_chronicle) > 0,
    }

    return project


@router.post("")
async def create_project(body: ProjectCreate):
    db = await get_db()
    pid = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO projects (id, name, genre, chapter_name_template)
        VALUES (?, ?, ?, ?)""",
        (pid, body.name, body.genre, body.chapter_name_template),
    )
    await db.commit()
    return await get_project(pid)


@router.put("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate):
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT 1 FROM projects WHERE id = ?", (project_id,)
    )
    if not cursor:
        raise HTTPException(status_code=404, detail="Project not found")

    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [project_id]
    await db.execute(
        f"UPDATE projects SET {set_clause} WHERE id = ?", values
    )
    await db.commit()
    return await get_project(project_id)


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    db = await get_db()
    cursor = await db.execute_fetchall(
        "SELECT 1 FROM projects WHERE id = ?", (project_id,)
    )
    if not cursor:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()
    return {"detail": "Project deleted"}
