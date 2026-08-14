"""workspace 状态机与条目 CRUD 测试。"""
import pytest
from httpx import AsyncClient


async def _create_item(client: AsyncClient, project_id: str, **overrides) -> dict:
    body = {
        "item_type": "world_setting",
        "title": "测试条目",
        "content": "## 地理\n青云山脉绵延千里。",
    }
    body.update(overrides)
    resp = await client.post(f"/api/projects/{project_id}/workspace", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _set_status(client: AsyncClient, item_id: str, status: str):
    return await client.put(f"/api/workspace/{item_id}/status", json={"status": status})


@pytest.mark.asyncio
async def test_status_transitions(client, project_id):
    item = await _create_item(client, project_id)
    iid = item["id"]

    # draft → finalized / locked 均合法
    assert (await _set_status(client, iid, "finalized")).status_code == 200
    assert (await _set_status(client, iid, "draft")).status_code == 200
    assert (await _set_status(client, iid, "locked")).status_code == 200
    # locked → finalized 不合法
    resp = await _set_status(client, iid, "finalized")
    assert resp.status_code == 409
    # locked → draft 合法（解锁）
    assert (await _set_status(client, iid, "draft")).status_code == 200


@pytest.mark.asyncio
async def test_locked_item_cannot_edit(client, project_id):
    item = await _create_item(client, project_id)
    await _set_status(client, item["id"], "locked")
    resp = await client.put(f"/api/workspace/{item['id']}", json={"content": "篡改"})
    assert resp.status_code == 409

    resp = await client.delete(f"/api/workspace/{item['id']}")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_chapter_auto_numbering(client, project_id):
    c1 = await _create_item(client, project_id, item_type="chapter", title="第一章")
    c2 = await _create_item(client, project_id, item_type="chapter", title="第二章")
    assert c1["chapter_number"] == 1
    assert c2["chapter_number"] == 2


@pytest.mark.asyncio
async def test_metadata_persists(client, project_id):
    item = await _create_item(client, project_id, metadata={"power_system": "练气"})
    resp = await client.get(f"/api/projects/{project_id}/workspace")
    rows = resp.json()
    target = [r for r in rows if r["id"] == item["id"]][0]
    assert "power_system" in target["metadata"]  # list 接口返回原始 JSON 字符串或 dict 均可
