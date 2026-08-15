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
