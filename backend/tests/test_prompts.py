"""/api/prompts 提示词库：全环节提示词清单完整性与真实性。"""
import pytest


@pytest.mark.asyncio
async def test_prompts_library_covers_all_groups(client):
    resp = await client.get("/api/prompts")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == len(data["items"]) >= 40
    got_groups = {g["group"] for g in data["groups"]}
    expect_groups = {
        "创作对话", "作者设定集", "点位人格", "专家圆桌", "章节写作",
        "大纲与卷纲", "工作台辅助", "图谱与检查", "素材库",
    }
    assert expect_groups <= got_groups

    for e in data["items"]:
        assert e["text"].strip(), f"空提示词: {e['name']}"
        assert e["source"].endswith(".py")
        assert e["node"] and e["name"] and e["chars"] > 0

    # 分组计数与条目一致
    from collections import Counter
    actual = Counter(e["group"] for e in data["items"])
    for g in data["groups"]:
        assert g["count"] == actual[g["group"]]


@pytest.mark.asyncio
async def test_prompts_library_references_live_values(client):
    """清单直接引用代码常量：抽查几条与真实常量逐字一致，防止出现第二份拷贝。"""
    from backend.api import chat, chapter_writing
    from backend.agents.authors import AUTHORS
    from backend.config import SYSTEM_PROMPT

    resp = await client.get("/api/prompts")
    items = {(e["group"], e["name"]): e["text"] for e in resp.json()["items"]}

    assert items[("创作对话", "默认助手系统提示词")] == SYSTEM_PROMPT
    assert items[("章节写作", "执笔通用规则系统提示词")] == chapter_writing.CHAPTER_WRITER_SYSTEM_PROMPT
    assert items[("创作对话", "创作对话系统提示词（模板）")] == chat.STUDIO_CHAT_PROMPT_TEMPLATE
    # 6 位作者文风 DNA 全部在列
    for a in AUTHORS.values():
        assert any(a["style_dna"] == e["text"] for e in resp.json()["items"])
