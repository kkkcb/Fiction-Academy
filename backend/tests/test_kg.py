"""知识图谱合并去重测试。"""
import pytest

from backend.services import kg as kg_service


EXTRACTION = {
    "entities": [
        {"type": "character", "name": "林轩", "aliases": ["小轩"],
         "properties": {"境界": "练气三层"}, "summary": "主角"},
        {"type": "location", "name": "青云山脉", "properties": {}, "summary": "主要场景"},
    ],
    "relations": [
        {"subject": "林轩", "subject_type": "character",
         "predicate": "修炼于", "object": "青云山脉", "object_type": "location"},
    ],
}


@pytest.mark.asyncio
async def test_merge_dedup(project_id):
    stats1 = await kg_service.merge_extraction(project_id, EXTRACTION, source="ai")
    assert stats1["entities_new"] == 2
    assert stats1["relations_new"] == 1

    # 相同数据再合并：全部判重，不产生新行
    stats2 = await kg_service.merge_extraction(project_id, EXTRACTION, source="ai")
    assert stats2["entities_new"] == 0
    assert stats2["relations_new"] == 0
    assert stats2["relations_dup"] == 1

    graph = await kg_service.get_graph(project_id)
    assert len(graph["entities"]) == 2
    assert len(graph["relations"]) == 1


@pytest.mark.asyncio
async def test_merge_updates_properties(project_id):
    await kg_service.merge_extraction(project_id, EXTRACTION, source="ai")
    updated = {
        "entities": [
            {"type": "character", "name": "林轩",
             "properties": {"境界": "筑基期"}, "summary": "主角突破"},
        ],
        "relations": [],
    }
    stats = await kg_service.merge_extraction(project_id, updated, source="ai")
    assert stats["entities_updated"] == 1

    entities = await kg_service.list_entities(project_id)
    linxuan = [e for e in entities if e["name"] == "林轩"][0]
    assert linxuan["properties"]["境界"] == "筑基期"


@pytest.mark.asyncio
async def test_injection_respects_budget(project_id):
    """实体很多时 KG 注入必须受 token 预算约束。"""
    big = {
        "entities": [
            {"type": "character", "name": f"角色{i:03d}",
             "properties": {"背景": "很长的背景描述" * 20}, "summary": "概述" * 30}
            for i in range(60)
        ],
        "relations": [],
    }
    await kg_service.merge_extraction(project_id, big, source="ai")

    inject = await kg_service.build_kg_injection(project_id, max_tokens=1500)
    assert inject, "注入不应为空"
    # 粗估 token（中文 0.6/字）不超过预算的 1.3 倍（标签开销留余量）
    chinese_chars = sum(1 for ch in inject if '\u4e00' <= ch <= '\u9fff')
    assert chinese_chars * 0.6 <= 1500 * 1.3
    # 只保留了一部分角色（预算生效）
    assert inject.count("角色") < 60
