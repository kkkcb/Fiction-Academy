import yaml
from pathlib import Path

from config import CHARACTERS_DIR, DEFAULT_MODEL

CHAR_TYPE_DIR_MAP = {
    "writer": "writers",
    "peer": "peers",
    "operator": "operators",
    "content_reviewer": "content-reviewers",
    "compliance_reviewer": "compliance-reviewers",
    "reader": "readers",
}

def list_characters(char_type: str | None = None) -> list[dict]:
    results = []
    base = Path(CHARACTERS_DIR)
    if char_type:
        dirs = [base / CHAR_TYPE_DIR_MAP.get(char_type, char_type)]
    else:
        dirs = [d for d in base.iterdir() if d.is_dir()]

    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.md"):
            try:
                char = load_character_file(f)
                results.append(char)
            except Exception:
                continue
    return results

def load_character_file(filepath: Path | str) -> dict:
    filepath = Path(filepath)
    content = filepath.read_text(encoding="utf-8")

    if "---" not in content:
        raise ValueError(f"No frontmatter in {filepath}")

    parts = content.split("---", 2)
    meta = yaml.safe_load(parts[1])
    body = parts[2].strip()

    name = meta.get("name", filepath.stem)
    char_type = meta.get("type", filepath.parent.name.replace("-", "_"))

    system_prompt = (
        f"你是{name}。\n\n"
        f"{body}\n\n"
        f"请始终以{name}的身份和视角完成任务。保持你的性格特点和说话方式。"
    )

    return {
        "name": name,
        "type": char_type,
        "model": meta.get("model", DEFAULT_MODEL),
        "temperature": meta.get("temperature", 0.7),
        "system_prompt": system_prompt,
        "file_path": str(filepath.relative_to(Path(CHARACTERS_DIR).parent)),
        "description": meta.get("description", ""),
    }

def load_character(char_type: str, char_name: str) -> dict:
    dir_name = CHAR_TYPE_DIR_MAP.get(char_type, char_type)
    filepath = Path(CHARACTERS_DIR) / dir_name / f"{char_name}.md"
    if not filepath.exists():
        raise FileNotFoundError(f"Character not found: {char_type}/{char_name}")
    return load_character_file(filepath)

def save_character(char_type: str, char_name: str, content: str) -> dict:
    dir_name = CHAR_TYPE_DIR_MAP.get(char_type, char_type)
    dir_path = Path(CHARACTERS_DIR) / dir_name
    dir_path.mkdir(parents=True, exist_ok=True)
    filepath = dir_path / f"{char_name}.md"
    filepath.write_text(content, encoding="utf-8")
    return load_character_file(filepath)

def delete_character(char_type: str, char_name: str) -> bool:
    dir_name = CHAR_TYPE_DIR_MAP.get(char_type, char_type)
    filepath = Path(CHARACTERS_DIR) / dir_name / f"{char_name}.md"
    if filepath.exists():
        filepath.unlink()
        return True
    return False
