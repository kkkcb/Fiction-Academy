from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import close_db, get_db

from backend.api.projects import router as projects_router
from backend.api.chat import router as chat_router
from backend.api.workspace import router as workspace_router
from backend.api.chronicle import router as chronicle_router
from backend.api.assistants import router as assistants_router

STATIC_DIR = Path(__file__).parent.parent / "frontend"
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_db()
    yield
    await close_db()

app = FastAPI(title="Fiction Academy", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def no_cache_static_files(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/js/") or path.startswith("/css/") or path == "/style.css" or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(workspace_router, prefix="/api", tags=["workspace"])
app.include_router(chronicle_router, prefix="/api/projects", tags=["chronicle"])
app.include_router(assistants_router, prefix="/api", tags=["assistants"])

@app.get("/api/health")
async def health():
    return {"status": "ok"}

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
