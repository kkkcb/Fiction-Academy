from fastapi import APIRouter

from backend.services.lint import run_lint

router = APIRouter(prefix="/api", tags=["lint"])


@router.post("/projects/{project_id}/lint")
async def lint_project(project_id: str):
    return await run_lint(project_id)
