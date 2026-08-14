from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import goal as goal_service

router = APIRouter(prefix="/api", tags=["goal"])


class GoalStartRequest(BaseModel):
    description: str


class GoalConfirmRequest(BaseModel):
    steps: list[dict] | None = None


class GoalExecuteRequest(BaseModel):
    step_index: int
    user_input: str = ""


class GoalSkipRequest(BaseModel):
    step_index: int


def _goal_to_response(goal: dict) -> dict:
    return {
        "goal_id": goal["goal_id"],
        "project_id": goal["project_id"],
        "description": goal["description"],
        "goal_type": goal["goal_type"],
        "status": goal["status"],
        "analysis": goal.get("analysis", {}),
        "steps": goal["steps"],
        "current_step": goal["current_step"],
        "summary": goal_service.generate_summary(goal) if goal["status"] == "completed" else "",
        "created_at": goal.get("created_at", ""),
    }


async def _get_owned_goal(project_id: str, goal_id: str) -> dict:
    goal = await goal_service.get_goal(goal_id)
    if not goal or goal["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="目标不存在")
    return goal


@router.post("/projects/{project_id}/goal/start")
async def start_goal(project_id: str, body: GoalStartRequest):
    desc = body.description.strip()
    if not desc:
        raise HTTPException(status_code=400, detail="目标描述不能为空")
    goal = await goal_service.start_goal(project_id, desc)
    return _goal_to_response(goal)


@router.get("/projects/{project_id}/goal/{goal_id}")
async def get_goal(project_id: str, goal_id: str):
    goal = await _get_owned_goal(project_id, goal_id)
    return _goal_to_response(goal)


@router.post("/projects/{project_id}/goal/{goal_id}/confirm-plan")
async def confirm_plan(project_id: str, goal_id: str, body: GoalConfirmRequest):
    await _get_owned_goal(project_id, goal_id)
    goal = await goal_service.confirm_plan(goal_id, body.steps)
    return _goal_to_response(goal)


@router.post("/projects/{project_id}/goal/{goal_id}/execute-step")
async def execute_step(project_id: str, goal_id: str, body: GoalExecuteRequest):
    await _get_owned_goal(project_id, goal_id)
    goal = await goal_service.execute_step(goal_id, body.step_index, body.user_input)
    if not goal:
        raise HTTPException(status_code=400, detail="步骤不存在")
    return _goal_to_response(goal)


@router.post("/projects/{project_id}/goal/{goal_id}/skip")
async def skip_step(project_id: str, goal_id: str, body: GoalSkipRequest):
    await _get_owned_goal(project_id, goal_id)
    goal = await goal_service.skip_step(goal_id, body.step_index)
    if not goal:
        raise HTTPException(status_code=400, detail="步骤不存在")
    return _goal_to_response(goal)


@router.post("/projects/{project_id}/goal/{goal_id}/cancel")
async def cancel_goal(project_id: str, goal_id: str):
    await _get_owned_goal(project_id, goal_id)
    goal = await goal_service.cancel_goal(goal_id)
    return _goal_to_response(goal)
