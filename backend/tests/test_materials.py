"""热点素材库测试：CRUD + 去重 + 热榜归一化（外部 API 打桩）。"""
import pytest

from backend.api import materials as mat


@pytest.mark.asyncio
async def test_material_crud(client):
    # 收藏
    r = await client.post("/api/materials", json={
        "title": "开渔后第一波海鲜有多鲜", "source": "douyin", "hot": "1140万热度", "url": "https://x"})
    assert r.status_code == 200, r.text
    mid = r.json()["id"]

    # 重复收藏 → 409
    dup = await client.post("/api/materials", json={"title": "开渔后第一波海鲜有多鲜", "source": "douyin"})
    assert dup.status_code == 409

    # 列表
    lst = await client.get("/api/materials")
    assert any(m["id"] == mid for m in lst.json())

    # 删除 + 再删 404
    assert (await client.delete(f"/api/materials/{mid}")).status_code == 200
    assert (await client.delete(f"/api/materials/{mid}")).status_code == 404

    # 空标题 → 400
    assert (await client.post("/api/materials", json={"title": "  "})).status_code == 400


@pytest.mark.asyncio
async def test_hot_endpoint_normalization(client, monkeypatch):
    async def fake_fetch(source: str):
        return [{"title": f"事件{source}", "hot": "123万热度", "url": "u"}]

    monkeypatch.setattr(mat, "_fetch_hot", fake_fetch)
    r = await client.get("/api/hot?source=weibo")
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "微博热搜"
    assert body["items"][0]["title"] == "事件weibo"

    # 非法源 → 400
    assert (await client.get("/api/hot?source=xxx")).status_code == 400
