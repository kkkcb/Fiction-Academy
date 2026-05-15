import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

XIAOMI_API_KEY = os.getenv("XIAOMI_API_KEY", "")
XIAOMI_BASE_URL = os.getenv("XIAOMI_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "mimo-v2.5-pro")
CHARACTERS_DIR = os.path.join(os.path.dirname(__file__), "..", "characters")
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fiction_academy.db")
