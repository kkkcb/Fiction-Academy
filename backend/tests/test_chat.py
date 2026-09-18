"""聊天流与 regenerate 行为测试（LLM 打桩）。"""
import json

import pytest
from httpx import AsyncClient

from backend.database import get_db, fetch_all
from backend.api.chat import MSG_ORDER


@pytest.fixture
def llm_calls(monkeypatch):
    """打桩 chat_stream，记录每次调用的 messages 与 system_prompt。"""
    calls: list[dict] = []

    async def fake_stream(messages, system_prompt=None, model="", temperature=0.8):
        calls.append({"messages": [dict(m) for m in messages], "system_prompt": system_prompt or ""})
        yield ("content", f"第{len(calls)}版回复")

    import backend.api.chat as chat_module
    monkeypatch.setattr(chat_module, "chat_stream", fake_stream)
    return calls


async def _stream_chat(client: AsyncClient, cid: str, **body) -> list[dict]:
    resp = await client.post(f"/api/conversations/{cid}/chat/stream", json=body)
    assert resp.status_code == 200, resp.text
    events = []
    for line in resp.text.splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


@pytest.mark.asyncio
async def test_normal_chat_saves_both_messages(client, project_id, llm_calls):
    resp = await client.post(f"/api/projects/{project_id}/conversations")
    cid = resp.json()["id"]

    events = await _stream_chat(client, cid, content="你好")
    assert events[-1] == {"done": True}

    msgs = (await client.get(f"/api/conversations/{cid}/messages")).json()
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant"]
    assert len(llm_calls) == 1
    user_msgs = [m for m in llm_calls[0]["messages"] if m["role"] == "user"]
    assert len(user_msgs) == 1  # 用户消息只出现一次
    # 自由对话用默认助手人格
    assert "小说创作助手" in llm_calls[0]["system_prompt"]


@pytest.mark.asyncio
async def test_regenerate_does_not_duplicate_user_message(client, project_id, llm_calls):
    resp = await client.post(f"/api/projects/{project_id}/conversations")
    cid = resp.json()["id"]

    await _stream_chat(client, cid, content="写一段开头")
    await _stream_chat(client, cid, regenerate=True)

    # 库里：1 条 user + 1 条 assistant（新版覆盖旧版）
    msgs = (await client.get(f"/api/conversations/{cid}/messages")).json()
    user_rows = [m for m in msgs if m["role"] == "user"]
    asst_rows = [m for m in msgs if m["role"] == "assistant"]
    assert len(user_rows) == 1
    assert len(asst_rows) == 1
    assert asst_rows[0]["content"] == "第2版回复"

    # 发给 LLM 的消息里，用户内容只出现一次，且在末尾
    last_call = llm_calls[-1]["messages"]
    user_msgs = [m for m in last_call if m["role"] == "user"]
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"] == "写一段开头"
    assert last_call[-1]["role"] == "user"


@pytest.mark.asyncio
async def test_same_second_messages_order_stable(client, project_id, llm_calls):
    """同秒写入的消息按 rowid 排序，顺序稳定。"""
    resp = await client.post(f"/api/projects/{project_id}/conversations")
    cid = resp.json()["id"]
    await _stream_chat(client, cid, content="第一条")
    await _stream_chat(client, cid, content="第二条")

    msgs = (await client.get(f"/api/conversations/{cid}/messages")).json()
    contents = [m["content"] for m in msgs if m["role"] == "user"]
    assert contents == ["第一条", "第二条"]


@pytest.mark.asyncio
async def test_world_setting_point_uses_persona(client, project_id, llm_calls):
    """世界观点位：未选助理时由「铸世者-炳」主导；显式选择助理则助理优先。"""
    resp = await client.post(f"/api/projects/{project_id}/points/world_setting/ensure-conversation")
    cid = resp.json()["conversation_id"]

    # 默认（未选助理）：点位角色生效
    await _stream_chat(client, cid, content="这个世界靠什么变强？")
    assert "铸世者-炳" in llm_calls[-1]["system_prompt"]
    assert "世界建筑师" in llm_calls[-1]["system_prompt"]

    # 显式选择助理：助理覆盖点位角色
    await _stream_chat(client, cid, content="再讲讲", assistant_id="builtin-novel-writer")
    assert "小说创作助手" in llm_calls[-1]["system_prompt"]
    assert "世界建筑师" not in llm_calls[-1]["system_prompt"]


