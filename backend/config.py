import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent

_env_file = _BASE_DIR / ".env.local"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass

DATABASE_PATH = os.getenv("FA_DATABASE_PATH", str(_BASE_DIR / "data" / "fiction_academy.db"))
CHARACTERS_DIR = os.getenv("FA_CHARACTERS_DIR", str(_BASE_DIR / "characters"))
STATIC_DIR = _BASE_DIR / "frontend"

LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("XIAOMI_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("XIAOMI_BASE_URL", "") or "https://open.bigmodel.cn/api/coding/paas/v4"
DEFAULT_MODEL = os.getenv("FA_DEFAULT_MODEL", "glm-5.2")
XIAOMI_API_KEY = LLM_API_KEY
XIAOMI_BASE_URL = LLM_BASE_URL

SYSTEM_PROMPT = """你是一位专业的小说创作助手。你的任务是协助用户进行小说创作，包括：
- 构建世界观、角色设定、大纲规划
- 撰写和优化章节内容
- 保持设定的连贯性和逻辑性

请遵循以下原则：
1. 严格基于用户已有的设定进行创作
2. 保持文风的一致性
3. 注意情节的因果关系和逻辑性
4. 如果用户的设定存在矛盾，请及时指出"""

LLM_TIMEOUT = int(os.getenv("FA_LLM_TIMEOUT", "120"))
LLM_MAX_RETRIES = int(os.getenv("FA_LLM_MAX_RETRIES", "3"))
LLM_MAX_TOKENS = int(os.getenv("FA_LLM_MAX_TOKENS", "8192"))
CHAT_HISTORY_LIMIT = int(os.getenv("FA_CHAT_HISTORY_LIMIT", "40"))

CORS_ORIGINS = [o.strip() for o in os.getenv("FA_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o.strip()]

if not LLM_API_KEY:
    logger.warning("LLM_API_KEY 未配置！聊天功能将无法使用。请设置环境变量 LLM_API_KEY。")
