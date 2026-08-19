"""一键写章端点测试：章纲自动生成 → 流式执笔 → 存档。"""
import json

import pytest

from backend.database import get_db, fetch_all
from backend.services import repo


@pytest.fixture
def write_stubs(monkeypatch):
    """打桩章纲生成与正文流式，记录调用。"""
    from backend.api import chapter_writing as cw
    from backend.api import workspace as ws

    calls = {"plan": [], "stream": []}

    async def fake_plan(**kwargs):
        calls["plan"].append(kwargs)
        return {
            "chapter_title": "青石镇来了个懒郎中",
            "pov": "顾平安",
            "core_conflict": "血神教执事夜袭青石镇",
            "reward": {"type": "反差", "design": "一掌平事"},
            "hook": "镇口来了个测灵老道",
            "threads": ["主线"],
            "foreshadows_setup": [],
            "foreshadows_payoff": [],
        }

    async def fake_stream(messages, system_prompt=None, model="", temperature=0.8, disable_thinking=False):
        calls["stream"].append({"messages": messages, "system_prompt": system_prompt, "disable_thinking": disable_thinking})
        for t in ["暮色四合，青石镇的炊烟刚起。", "顾平安把最后一把灵茶收进竹匾。"]:
            yield ("content", t)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(cw, "generate_chapter_plan", fake_plan)
    monkeypatch.setattr(cw, "chat_stream", fake_stream)
    # 后台钩子（编年史/摘要走真实 LLM）置空
    monkeypatch.setattr(ws, "_trigger_chronicle_update", noop)
    monkeypatch.setattr(ws, "_generate_chapter_summary", noop)
    return calls


async def _seed_skeleton(project_id: str):
    db = await get_db()
    await repo.upsert_workspace_item(
        db, project_id, "world_setting", title="世界观",
        content="守一道：动争心则道行崩", metadata={}, status="finalized",
    )


@pytest.mark.asyncio
async def test_write_stream_creates_plan_and_chapter(client, project_id, write_stubs):
    await _seed_skeleton(project_id)

    resp = await client.post(f"/api/projects/{project_id}/chapters/write-stream", json={})
    assert resp.status_code == 200, resp.text
    lines = [json.loads(l) for l in resp.text.strip().split("\n") if l.strip()]
    assert any(l.get("phase") == "plan" for l in lines)
    assert any(l.get("phase") == "writing" for l in lines)
    done = [l for l in lines if l.get("done")]
    assert done and done[0]["chapter_number"] == 1

    # 执笔 prompt 包含骨架约束与章纲
    assert write_stubs["stream"][0].get("disable_thinking") is False  # 默认精细模式（思考开）
    sys_prompt = write_stubs["stream"][0]["system_prompt"]
    assert "守一道" in sys_prompt
    assert "青石镇来了个懒郎中" in sys_prompt

    db = await get_db()
    plan_rows = await fetch_all(
        db, "SELECT status, chapter_number FROM workspace_items WHERE project_id=? AND item_type='chapter_plan'",
        (project_id,),
    )
    chap_rows = await fetch_all(
        db, "SELECT status, chapter_number, content FROM workspace_items WHERE project_id=? AND item_type='chapter'",
        (project_id,),
    )
    assert len(plan_rows) == 1 and plan_rows[0]["status"] == "finalized"
    assert len(chap_rows) == 1 and chap_rows[0]["chapter_number"] == 1
    assert chap_rows[0]["status"] == "finalized"
    assert "灵茶" in chap_rows[0]["content"]
    # 快速模式：关思考
    resp_fast = await client.post(f"/api/projects/{project_id}/chapters/write-stream", json={"fast": True})
    assert resp_fast.status_code == 200
    assert write_stubs["stream"][-1].get("disable_thinking") is True


@pytest.mark.asyncio
async def test_write_second_chapter_increments(client, project_id, write_stubs):
    await _seed_skeleton(project_id)
    for _ in range(2):
        resp = await client.post(f"/api/projects/{project_id}/chapters/write-stream", json={})
        assert resp.status_code == 200

    db = await get_db()
    nums = await fetch_all(
        db, "SELECT chapter_number FROM workspace_items WHERE project_id=? AND item_type='chapter' ORDER BY chapter_number",
        (project_id,),
    )
    assert [r["chapter_number"] for r in nums] == [1, 2]


@pytest.mark.asyncio
async def test_write_stream_requires_skeleton(client, project_id, write_stubs):
    resp = await client.post(f"/api/projects/{project_id}/chapters/write-stream", json={})
    assert resp.status_code == 200
    lines = [json.loads(l) for l in resp.text.strip().split("\n") if l.strip()]
    assert lines and "骨架" in lines[0].get("error", "")


@pytest.mark.asyncio
async def test_story_web_builds_threads(client, project_id):
    """脉络网组装：人物线聚合 + 伏笔埋收连线（纯 DB 组装，无 LLM）。"""
    from backend.services.story_web import build_story_web
    from backend.database import get_db
    import json as _json

    db = await get_db()
    for n, web in [
        (1, {"plot": "p1", "characters": ["顾平安", "沈青梧"], "foreshadows_setup": ["老槐树下的铁盒"], "foreshadows_payoff": []}),
        (2, {"plot": "p2", "characters": ["顾平安"], "foreshadows_setup": [], "foreshadows_payoff": ["老槐树下的铁盒"]}),
    ]:
        meta = {"web": web}
        if n == 2:
            meta["chapter_types"] = ["推剧情"]
        await db.execute(
            """INSERT INTO workspace_items (id, project_id, item_type, status, title, content, metadata, chapter_number, sort_order)
               VALUES (?, ?, 'chapter', 'finalized', ?, ?, ?, ?, ?)""",
            (f"sw-{n}", project_id, f"第{n}章", "内容" * 40, _json.dumps(meta, ensure_ascii=False), n, n),
        )
    await db.commit()

    web = await build_story_web(project_id)
    assert len(web["chapters"]) == 2
    gu = next(t for t in web["threads"] if t["kind"] == "character" and t["name"] == "顾平安")
    assert gu["chapters"] == [1, 2]
    fs = next(t for t in web["threads"] if t["kind"] == "foreshadow")
    assert fs["setup_ch"] == 1 and 2 in fs["chapters"] and 2 in fs["payoff_chs"]


@pytest.mark.asyncio
async def test_story_web_backfill(client, project_id, monkeypatch):
    from backend.services import story_web as sw

    async def fake_chat_json(messages, system_prompt=None, model="", temperature=0.5, **kw):
        return {"plot": "本章顾平安救下沈青梧", "characters": ["顾平安"],
                "foreshadows_setup": ["铁盒"], "foreshadows_payoff": [], "emotion": "暖"}

    monkeypatch.setattr(sw, "chat_json", fake_chat_json)
    from backend.database import get_db
    db = await get_db()
    await db.execute(
        """INSERT INTO workspace_items (id, project_id, item_type, status, title, content, metadata, chapter_number, sort_order)
               VALUES ('sw-bf', ?, 'chapter', 'finalized', '第9章', ?, '{}', 9, 9)""",
            (project_id, "内容" * 60),
    )
    await db.commit()

    r = await client.post(f"/api/projects/{project_id}/story-web/backfill", json={"limit": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] >= 1 and body["remaining"] == 0
