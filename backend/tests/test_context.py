"""Context Builder 管道测试。"""
import pytest
from httpx import AsyncClient

from backend.services.context_builder import (
    ContextRequest, build_chat_context, build_workspace_digest, MAX_TOTAL_TOKENS,
)
from backend.services.wiki import estimate_tokens, detect_scene


def test_scene_detection():
    assert detect_scene("继续写下一章") == "write_chapter"
    assert detect_scene("帮我修改一下这段") == "edit_chapter"
    assert detect_scene("聊聊世界观设定") == "discuss_setting"
    assert detect_scene("今天天气不错") == "casual"


@pytest.mark.asyncio
async def test_chat_context_respects_total_budget(client, project_id):
    """大量设定条目时，最终上下文必须收敛到预算内。"""
    long_body = "## 地理\n" + ("青云山脉附近有一座古老的城池，城中流传着无数传说。" * 120)
    for i in range(12):
        resp = await client.post(
            f"/api/projects/{project_id}/workspace",
            json={
                "item_type": "world_setting",
                "title": f"设定{i}",
                "content": long_body,
                "status": "finalized",
            },
        )
        assert resp.status_code == 200

    ctx = ContextRequest(project_id=project_id, user_content="写第1章", scene="write_chapter")
    body = await build_chat_context(ctx)
    assert body, "上下文不应为空"
    assert estimate_tokens(body) <= MAX_TOTAL_TOKENS


@pytest.mark.asyncio
async def test_chat_context_includes_rules_and_settings(client, project_id):
    await client.put(f"/api/projects/{project_id}", json={"rules_text": "主角绝不能杀人"})
    await client.post(
        f"/api/projects/{project_id}/workspace",
        json={
            "item_type": "world_setting",
            "title": "世界观",
            "content": "## 力量体系\n练气、筑基、金丹。",
            "status": "finalized",
        },
    )
    body = await build_chat_context(ContextRequest(
        project_id=project_id, user_content="聊聊世界观", scene="discuss_setting",
    ))
    assert "主角绝不能杀人" in body
    assert "练气、筑基、金丹" in body


@pytest.mark.asyncio
async def test_workspace_digest(client, project_id):
    await client.post(
        f"/api/projects/{project_id}/workspace",
        json={"item_type": "world_setting", "title": "世界观", "content": "内容", "status": "draft"},
    )
    digest = await build_workspace_digest(project_id)
    assert "世界观" in digest
