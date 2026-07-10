import uuid
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import get_db, fetch_all, fetch_one

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

BUILTIN_ASSISTANTS = [
    {
        "id": "builtin-novel-writer",
        "name": "小说创作助手",
        "description": "专业的小说创作助手，擅长构建世界观、设计角色、编写情节",
        "system_prompt": """你是一位专业的小说创作助手。你拥有丰富的小说创作经验，擅长：
- 构建自洽的世界观体系
- 设计立体的角色
- 编写引人入胜的故事情节
- 把控节奏和悬念

你的工作原则：
1. 一切创作必须基于已定稿的世界观，不可矛盾
2. 角色随故事发展自然成长变化
3. 每一章都要有看点和钩子
4. 尊重用户的创作意图，提供专业建议但以用户为准""",
        "model": "",
        "is_builtin": 1,
    },
]


class AssistantCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = ""


class AssistantUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None


async def ensure_builtins():
    db = await get_db()
    for a in BUILTIN_ASSISTANTS:
        row = await fetch_one(db, "SELECT id FROM assistants WHERE id = ?", (a["id"],))
        if not row:
            await db.execute(
                "INSERT INTO assistants (id, name, description, system_prompt, model, is_builtin) VALUES (?, ?, ?, ?, ?, ?)",
                (a["id"], a["name"], a["description"], a["system_prompt"], a["model"], a["is_builtin"]),
            )
    await db.commit()


@router.get("/assistants")
async def list_assistants():
    db = await get_db()
    rows = await fetch_all(db, "SELECT * FROM assistants ORDER BY is_builtin DESC, created_at ASC")
    return rows


@router.post("/assistants")
async def create_assistant(body: AssistantCreate):
    db = await get_db()
    aid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO assistants (id, name, description, system_prompt, model) VALUES (?, ?, ?, ?, ?)",
        (aid, body.name, body.description, body.system_prompt, body.model),
    )
    await db.commit()
    row = await fetch_one(db, "SELECT * FROM assistants WHERE id = ?", (aid,))
    return row


@router.put("/assistants/{assistant_id}")
async def update_assistant(assistant_id: str, body: AssistantUpdate):
    db = await get_db()
    existing = await fetch_one(db, "SELECT * FROM assistants WHERE id = ?", (assistant_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Assistant not found")

    name = body.name if body.name is not None else existing["name"]
    description = body.description if body.description is not None else existing["description"]
    model = body.model if body.model is not None else existing["model"]

    if existing.get("is_builtin"):
        system_prompt = existing["system_prompt"]
    else:
        system_prompt = body.system_prompt if body.system_prompt is not None else existing["system_prompt"]

    await db.execute(
        "UPDATE assistants SET name=?, description=?, system_prompt=?, model=?, updated_at=datetime('now') WHERE id=?",
        (name, description, system_prompt, model, assistant_id),
    )
    await db.commit()
    row = await fetch_one(db, "SELECT * FROM assistants WHERE id = ?", (assistant_id,))
    return row


@router.delete("/assistants/{assistant_id}")
async def delete_assistant(assistant_id: str):
    db = await get_db()
    row = await fetch_one(db, "SELECT is_builtin FROM assistants WHERE id = ?", (assistant_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Assistant not found")
    if row.get("is_builtin"):
        raise HTTPException(status_code=403, detail="Cannot delete built-in assistant")
    await db.execute("DELETE FROM assistants WHERE id = ?", (assistant_id,))
    await db.commit()
    return {"ok": True}
