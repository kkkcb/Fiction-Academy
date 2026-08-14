from backend.database import get_db, fetch_one


async def get_rules_injection(project_id: str) -> str:
    db = await get_db()
    row = await fetch_one(db, "SELECT rules_text FROM projects WHERE id = ?", (project_id,))
    if not row:
        return ""
    rules = (row.get("rules_text") or "").strip()
    if not rules:
        return ""
    return f"""<project_rules priority="absolute">
以下是本项目的「创作守则」，是最高优先级的约束，任何创作都必须严格遵守，不得违反：

{rules}

如果用户的请求与上述守则冲突，请优先遵守守则并明确提醒用户。
</project_rules>

"""
