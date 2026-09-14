"""提示词库测试：清单完整性 + 真实性 + 编辑（覆盖/恢复/热生效）+ 全量 key 覆盖 + 历史版本。"""
import pytest

import backend.api.prompts as prompts


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

    # 非法 key / 空文本
    assert (await client.put("/api/prompts/no.such.key", json={"text": "x"})).status_code == 404
    assert (await client.put("/api/prompts/studio.sort_edit", json={"text": "  "})).status_code == 400

    # 清理（保险：测试进程内模块常量还原）
    await prompt_store.clear_override(key)
    await prompt_store.clear_override("author.fanren")
    prompts._apply_patch(key, original)
    prompts._apply_patch("author.fanren", prompts._ORIGINALS["author.fanren"])


@pytest.mark.asyncio
async def test_every_prompt_key_is_patchable(client):
    """全量覆盖：除内置助理（存 assistants 表）外，每个 key 的热替换都必须
    真正改写运行时对象——用注册表读到的值做断言（它读的就是调用点的同一对象）。"""
    SENTINEL = "【热替换探针】"
    for e in prompts._entries():
        key = e["key"]
        if key.startswith("assistant.builtin."):
            continue  # 助理走表，单独测
        prompts._apply_patch(key, SENTINEL)
        after = next(x["text"] for x in prompts._entries() if x["key"] == key)
        assert after == SENTINEL, f"{key} 热替换未生效——运行时对象没被改到"
        prompts._apply_patch(key, prompts._ORIGINALS[key])
    # 助理条目：PUT 写 assistants 表即生效
    resp = await client.put("/api/prompts/assistant.builtin.builtin-novel-writer",
                            json={"text": "助理提示词测试版"})
    assert resp.status_code == 200
    data = (await client.get("/api/prompts")).json()
    entry = next(e for e in data["items"] if e["key"] == "assistant.builtin.builtin-novel-writer")
    assert entry["text"] == "助理提示词测试版"
    assert entry["overridden"] is True
    # 恢复默认 → 回到代码内置文本
    await client.delete("/api/prompts/assistant.builtin.builtin-novel-writer")
    data = (await client.get("/api/prompts")).json()
    entry = next(e for e in data["items"] if e["key"] == "assistant.builtin.builtin-novel-writer")
    assert entry["overridden"] is False
    assert entry["text"] == prompts._ORIGINALS["assistant.builtin.builtin-novel-writer"]


@pytest.mark.asyncio
async def test_prompt_history_record_and_rollback(client):
    """历史版本：每次保存前旧版入档；可查看；把旧版重新 PUT 即回滚。"""
    key = "douyin.comment"
    original = prompts._ORIGINALS[key]

    r = await client.put(f"/api/prompts/{key}", json={"text": "版本A"})
    assert r.status_code == 200
    r = await client.put(f"/api/prompts/{key}", json={"text": "版本B"})
    assert r.status_code == 200

    hist = (await client.get(f"/api/prompts/{key}/history")).json()["items"]
    # 最近一次保存把「版本A」入档，最早一条是代码默认文本
    assert hist[0]["text"] == "版本A"
    assert any(h["text"] == original for h in hist), "首次修改前，代码默认文本也应入档"
    assert all("preview" in h and h["chars"] > 0 for h in hist)

    # 回滚 = 把历史版本重新保存
    await client.put(f"/api/prompts/{key}", json={"text": hist[0]["text"]})
    data = (await client.get("/api/prompts")).json()
    entry = next(e for e in data["items"] if e["key"] == key)
    assert entry["text"] == "版本A"
    # 回滚本身也留痕（版本B 入档）
    hist2 = (await client.get(f"/api/prompts/{key}/history")).json()["items"]
    assert hist2[0]["text"] == "版本B"

    # 收尾：恢复默认 + 清历史，避免影响其他测试
    await client.delete(f"/api/prompts/{key}")
    from backend.services import prompt_store as store
    db_mod = __import__("backend.database", fromlist=["get_db"])
    db = await db_mod.get_db()
    await db.execute("DELETE FROM prompt_history WHERE key = ?", (key,))
    await db.commit()
