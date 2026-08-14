import json
import logging

from backend.database import get_db, fetch_all
from backend.agents.base import chat_json

logger = logging.getLogger(__name__)


LINT_SYSTEM_PROMPT = """你是一位小说设定一致性检测专家。请仔细检查以下小说项目中的所有设定，找出矛盾、冲突和缺漏。

【工作台条目】
{workspace_content}

【知识图谱实体】
{kg_content}

请检查以下方面的问题：
1. 同一实体的属性在不同条目中是否矛盾（如角色A在某处是剑修，在另一处是法修）
2. 关系是否冲突（如A是B的师父，但年龄比B小）
3. 时间线是否矛盾（事件先后顺序不合理）
4. 力量体系是否自洽（境界高低与描述不符）
5. 世界观规则是否被违反（已设定的规则在后文被打破）
6. 重要信息缺失（提到但未解释的概念、未交代的伏笔）

返回 JSON：
{{
  "issues": [
    {{
      "severity": "error（严重矛盾）| warning（潜在问题）| info（建议补充）",
      "category": "角色矛盾|关系冲突|时间线|力量体系|世界观|信息缺失",
      "description": "具体问题描述",
      "location": "涉及的条目或实体名",
      "suggestion": "修正建议"
    }}
  ],
  "summary": "整体一致性评价（一句话）",
  "consistency_score": 0.0到1.0的数字
}}

如果没有发现问题，issues 返回空数组。只返回 JSON。"""


async def run_lint(project_id: str) -> dict:
    db = await get_db()
    ws_rows = await fetch_all(
        db,
        "SELECT item_type, title, content, status FROM workspace_items WHERE project_id = ? AND status IN ('finalized', 'locked', 'draft') ORDER BY sort_order",
        (project_id,),
    )
    workspace_parts = []
    for r in ws_rows:
        title = r["title"] or r["item_type"]
        content = (r["content"] or "")[:600]
        workspace_parts.append(f"【{title}】[{r['status']}]\n{content}")
    workspace_content = "\n\n".join(workspace_parts) if workspace_parts else "（无工作台条目）"

    try:
        from backend.services.kg import list_entities, list_relations
        entities = await list_entities(project_id)
        relations = await list_relations(project_id)
        ent_lines = [f"- {e['name']}({e['entity_type']}): {json.dumps(e.get('properties', {}), ensure_ascii=False)}" for e in entities[:30]]
        rel_lines = [f"- {r.get('subject_name')} {r['predicate']} {r.get('object_name')}" for r in relations[:20]]
        kg_content = "\n".join(ent_lines + [""] + rel_lines) if entities else "（知识图谱为空）"
    except Exception:
        kg_content = "（知识图谱不可用）"

    result = await chat_json(
        messages=[{"role": "user", "content": "请检查这个项目的设定一致性。"}],
        system_prompt=LINT_SYSTEM_PROMPT.format(workspace_content=workspace_content[:4000], kg_content=kg_content[:2000]),
        temperature=0.3,
    )

    if "error" in result:
        return {"issues": [], "summary": "检测失败，请重试", "consistency_score": 0, "error": result["error"]}

    return result
