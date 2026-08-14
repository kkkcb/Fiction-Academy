"""项目创建与 AI 自动命名测试。"""
import pytest
from httpx import AsyncClient

from backend.services import repo
from backend.database import get_db, fetch_one


@pytest.mark.asyncio
async def test_create_project_without_name(client: AsyncClient):
    resp = await client.post("/api/projects", json={})
    assert resp.status_code == 200, resp.text
    project = resp.json()
    assert project["name"] == "未命名作品"

    # 空字符串同样落默认名
    resp2 = await client.post("/api/projects", json={"name": "   "})
    assert resp2.json()["name"] == "未命名作品"


@pytest.mark.asyncio
async def test_maybe_apply_book_name(client, project_id):
    db = await get_db()

    # 无书名：不改
    assert await repo.maybe_apply_book_name(db, project_id, {"one_liner": "x"}) is None

    # 已命名的项目不会被覆盖
    await client.put(f"/api/projects/{project_id}", json={"name": "我的书"})
    assert await repo.maybe_apply_book_name(db, project_id, {"book_name": "AI起的名"}) is None

    # 未命名项目：书名生效
    await client.put(f"/api/projects/{project_id}", json={"name": "未命名作品"})
    new_name = await repo.maybe_apply_book_name(db, project_id, {"book_name": "《外卖修仙录》"})
    assert new_name == "《外卖修仙录》"
    row = await fetch_one(db, "SELECT name FROM projects WHERE id = ?", (project_id,))
    assert row["name"] == "《外卖修仙录》"

    # 改名后再次产出书名：不覆盖用户可见名
    assert await repo.maybe_apply_book_name(db, project_id, {"book_name": "另一本书"}) is None
