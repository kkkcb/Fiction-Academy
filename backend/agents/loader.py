import re
import yaml
import logging
from pathlib import Path

from backend.config import CHARACTERS_DIR, DEFAULT_MODEL

logger = logging.getLogger(__name__)

CHAR_TYPE_DIR_MAP = {
    "writer": "writers",
    "peer": "peers",
    "operator": "operators",
    "content_reviewer": "content-reviewers",
    "compliance_reviewer": "compliance-reviewers",
    "reader": "readers",
}

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5\-]{1,64}$")


def _validate_path(char_type: str, char_name: str) -> Path:
    if char_type not in CHAR_TYPE_DIR_MAP:
        raise ValueError(f"Invalid character type: {char_type}")
    if not _NAME_PATTERN.match(char_name):
        raise ValueError(f"Invalid character name: {char_name}")
    base = Path(CHARACTERS_DIR).resolve()
    filepath = (base / CHAR_TYPE_DIR_MAP[char_type] / f"{char_name}.md").resolve()
    if not str(filepath).startswith(str(base)):
        raise ValueError(f"Path traversal detected: {char_name}")
    return filepath


def list_characters(char_type: str | None = None) -> list[dict]:
    results = []
    base = Path(CHARACTERS_DIR)
    if not base.exists():
        return results
    if char_type:
        if char_type not in CHAR_TYPE_DIR_MAP:
            return []
        dirs = [base / CHAR_TYPE_DIR_MAP[char_type]]
    else:
        dirs = [d for d in base.iterdir() if d.is_dir()]

    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.md"):
            try:
                char = load_character_file(f)
                results.append(char)
            except Exception as e:
                logger.warning("Failed to load character file %s: %s", f, e)
    return results


def load_character_file(filepath: Path | str) -> dict:
    filepath = Path(filepath)
    content = filepath.read_text(encoding="utf-8")

    if "---" not in content:
        raise ValueError(f"No frontmatter in {filepath}")

    parts = content.split("---", 2)
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()

    name = meta.get("name", filepath.stem)
    char_type = meta.get("type", filepath.parent.name.replace("-", "_"))

    system_prompt = (
        f"你是{name}。\n\n"
        f"{body}\n\n"
        f"请始终以{name}的身份和视角完成任务。保持你的性格特点和说话方式。"
    )

    base = Path(CHARACTERS_DIR).resolve()
    try:
        rel_path = str(filepath.resolve().relative_to(base.parent))
    except ValueError:
        rel_path = filepath.name

    return {
        "name": name,
        "type": char_type,
        "model": meta.get("model", DEFAULT_MODEL),
        "temperature": meta.get("temperature", 0.7),
        "system_prompt": system_prompt,
        "file_path": rel_path,
        "description": meta.get("description", ""),
    }


def load_character(char_type: str, char_name: str) -> dict:
    filepath = _validate_path(char_type, char_name)
    if not filepath.exists():
        raise FileNotFoundError(f"Character not found: {char_type}/{char_name}")
    return load_character_file(filepath)


def save_character(char_type: str, char_name: str, content: str) -> dict:
    filepath = _validate_path(char_type, char_name)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    return load_character_file(filepath)


def delete_character(char_type: str, char_name: str) -> bool:
    filepath = _validate_path(char_type, char_name)
    if filepath.exists():
        filepath.unlink()
        return True
    return False
