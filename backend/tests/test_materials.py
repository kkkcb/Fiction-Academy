"""热点素材库测试：CRUD + 去重 + 热榜归一化（外部 API 打桩）。"""
import time

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


def test_paraphrase_detector():
    """复读型摘要被识别，真增量信息放行。"""
    assert mat._is_paraphrase("宇树科技8月19日上市", "宇树科技将于8月19日上市")
    assert mat._is_paraphrase("未来5年我国能源蓝图划重点", "未来5年我国能源发展蓝图划定重点")
    assert not mat._is_paraphrase("宇树科技8月19日上市", "机器人独角兽宇树科技启动A股IPO")
    assert not mat._is_paraphrase("大批AI博主停更了", "AI内容创作竞争加剧，流量收益下滑引发停更潮")


@pytest.mark.asyncio
async def test_hot_discuss_paths(client, monkeypatch):
    """看讨论三条路径：知乎本地详情 / 可读网页 LLM 概括 / JS墙诚实失败。"""
    from backend.api import materials as m

    # 1) 知乎：命中本地缓存 detail 直出（无 LLM/网络）
    m._HOT_CACHE["zhihu"] = (time.time() + 600, [
        {"title": "知乎热题", "hot": "1万", "url": "u", "summary": "s", "detail": "完整的讨论摘录内容"}])
    r = await client.get("/api/hot/discuss", params={"title": "知乎热题", "source": "zhihu"})
    assert r.status_code == 200 and r.json()["ok"] and "讨论摘录" in r.json()["summary"]

    # 2) 可读网页：meta 摘要提取 + LLM 打桩
    class FakeResp:
        status_code = 200
        text = '<html><meta name="description" content="关于该热点的完整报道正文，包含事件经过、多方观点交锋与网友热议的讨论内容详述，信息量充足"></html>'
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return FakeResp()

    async def fake_chat_text(messages, system_prompt=None, model="", temperature=0.5, **kw):
        return "网友主要在讨论成本与安全性的取舍，情绪偏担忧。"

    monkeypatch.setattr(m.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(m, "chat_text", fake_chat_text)
    r2 = await client.get("/api/hot/discuss", params={"url": "https://x.example/a", "title": "T", "source": "weibo"})
    assert r2.json()["ok"] and "讨论" in r2.json()["summary"]

    # 3) JS 墙页面：提取不到正文 → 诚实失败
    class EmptyResp(FakeResp):
        text = "<html><body>short</body></html>"
    async def _empty_get(self, url):
        return EmptyResp()
    FakeClient.get = _empty_get
    r3 = await client.get("/api/hot/discuss", params={"url": "https://x.example/b", "title": "T2", "source": "douyin"})
    assert not r3.json()["ok"] and r3.json()["reason"] == "js_or_login"
