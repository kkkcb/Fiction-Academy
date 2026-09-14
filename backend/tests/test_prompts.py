"""/api/prompts 提示词库：清单完整性 + 真实性 + 编辑（覆盖/恢复/热生效）。"""
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
        assert e["node"] and e["name"] and e["chars"] > 0 and e["key"]

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


@pytest.mark.asyncio
async def test_prompt_override_save_reset_and_hot_apply(client):
    """编辑链路：保存→运行时热生效→清单标记→恢复默认→还原。"""
    import backend.api.chat as chat
    import backend.api.prompts as prompts
    from backend.services import prompt_store

    key = "studio.sort_edit"
    original = prompts._ORIGINALS[key]

    # 保存覆盖
    resp = await client.put(f"/api/prompts/{key}", json={"text": "热更新测试文案"})
    assert resp.status_code == 200
    # 运行时对象已被热替换（无需重启）
    assert chat.SORT_EDIT_PROMPT == "热更新测试文案"
    # 清单展示覆盖文本 + 标记
    data = (await client.get("/api/prompts")).json()
    entry = next(e for e in data["items"] if e["key"] == key)
    assert entry["overridden"] is True
    assert entry["text"] == "热更新测试文案"
    assert data["overridden"] >= 1

    # 作者 DNA 覆盖：共享 dict 成员生效
    from backend.agents.authors import AUTHORS
    await client.put("/api/prompts/author.fanren", json={"text": "忘语测试DNA"})
    assert AUTHORS["fanren"]["style_dna"] == "忘语测试DNA"

    # 恢复默认
    resp = await client.delete(f"/api/prompts/{key}")
    assert resp.status_code == 200
    assert chat.SORT_EDIT_PROMPT == original
    await client.delete("/api/prompts/author.fanren")
    assert AUTHORS["fanren"]["style_dna"] != "忘语测试DNA"

    # 非法 key / 只读条目
    assert (await client.put("/api/prompts/no.such.key", json={"text": "x"})).status_code == 404
    assert (await client.put("/api/prompts/assistant.builtin.builtin-novel-writer",
                             json={"text": "x"})).status_code == 400

    # 清理（保险：测试进程内模块常量还原）
    await prompt_store.clear_override(key)
    await prompt_store.clear_override("author.fanren")
    prompts._apply_patch(key, original)
    prompts._apply_patch("author.fanren", prompts._ORIGINALS["author.fanren"])