@pytest.mark.asyncio
async def test_delete_message(client, project_id):
    conv = await client.post(f"/api/projects/{project_id}/conversations", json={"title": "t"})
    cid = conv.json()["id"]
    db = await get_db()
    from backend.services import repo
    await repo.save_message(db, cid, "user", "要删的消息")
    await repo.save_message(db, cid, "assistant", "保留的消息")
    rows = await fetch_all(db, f"SELECT id, content FROM messages WHERE conversation_id = ? ORDER BY {MSG_ORDER}", (cid,))
    target = next(r for r in rows if r["content"] == "要删的消息")

    resp = await client.delete(f"/api/messages/{target['id']}")
    assert resp.status_code == 200 and resp.json()["ok"] is True

    rows2 = await fetch_all(db, "SELECT content FROM messages WHERE conversation_id = ?", (cid,))
    assert [r["content"] for r in rows2] == ["保留的消息"]

    # 删除不存在的消息 → 404
    resp404 = await client.delete(f"/api/messages/{target['id']}")
    assert resp404.status_code == 404


@pytest.mark.asyncio
async def test_studio_distill_classifies_and_increments(client, project_id, llm_calls, monkeypatch):
    """/studio/distill：新增对话自动归类到点位；水位线保证增量。"""
    ensure = await client.post(f"/api/projects/{project_id}/studio/ensure")
    cid = ensure.json()["conversation_id"]

    # 两轮对话（LLM 打桩）
    await _stream_chat(client, cid, content="主角的师父是个说书人，教过他一句话：话不能说满")
    await _stream_chat(client, cid, content="世界里灵气复苏只有三十年，老修士都是残废")

    # 分拣 LLM 打桩：归类到 人物 + 世界观
    async def fake_json(messages, system_prompt=None, temperature=0.3, **kw):
        return {
            "updates": [
                {"point": "character_setting", "changed": True, "note": "新增师父说书人设定",
                 "content": "师父是个说书人，教过主角：话不能说满。行走江湖靠一张嘴。"},
                {"point": "world_setting", "changed": True, "note": "灵气复苏三十年",
                 "content": "灵气复苏仅三十年，老一辈修士修为尽废，被称作残废。"},
                {"point": "story_core", "changed": False, "content": "x" * 30},
            ],
            "leftover": "用户随口提了个书名备选",
        }

    import backend.agents.base as base_module
    monkeypatch.setattr(base_module, "chat_json", fake_json)

    resp = await client.post(f"/api/projects/{project_id}/studio/distill")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    applied_points = {a["point"] for a in data["applied"]}
    assert applied_points == {"character_setting", "world_setting"}  # changed=False 的被跳过
    assert data["leftover"]

    # 工作台生成两条 draft
    items = (await client.get(f"/api/projects/{project_id}/workspace")).json()
    by_type = {i["item_type"]: i for i in items if i["item_type"] in ("character_setting", "world_setting")}
    assert len(by_type) == 2
    assert all(i["status"] == "draft" for i in by_type.values())
    assert "说书人" in by_type["character_setting"]["content"]

    # 汇报消息写入对话
    msgs = (await client.get(f"/api/conversations/{cid}/messages")).json()
    assert any("已把本轮讨论分拣进设定" in m["content"] for m in msgs)

    # 没有新对话时再分拣 → 400（增量水位生效）
    resp2 = await client.post(f"/api/projects/{project_id}/studio/distill")
    assert resp2.status_code == 400

    # 再聊一轮后可再次分拣；已有点位走 merge 且保留 status
    await _stream_chat(client, cid, content="师父其实姓柳，早年在皇城说书")

    async def fake_json2(messages, system_prompt=None, temperature=0.3, **kw):
        return {"updates": [
            {"point": "character_setting", "changed": True, "note": "补全师父身份",
             "content": "师父柳姓，皇城说书人出身，教主角：话不能说满。"},
        ], "leftover": ""}

    monkeypatch.setattr(base_module, "chat_json", fake_json2)
    resp3 = await client.post(f"/api/projects/{project_id}/studio/distill")
    assert resp3.status_code == 200
    assert resp3.json()["applied"][0]["action"] == "merged"
    items2 = (await client.get(f"/api/projects/{project_id}/workspace")).json()
    cs = [i for i in items2 if i["item_type"] == "character_setting"]
    assert len(cs) == 1  # merge 不新增条目
    assert "柳" in cs[0]["content"]
    assert cs[0]["status"] == "draft"


