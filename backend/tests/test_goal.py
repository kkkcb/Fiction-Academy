"""Goal 模式持久化测试（LLM 打桩）。"""
import pytest

from backend.services import goal as goal_service


@pytest.fixture
def mock_llm(monkeypatch):
    json_results = iter([
        {  # 完整性分析
            "dimensions": [{"name": "力量体系", "status": "missing", "detail": ""}],
            "completion_rate": 0.2,
            "priority_gaps": ["力量体系"],
        },
        {  # 执行计划
            "steps": [
                {"title": "设计力量体系", "dimension": "力量体系",
                 "description": "设计境界划分", "step_type": "generate", "questions": []},
                {"title": "设计主角", "dimension": "主角设定",
                 "description": "主角人设", "step_type": "generate", "questions": []},
            ]
        },
    ])

    async def fake_chat_json(messages, system_prompt=None, model="", temperature=0.5, **kw):
        return next(json_results)

    async def fake_chat_text(messages, system_prompt=None, model="", temperature=0.8, **kw):
        return "生成的设定内容"

    monkeypatch.setattr(goal_service, "chat_json", fake_chat_json)
    monkeypatch.setattr(goal_service, "chat_text", fake_chat_text)


@pytest.mark.asyncio
async def test_goal_lifecycle_persisted(project_id, mock_llm):
    goal = await goal_service.start_goal(project_id, "补全世界观")
    gid = goal["goal_id"]
    assert goal["status"] == "planning"
    assert len(goal["steps"]) == 2

    # 重新从数据库加载（模拟进程重启后的读取）
    reloaded = await goal_service.get_goal(gid)
    assert reloaded is not None
    assert reloaded["status"] == "planning"
    assert [s["title"] for s in reloaded["steps"]] == ["设计力量体系", "设计主角"]

    goal = await goal_service.confirm_plan(gid)
    assert goal["status"] == "executing"

    goal = await goal_service.execute_step(gid, 0)
    assert goal["steps"][0]["status"] == "completed"
    assert goal["steps"][0]["result"] == "生成的设定内容"
    assert goal["steps"][0]["saved_item_id"]

    goal = await goal_service.skip_step(gid, 1)
    assert goal["status"] == "completed"

    # 最终状态落库
    final = await goal_service.get_goal(gid)
    assert final["status"] == "completed"
    assert final["steps"][1]["status"] == "skipped"

    summary = goal_service.generate_summary(final)
    assert "目标完成" in summary


@pytest.mark.asyncio
async def test_goal_steps_saved_to_workspace(project_id, mock_llm):
    goal = await goal_service.start_goal(project_id, "补全世界观")
    gid = goal["goal_id"]
    await goal_service.confirm_plan(gid)
    goal = await goal_service.execute_step(gid, 0)

    saved_id = goal["steps"][0]["saved_item_id"]
    assert saved_id

    from backend.database import get_db, fetch_one
    db = await get_db()
    row = await fetch_one(db, "SELECT * FROM workspace_items WHERE id = ?", (saved_id,))
    assert row is not None
    assert row["status"] == "draft"  # 草稿状态待作者确认
    assert row["project_id"] == project_id
