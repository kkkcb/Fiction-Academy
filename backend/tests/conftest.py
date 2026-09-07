"""测试环境：必须在导入 backend 前设置环境变量（数据库路径在导入期读取）。"""
import os
import tempfile
from pathlib import Path

_TMP_DIR = tempfile.mkdtemp(prefix="fa_test_")
os.environ["FA_DATABASE_PATH"] = str(Path(_TMP_DIR) / "test_fiction_academy.db")
os.environ["LLM_API_KEY"] = "test-key-not-real"
os.environ["LLM_BASE_URL"] = "http://127.0.0.1:9/v1"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from backend.main import app


@pytest_asyncio.fixture
async def client():
    from backend.database import get_db
    from backend.api.assistants import ensure_builtins
    await get_db()  # 确保 schema/迁移就绪
    await ensure_builtins()  # 与生产一致：注册内置助理
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def project_id(client: AsyncClient) -> str:
    # author_key 与线上行为一致：作者人格必选，创作对话/写章都依赖它
    resp = await client.post("/api/projects", json={"name": "测试项目", "author_key": "fanren"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]