@pytest.mark.asyncio
async def test_studio_distill_requires_conversation(client, project_id):
    resp = await client.post(f"/api/projects/{project_id}/studio/distill")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_studio_distill_conflicts_human_review_flow(client, project_id, llm_calls, monkeypatch):
    """/distill 冲突链路：冲突不自动合并 → 审阅卡片消息 → 人工取舍 API → 写回点位 + 摘要。"""
    ensure = await client.post(f"/api/projects/{project_id}/studio/ensure")
    cid = ensure.json()["conversation_id"]
    await _stream_chat(client, cid, content="聊聊力量体系：旧的是万物有灵，现在想改成规则森严的一物一律")

    # 先造一份现有世界观（分拣的合并基底，也是冲突的"旧"）
    await client.post(f"/api/projects/{project_id}/workspace", json={
        "item_type": "world_setting", "title": "世界观",
        "content": "力量体系：万物有灵，各凭物性修行，灵气如潮汐涨落。" + "背景。" * 5,
        "status": "finalized",
    })

    async def fake_json(messages, system_prompt=None, temperature=0.3, **kw):
        return {
            "updates": [],
            "conflicts": [{
                "point": "world_setting",
                "old_summary": "万物有灵，各凭物性",
                "new_summary": "一物一律，规则森严",
                "suggestion": "以一物一律为主干，保留灵气潮汐",
                "new_content": "力量体系：一物一律，规则森严；灵气仍如潮汐涨落（保留自旧设定）。",
            }],
            "leftover": "",
        }

    import backend.agents.base as base_module
    monkeypatch.setattr(base_module, "chat_json", fake_json)

    resp = await client.post(f"/api/projects/{project_id}/studio/distill")
    assert resp.status_code == 200, resp.text

    # 冲突未自动合并：世界观内容保持旧版
    items = (await client.get(f"/api/projects/{project_id}/workspace")).json()
    ws = next(i for i in items if i["item_type"] == "world_setting")
    assert "万物有灵" in ws["content"]

    # 审阅卡片消息 + 汇报里提到冲突
    msgs = (await client.get(f"/api/conversations/{cid}/messages")).json()
    cards = [m for m in msgs if m["content"].lstrip().startswith('{"kind": "distill_review"')
             or m["content"].lstrip().startswith('{"kind":"distill_review"')]
    assert cards, "审阅卡片消息未写入"
    assert any("冲突" in m["content"] for m in msgs if m["role"] == "assistant")

    # digest：待取舍 1
    digest = (await client.get(f"/api/projects/{project_id}/distill-conflicts/digest")).json()
    assert digest["pending_count"] == 1
    conflict_id = digest["pending"][0]["id"]

    # 人工取舍：用新的
    r = await client.post(f"/api/projects/{project_id}/distill-conflicts/resolve", json={
        "choices": [{"id": conflict_id, "decision": "new"}],
    })
    assert r.status_code == 200 and r.json()["resolved"] == 1

    # 点位已按新说法更新；总结消息写入对话；digest 清零且带最近取舍
    items2 = (await client.get(f"/api/projects/{project_id}/workspace")).json()
    ws2 = next(i for i in items2 if i["item_type"] == "world_setting")
    assert "一物一律" in ws2["content"]
    msgs2 = (await client.get(f"/api/conversations/{cid}/messages")).json()
    assert any("分拣取舍完成" in m["content"] for m in msgs2)
    digest2 = (await client.get(f"/api/projects/{project_id}/distill-conflicts/digest")).json()
    assert digest2["pending_count"] == 0
    assert len(digest2["latest_resolved"]) == 1
    assert digest2["latest_resolved"][0]["decision"] == "new"


