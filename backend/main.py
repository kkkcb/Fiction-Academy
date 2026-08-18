import os
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import CORS_ORIGINS, STATIC_DIR, VUE_DIST_DIR
from backend.database import get_db, close_db


def _setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Fiction Academy starting up...")

    db = await get_db()
    logger.info("Database initialized: %s", db)

    from backend.api.assistants import ensure_builtins
    await ensure_builtins()
    logger.info("Built-in assistants ensured")

    # 热榜预热：启动即拉取（用户首次打开素材库秒开），之后每 10 分钟保温
    import asyncio
    from backend.api.materials import warm_hot_cache, _HOT_CACHE

    async def _hot_keepalive():
        while True:
            _HOT_CACHE.clear()  # 让下一轮重新拉新
            await warm_hot_cache()
            await asyncio.sleep(24 * 3600)  # 一天一更

    hot_task = asyncio.create_task(_hot_keepalive())

    yield

    hot_task.cancel()
    logger.info("Shutting down...")
    await close_db()
    logger.info("Database closed")


app = FastAPI(title="Fiction Academy", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class NoCacheStaticFilesMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(".html") or path == "/" or path.endswith(".js") or path.endswith(".css"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheStaticFilesMiddleware)

from backend.api import projects, chat, workspace, chronicle, assistants, skeleton, chapter_writing, points, kg, goal, lint, materials

app.include_router(projects.router, prefix="/api/projects")
app.include_router(chat.router)
app.include_router(workspace.router)
app.include_router(chronicle.router)
app.include_router(assistants.router)
app.include_router(skeleton.router)
app.include_router(chapter_writing.router)
app.include_router(points.router)
app.include_router(kg.router)
app.include_router(goal.router)
app.include_router(lint.router)
app.include_router(materials.router)


@app.get("/api/health")
async def health_check():
    try:
        db = await get_db()
        from backend.database import fetch_one
        row = await fetch_one(db, "SELECT 1 as ok")
        db_ok = row is not None
    except Exception:
        db_ok = False

    from backend.config import LLM_API_KEY
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "llm_configured": bool(LLM_API_KEY),
    }


# Vue 版是主线前端；dist 已构建则优先托管，否则回退到原生版 frontend/
_vue_dist = VUE_DIST_DIR if (VUE_DIST_DIR / "index.html").exists() else STATIC_DIR
if _vue_dist.exists():
    logging.getLogger(__name__).info("Serving frontend from %s", _vue_dist)
    app.mount("/", StaticFiles(directory=str(_vue_dist), html=True), name="static")
