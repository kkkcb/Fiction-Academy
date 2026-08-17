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


@pytest.mark.asyncio
async def test_summarize_merges_into_items(client, monkeypatch):
    """AI 批量摘要合并进热榜条目（LLM 打桩）。"""
    items = [
        {"title": "热点A", "hot": "1万热度", "url": "", "summary": ""},
        {"title": "热点B", "hot": "2万热度", "url": "", "summary": "知乎自带详情"},
    ]

    async def fake_chat_json(messages, system_prompt=None, model="", temperature=0.5, **kw):
        return {"summaries": {"热点A": "某人做了某事引发讨论"}}

    monkeypatch.setattr(mat, "chat_json", fake_chat_json)
    await mat._summarize_source("weibo", items)
    assert items[0]["summary"] == "某人做了某事引发讨论"
    assert items[1]["summary"] == "知乎自带详情"  # 已有概要不被覆盖


@pytest.mark.asyncio
async def test_fetch_hot_seeds_zhihu_detail(client, monkeypatch):
    """知乎条目自带 detail 直接作为概要。"""
    class FakeResp:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [{"title": "某问题？", "detail": "关于某事的长描述" * 5, "hot_value_desc": "500万热度"}]}

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return FakeResp()

    monkeypatch.setattr(mat.httpx, "AsyncClient", FakeClient)
    items = await mat._fetch_hot("zhihu")
    assert items[0]["summary"].startswith("关于某事")
    assert len(items[0]["summary"]) <= 80
