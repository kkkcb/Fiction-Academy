"""Goal 模式：目标拆解与逐步执行。

状态持久化在 goals / goal_steps 表中（重启不丢、支持多实例）。
状态机：planning → executing → completed / cancelled
"""
import json
import logging
import uuid
from datetime import datetime

from backend.database import get_db, fetch_all, fetch_one, transaction
from backend.agents.base import chat_json, chat_text, LLMError
from backend.services import repo
from backend.services.context_builder import build_workspace_digest

logger = logging.getLogger(__name__)


COMPLETENESS_SYSTEM_PROMPT = """你是一位资深小说创作顾问。请检查以下小说项目的完整性。

【已有设定】
{project_context}

请对照以下维度逐项检查，判断每项是 complete（完整）/ partial（部分）/ missing（缺失）：

1. 地理环境（世界格局、主要地点、特殊地理）
2. 势力体系（主要势力、势力关系、等级对比）
3. 力量体系（境界/等级划分、战力范围、特殊能力）
4. 社会规则（货币、等级制度、法律禁忌）
5. 历史背景（重大事件、时代背景、传说预言）
6. 主角设定（基本信息、性格、能力、动机、成长弧线）
7. 配角设定（关系、功能、独立动机）
8. 反派设定（核心动机、冲突根源、实力等级）
9. 角色关系网（主要角色间关系）
10. 核心冲突（主线冲突、起因、预期解决）
11. 故事结构（开端、发展、高潮、结局）
12. 关键事件链（必须发生的剧情节点）

返回 JSON：
{{
  "dimensions": [
    {{"name": "维度名", "status": "complete|partial|missing", "detail": "简短说明已有或缺少什么"}},
  ],
  "completion_rate": 0.0到1.0的数字,
  "priority_gaps": ["最优先要补的缺失项", ...]
}}

只返回 JSON，不要解释。"""


PLAN_SYSTEM_PROMPT = """你是一位小说创作项目经理。用户给出了一个创作目标，你需要根据项目当前的完整性分析，拆解为可执行的步骤列表。

【用户目标】{goal}

【完整性分析】
完成度：{rate}
缺失项：{gaps}

请生成一个执行计划，每一步应该：
1. 聚焦一个具体的创作子任务
2. 按逻辑顺序排列（先基础后衍生）
3. 说明这一步要做什么、为什么需要

返回 JSON：
{{
  "steps": [
    {{
      "title": "步骤标题（如：确认境界体系）",
      "dimension": "对应维度（如：力量体系）",
      "description": "这步要做什么的说明",
      "step_type": "generate（AI生成内容）或 confirm（需要用户先确认选择）",
      "questions": ["如果需要用户确认，列出问题（可空数组）"]
    }}
  ]
}}

步骤数量控制在3-7步。只返回 JSON。"""


EXECUTE_SYSTEM_PROMPT = """你是一位小说创作助手。请执行以下创作任务。

【项目已有设定】
{project_context}

【创作守则】
{rules}

【知识图谱摘要】
{kg_summary}

【当前任务】
{step_title}
{step_description}

{user_input_section}

请生成详细的创作内容。要求：
1. 内容要具体、可直接使用
2. 保持与已有设定一致
3. 符合创作守则的约束

直接输出创作内容正文，不要加标题前缀、不要解释。"""


GOAL_TYPE_MAP = {
    "补全世界观": ("complete_world", "世界观层"),
    "完善主角": ("complete_protagonist", "角色层·主角"),
    "设计反派": ("design_antagonist", "角色层·反派"),
    "梳理关系": ("review_relations", "角色层·关系网"),
    "规划大纲": ("plan_outline", "剧情层"),
    "检查一致性": ("check_consistency", "全部"),
}


async def _gather_kg_summary(project_id: str) -> str:
    try:
        from backend.services.kg import list_entities, list_relations
        entities = await list_entities(project_id)
        relations = await list_relations(project_id)
        if not entities:
            return "（知识图谱为空）"
        ent_lines = [f"- {e['name']}({e['entity_type']})" for e in entities[:20]]
        rel_lines = [f"- {r.get('subject_name')} {r['predicate']} {r.get('object_name')}" for r in relations[:15]]
        return f"实体({len(entities)}):\n" + "\n".join(ent_lines) + f"\n\n关系({len(relations)}):\n" + "\n".join(rel_lines)
    except Exception:
        return "（知识图谱不可用）"


async def _gather_rules(project_id: str) -> str:
    db = await get_db()
    row = await fetch_one(db, "SELECT rules_text FROM projects WHERE id = ?", (project_id,))
    return (row["rules_text"] or "").strip() if row else ""


def _classify_goal(description: str) -> str:
    desc = description.strip()
    for keyword, (gtype, _) in GOAL_TYPE_MAP.items():
        if keyword in desc:
            return gtype
    return "custom"


# ---------------------------------------------------------------------------
# 持久化