@pytest.mark.asyncio
async def test_pin_redistill_and_apply(client, project_id, llm_calls, monkeypatch):
    """沉淀=全模块再分拣：选中对话(新设定)×总览全部模块(原设定)→逐模块确认→采纳写入。"""
    ensure = await client.post(f"/api/projects/{project_id}/studio/ensure")
    assert ensure.status_code == 200
    await client.post(f"/api/projects/{project_id}/workspace", json={
        "item_type": "world_setting", "title": "世界观",
        "content": "力量体系：万物有灵，各凭物性修行。", "status": "finalized",
    })

    calls = {}

    async def fake_redistill(messages, system_prompt=None, temperature=0.5,
                             response_schema=None, deep_thinking=False, **kw):
        calls["deep_thinking"] = deep_thinking
        # prompt 里应带全部模块的原设定 + 新设定两输入
        joined = "".join(m["content"] for m in messages)
        assert "原设定" in joined and "新设定" in joined
        return {"modules": [
            {"point": "world_setting", "note": "修正力量体系并联动大纲",
             "content": "力量体系：一物一律，规则森严（修正自万物有灵）。灵气如潮汐。"},
            {"point": "outline", "note": "开局节奏联动调整",
             "content": "第一幕：灵气复苏开局，成长压着水位走半步，力量浓度前期压极低。"},
        ]}

    import backend.agents.base as base_module
    monkeypatch.setattr(base_module, "chat_json", fake_redistill)

    r = await client.post(f"/api/projects/{project_id}/pin-redistill", json={
        "content": "力量体系改成规则森严的一物一律；开局成长压着水位走。"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert calls["deep_thinking"] is True  # 思考强度最高
    assert {m["point"] for m in data["modules"]} == {"world_setting", "outline"}
    assert data["modules"][0]["is_new"] is False

    # 未确认前不落库
    items = (await client.get(f"/api/projects/{project_id}/workspace")).json()
    ws = next(i for i in items if i["item_type"] == "world_setting")
    assert "一物一律" not in ws["content"]

    # 只采纳世界观模块
    r2 = await client.post(f"/api/projects/{project_id}/pin-apply", json={
        "modules": [m for m in data["modules"] if m["point"] == "world_setting"],
    })
    assert r2.status_code == 200
    assert [a["point"] for a in r2.json()["applied"]] == ["world_setting"]
    items2 = (await client.get(f"/api/projects/{project_id}/workspace")).json()
    ws2 = next(i for i in items2 if i["item_type"] == "world_setting")
    assert "一物一律" in ws2["content"]
    assert not any(i["item_type"] == "outline" for i in items2)  # 未采纳的不写入

    # 空模块的 is_new 标记（foreshadow 不存在 → 若模型建议则为新建草稿）
    r3 = await client.post(f"/api/projects/{project_id}/pin-apply", json={
        "modules": [{"point": "foreshadow", "content": "最大伏笔：主角之死与死因真相，第一世实写埋节点。" * 1}],
    })
    assert r3.status_code == 200
    items3 = (await client.get(f"/api/projects/{project_id}/workspace")).json()
    assert any(i["item_type"] == "foreshadow" and i["status"] == "draft" for i in items3)


@pytest.mark.asyncio
async def test_pin_redistill_stream_emits_thinking_and_modules(client, project_id, monkeypatch):
    """流式再分拣：思考片段逐行推送，结束推 modules 结果。"""
    ensure = await client.post(f"/api/projects/{project_id}/studio/ensure")
    assert ensure.status_code == 200

    async def fake_stream(messages, system_prompt=None, model="", temperature=0.8,
                          disable_thinking=False, force_thinking=False, **kw):
        assert force_thinking is True  # 思考强度拉满
        yield ("reasoning", "先比对故事核…")
        yield ("reasoning", "再查世界观联动…")
        yield ("content", '```json\n{"modules": [{"point": "story_core", "note": "补充核心命题", '
                          '"content": "无善恶只有对立；生命的循环（死亡与馈赠同体）。"}]}\n```')

    import backend.agents.base as base_module
    monkeypatch.setattr(base_module, "chat_stream", fake_stream)

    async with client.stream("POST", f"/api/projects/{project_id}/pin-redistill/stream",
                             json={"content": "聊到生命的循环：死亡与馈赠同体。"}) as resp:
        assert resp.status_code == 200
        body = (await resp.aread()).decode("utf-8")
    lines = [__import__("json").loads(l) for l in body.splitlines() if l.strip()]
    thinkings = [l["thinking"] for l in lines if "thinking" in l]
    assert "".join(thinkings) == "先比对故事核…再查世界观联动…"
    result = next(l for l in lines if "modules" in l)
    assert result["modules"][0]["point"] == "story_core"
    assert any(l.get("done") for l in lines)


@pytest.mark.asyncio
async def test_chat_reply_persists_request_json(client, project_id, llm_calls):
    """AI 回复留存本次请求输入（系统提示词+消息列表+模型），双击可查。"""
    resp = await client.post(f"/api/projects/{project_id}/conversations")
    cid = resp.json()["id"]
    await _stream_chat(client, cid, content="你好，聊聊主角")
    msgs = (await client.get(f"/api/conversations/{cid}/messages")).json()
    assistant = next(m for m in msgs if m["role"] == "assistant")
    assert assistant.get("request_json"), "回复未留存 request_json"
    payload = json.loads(assistant["request_json"])
    assert "system_prompt" in payload and payload["system_prompt"].strip()
    assert payload["messages"], "消息列表为空"
    assert any(m["content"] == "你好，聊聊主角" for m in payload["messages"])
    # 用户消息不留存（它本身不是请求）
    user = next(m for m in msgs if m["role"] == "user")
    assert not user.get("request_json")
