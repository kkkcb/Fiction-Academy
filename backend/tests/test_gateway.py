"""LLM 网关单元测试：finish_reason=length 截断守卫。"""
import json
from types import SimpleNamespace

import pytest

from backend.agents import base
from backend.agents.base import chat_json, LLMJSONError


def _resp(content: str, finish_reason: str | None):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content),
            finish_reason=finish_reason,
        )],
        usage=None,
    )


def _fake_client(responses: list):
    """按顺序返回预设响应的假 OpenAI client。"""
    calls = {"n": 0}

    class Completions:
        async def create(self, **kwargs):
            i = min(calls["n"], len(responses) - 1)
            calls["n"] += 1
            return responses[i]

    class Chat:
        completions = Completions()

    class Client:
        chat = Chat()

    return Client(), calls


@pytest.mark.asyncio
async def test_chat_json_rejects_truncated_json(monkeypatch):
    """finish_reason=length（即使 JSON 恰好能解析）必须重试，不允许静默采用残缺数据。"""
    truncated = _resp('{"summary": "被截断但括号被服务端补全的合法 JSON"}', "length")
    good = _resp(json.dumps({"summary": "完整结果"}), "stop")
    client, calls = _fake_client([truncated, good])
    monkeypatch.setattr(base, "_get_client", lambda: client)
    monkeypatch.setattr(base, "LLM_MAX_RETRIES", 2)

    result = await chat_json([{"role": "user", "content": "x"}])
    assert result == {"summary": "完整结果"}
    assert calls["n"] == 2  # 第一次被拒，第二次采用


@pytest.mark.asyncio
async def test_chat_json_raises_when_always_truncated(monkeypatch):
    truncated = _resp('{"summary": "永远被截断"}', "length")
    client, calls = _fake_client([truncated])
    monkeypatch.setattr(base, "_get_client", lambda: client)
    monkeypatch.setattr(base, "LLM_MAX_RETRIES", 2)

    with pytest.raises(LLMJSONError):
        await chat_json([{"role": "user", "content": "x"}])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_chat_json_retry_feeds_error_back(monkeypatch):
    """解析失败重试必须带错误反馈（CrewAI guardrail 模式），而不是原样重发。"""
    bad = _resp("这不是JSON，只是普通文本", "stop")
    good = _resp(json.dumps({"summary": "修复后结果"}), "stop")
    seen: list[list[dict]] = []

    class Completions:
        async def create(self, **kwargs):
            seen.append(kwargs["messages"])
            return [bad, good][len(seen) - 1]

    class Chat:
        completions = Completions()

    class Client:
        chat = Chat()

    monkeypatch.setattr(base, "_get_client", lambda: Client())
    monkeypatch.setattr(base, "LLM_MAX_RETRIES", 2)

    result = await chat_json([{"role": "user", "content": "x"}])
    assert result == {"summary": "修复后结果"}
    assert len(seen) == 2
    # 第二次请求里带着第一次的坏输出 + 错误反馈
    assert seen[1][-2]["role"] == "assistant"
    assert seen[1][-2]["content"] == "这不是JSON，只是普通文本"
    assert seen[1][-1]["role"] == "user"
    assert "无法解析" in seen[1][-1]["content"]