async def _save_goal(goal: dict):
    db = await get_db()
    async with transaction():
        await db.execute(
            """UPDATE goals SET status = ?, current_step = ?, analysis = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (goal["status"], goal["current_step"],
             json.dumps(goal.get("analysis") or {}, ensure_ascii=False), goal["goal_id"]),
        )
        for step in goal["steps"]:
            await db.execute(
                """UPDATE goal_steps SET title = ?, dimension = ?, description = ?, step_type = ?,
                       questions = ?, status = ?, result = ?, saved_item_id = ?,
                       updated_at = datetime('now')
                   WHERE goal_id = ? AND step_index = ?""",
                (step["title"], step["dimension"], step["description"], step["step_type"],
                 json.dumps(step.get("questions") or [], ensure_ascii=False),
                 step["status"], step["result"], step.get("saved_item_id"),
                 goal["goal_id"], step["index"]),
            )


async def load_goal(goal_id: str) -> dict | None:
    db = await get_db()
    row = await fetch_one(db, "SELECT * FROM goals WHERE id = ?", (goal_id,))
    if not row:
        return None
    steps_rows = await fetch_all(
        db,
        "SELECT * FROM goal_steps WHERE goal_id = ? ORDER BY step_index ASC",
        (goal_id,),
    )
    try:
        analysis = json.loads(row.get("analysis") or "{}")
    except (json.JSONDecodeError, TypeError):
        analysis = {}
    steps = []
    for s in steps_rows:
        try:
            questions = json.loads(s.get("questions") or "[]")
        except (json.JSONDecodeError, TypeError):
            questions = []
        steps.append({
            "index": s["step_index"],
            "title": s["title"],
            "dimension": s["dimension"],
            "description": s["description"],
            "step_type": s["step_type"],
            "questions": questions,
            "status": s["status"],
            "result": s["result"],
            "saved_item_id": s.get("saved_item_id"),
        })
    return {
        "goal_id": row["id"],
        "project_id": row["project_id"],
        "description": row["description"],
        "goal_type": row["goal_type"],
        "status": row["status"],
        "analysis": analysis,
        "rules": row.get("rules") or "",
        "kg_summary": row.get("kg_summary") or "",
        "steps": steps,
        "current_step": row["current_step"],
        "created_at": row.get("created_at") or "",
    }


# ---------------------------------------------------------------------------
# 状态机操作（api/goal.py 的入口）

async def start_goal(project_id: str, description: str) -> dict:
    db = await get_db()
    context = await build_workspace_digest(project_id, per_item_limit=800)
    rules = await _gather_rules(project_id)
    kg_summary = await _gather_kg_summary(project_id)

    try:
        analysis = await chat_json(
            messages=[{"role": "user", "content": f"请分析这个项目的完整性。目标方向：{description}"}],
            system_prompt=COMPLETENESS_SYSTEM_PROMPT.format(project_context=context),
            temperature=0.3,
        )
    except LLMError as e:
        logger.warning("[goal] completeness analysis failed, using empty: %s", e)
        analysis = {"dimensions": [], "completion_rate": 0, "priority_gaps": []}

    completion_rate = analysis.get("completion_rate", 0)
    gaps = analysis.get("priority_gaps", [])
    if not gaps:
        dim_names = [d["name"] for d in analysis.get("dimensions", []) if d.get("status") in ("missing", "partial")]
        gaps = dim_names[:5]

    try:
        plan = await chat_json(
            messages=[{"role": "user", "content": "请根据分析结果生成执行计划"}],
            system_prompt=PLAN_SYSTEM_PROMPT.format(
                goal=description, rate=completion_rate,
                gaps=json.dumps(gaps, ensure_ascii=False),
            ),
            temperature=0.4,
        )
    except LLMError as e:
        logger.warning("[goal] plan generation failed, fallback to single step: %s", e)
        plan = {"steps": [{"title": description, "dimension": "自定义",
                           "description": "直接执行用户目标", "step_type": "generate", "questions": []}]}

    goal_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    async with transaction():
        await db.execute(
            """INSERT INTO goals (id, project_id, description, goal_type, status, analysis,
                                  rules, kg_summary, current_step, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'planning', ?, ?, ?, 0, ?, datetime('now'))""",
            (goal_id, project_id, description, _classify_goal(description),
             json.dumps(analysis, ensure_ascii=False), rules, kg_summary, now),
        )
        for i, s in enumerate(plan.get("steps", [])):
            await db.execute(
                """INSERT INTO goal_steps
                   (id, goal_id, step_index, title, dimension, description, step_type,
                    questions, status, result, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', datetime('now'))""",
                (str(uuid.uuid4()), goal_id, i,
                 s.get("title", f"步骤 {i+1}"), s.get("dimension", ""), s.get("description", ""),
                 s.get("step_type", "generate"),
                 json.dumps(s.get("questions") or [], ensure_ascii=False)),
            )

    logger.info("[goal] started goal=%s project=%s", goal_id, project_id)
    return await load_goal(goal_id)


async def get_goal(goal_id: str) -> dict | None:
    return await load_goal(goal_id)


async def confirm_plan(goal_id: str, steps: list[dict] | None = None) -> dict | None:
    db = await get_db()
    goal = await load_goal(goal_id)
    if not goal:
        return None
    async with transaction():
        if steps:
            # 用户编辑过计划：全量重建 steps
            await db.execute("DELETE FROM goal_steps WHERE goal_id = ?", (goal_id,))
            for i, s in enumerate(steps):
                await db.execute(
                    """INSERT INTO goal_steps
                       (id, goal_id, step_index, title, dimension, description, step_type,
                        questions, status, result, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (str(uuid.uuid4()), goal_id, i,
                     s.get("title", f"步骤 {i+1}"), s.get("dimension", ""),
                     s.get("description", ""), s.get("step_type", "generate"),
                     json.dumps(s.get("questions") or [], ensure_ascii=False),
                     s.get("status", "pending"), s.get("result", "")),
                )
        await db.execute(
            "UPDATE goals SET status = 'executing', current_step = 0, updated_at = datetime('now') WHERE id = ?",
            (goal_id,),
        )
    return await load_goal(goal_id)


async def execute_step(goal_id: str, step_index: int, user_input: str = "") -> dict | None:
    goal = await load_goal(goal_id)
    if not goal or step_index >= len(goal["steps"]):
        return None

    step = goal["steps"][step_index]
    project_id = goal["project_id"]
    context = await build_workspace_digest(project_id, per_item_limit=800)

    input_section = ""
    if user_input:
        input_section = f"【用户补充信息】\n{user_input}\n"

    content = await chat_text(
        messages=[{"role": "user", "content": f"请执行：{step['title']}"}],
        system_prompt=EXECUTE_SYSTEM_PROMPT.format(
            project_context=context[:3000],
            rules=goal.get("rules", "") or "（无特殊守则）",
            kg_summary=(goal.get("kg_summary", "") or "（无图谱数据）")[:1000],
            step_title=step["title"],
            step_description=step["description"],
            user_input_section=input_section,
        ),
        temperature=0.7,
    )

    step["result"] = content or ""
    step["status"] = "completed"
    goal["current_step"] = step_index + 1

    item_id = await _save_to_workspace(project_id, step)
    step["saved_item_id"] = item_id

    if all(s["status"] in ("completed", "skipped") for s in goal["steps"]):
        goal["status"] = "completed"

    await _save_goal(goal)
    return goal


async def _save_to_workspace(project_id: str, step: dict) -> str | None:
    try:
        db = await get_db()
        item_type = "world_setting"
        dim = step.get("dimension", "")
        if "角色" in dim or "主角" in dim or "反派" in dim:
            item_type = "character_setting"
        elif "剧情" in dim or "大纲" in dim or "冲突" in dim or "事件" in dim:
            item_type = "outline"

        return await repo.upsert_workspace_item(
            db, project_id, item_type,
            title=step["title"], content=step["result"] or "", status="draft",
        )
    except Exception as e:
        logger.warning("[goal] failed to save step to workspace: %s", e)
        return None


async def skip_step(goal_id: str, step_index: int) -> dict | None:
    goal = await load_goal(goal_id)
    if not goal or step_index >= len(goal["steps"]):
        return None
    goal["steps"][step_index]["status"] = "skipped"
    goal["current_step"] = step_index + 1
    if all(s["status"] in ("completed", "skipped") for s in goal["steps"]):
        goal["status"] = "completed"
    await _save_goal(goal)
    return goal


async def cancel_goal(goal_id: str) -> dict | None:
    db = await get_db()
    goal = await load_goal(goal_id)
    if not goal:
        return None
    async with transaction():
        await db.execute(
            "UPDATE goals SET status = 'cancelled', updated_at = datetime('now') WHERE id = ?",
            (goal_id,),
        )
    return await load_goal(goal_id)


def generate_summary(goal: dict) -> str:
    steps = goal["steps"]
    completed = [s for s in steps if s["status"] == "completed"]
    skipped = [s for s in steps if s["status"] == "skipped"]
    analysis = goal.get("analysis", {})
    before_rate = analysis.get("completion_rate", 0)

    lines = [f"🎯 目标完成：{goal['description']}", ""]
    for i, s in enumerate(steps):
        if s["status"] == "completed":
            lines.append(f"✅ 步骤 {i+1}/{len(steps)}：{s['title']} → 已保存")
        elif s["status"] == "skipped":
            lines.append(f"⏭️ 步骤 {i+1}/{len(steps)}：{s['title']} → 已跳过")
        else:
            lines.append(f"⬜ 步骤 {i+1}/{len(steps)}：{s['title']} → 未执行")

    lines.append("")
    lines.append(f"📊 初始完成度：{int(before_rate * 100)}%")
    lines.append(f"📝 完成步骤：{len(completed)}/{len(steps)}")
    if skipped:
        lines.append(f"⏭️ 跳过步骤：{len(skipped)}")

    saved_titles = [s["title"] for s in completed if s.get("saved_item_id")]
    if saved_titles:
        lines.append("")
        lines.append("📄 新增工作台条目：")
        for t in saved_titles:
            lines.append(f"• {t}")

    return "\n".join(lines)
