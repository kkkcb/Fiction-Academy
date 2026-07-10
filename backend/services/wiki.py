import re
import json
import logging
from typing import Literal

logger = logging.getLogger(__name__)

SceneType = Literal["write_chapter", "edit_chapter", "discuss_setting", "casual"]

MAX_CONTEXT_TOKENS = 8000

_SCENE_PATTERNS = [
    (re.compile(r"第\s*\d+\s*章|写.{0,6}章|继续写|下一章|开写|正文"), "write_chapter"),
    (re.compile(r"修改|重写|调整|改一下|润色"), "edit_chapter"),
    (re.compile(r"世界观|角色|设定|大纲|势力|地理|人物|性格|背景|修炼体系|历史"), "discuss_setting"),
]


def detect_scene(user_content: str) -> SceneType:
    if not user_content:
        return "casual"
    for pattern, scene in _SCENE_PATTERNS:
        if pattern.search(user_content):
            return scene
    return "casual"


_CHINESE_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "也", "都", "就", "还", "又",
    "这", "那", "这个", "那个", "这些", "那些", "什么", "怎么", "为什么",
    "可以", "能够", "应该", "需要", "必须", "的话", "的话", "一下", "一些",
    "一个", "一种", "一边", "一方面", "另外", "此外",
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们",
    "着", "过", "中", "上", "下", "里", "外", "前", "后",
    "写", "帮", "给", "让", "使", "被", "把", "到", "向", "对", "为",
}


def extract_keywords(*texts: str, min_len: int = 2, max_keywords: int = 30) -> set[str]:
    keywords = set()
    combined = " ".join(t for t in texts if t)
    for stopword in _CHINESE_STOPWORDS:
        combined = combined.replace(stopword, " ")
    chinese_words = re.findall(r"[\u4e00-\u9fa5]{2,8}", combined)
    for w in chinese_words:
        if w in _CHINESE_STOPWORDS:
            continue
        if len(w) < min_len:
            continue
        keywords.add(w)
        if len(keywords) >= max_keywords:
            break
    english_words = re.findall(r"[A-Za-z][a-z]{2,}", combined)
    for w in english_words:
        keywords.add(w.lower())
        if len(keywords) >= max_keywords:
            break
    return keywords


def parse_wiki_pages(content: str, item_type: str, doc_title: str = "") -> list[dict]:
    if not content:
        return []
    pages = []
    sections = re.split(r"^##\s+(.+)$", content, flags=re.MULTILINE)
    if len(sections) <= 1:
        keywords = extract_keywords(content, doc_title)
        return [{
            "type": item_type,
            "title": doc_title or item_type,
            "content": content.strip(),
            "keywords": keywords,
            "score": 0,
        }]
    for i in range(1, len(sections), 2):
        section_title = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""
        if not body:
            continue
        keywords = extract_keywords(section_title, body, doc_title)
        pages.append({
            "type": item_type,
            "title": section_title,
            "content": f"## {section_title}\n{body}",
            "keywords": keywords,
            "score": 0,
        })
    return pages


def query_wiki(
    all_pages: list[dict],
    user_content: str,
    scene: SceneType,
    max_pages: int = 12,
) -> list[dict]:
    if not all_pages:
        return []
    if scene in ("write_chapter", "edit_chapter"):
        return list(all_pages[:max_pages])

    query_keywords = extract_keywords(user_content)
    if not query_keywords:
        return list(all_pages[:max_pages // 2])

    for p in all_pages:
        page_kws = p.get("keywords", set())
        if not page_kws:
            p["score"] = 0
            continue
        overlap = len(query_keywords & page_kws)
        p["score"] = overlap / max(len(page_kws), 1) * (1 + overlap * 0.3)

    scored = [p for p in all_pages if p["score"] > 0]
    scored.sort(key=lambda x: -x["score"])
    if not scored:
        return list(all_pages[:max_pages // 2])
    return scored[:max_pages]


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    chinese_count = len(re.findall(r"[\u4e00-\u9fa5]", text))
    other_count = len(text) - chinese_count
    return int(chinese_count * 0.6 + other_count * 0.25)


def apply_token_budget(
    layer1: list[dict],
    layer2: list[dict],
    layer3: list[dict],
    max_tokens: int = MAX_CONTEXT_TOKENS,
) -> tuple[list[dict], list[dict], list[dict]]:
    l1, l2, l3 = list(layer1), list(layer2), list(layer3)
    total = sum(estimate_tokens(p["content"]) for p in l1 + l2 + l3)
    if total <= max_tokens:
        return l1, l2, l3

    while l3 and total > max_tokens:
        total -= estimate_tokens(l3.pop()["content"])
    while len(l2) > 2 and total > max_tokens:
        total -= estimate_tokens(l2.pop()["content"])
    while l2 and total > max_tokens:
        removed = l2.pop(0)
        total -= estimate_tokens(removed["content"])
    while len(l1) > 4 and total > max_tokens:
        total -= estimate_tokens(l1.pop()["content"])
    return l1, l2, l3


def assemble_context(
    core_pages: list[dict],
    story_pages: list[dict],
    detail_pages: list[dict],
    chronicle_text: str = "",
) -> str:
    parts = []

    ws_pages = [p for p in core_pages if p["type"] == "world_setting"]
    char_pages = [p for p in core_pages if p["type"] == "character_setting"]
    outline_pages = [p for p in core_pages if p["type"] == "outline"]

    if ws_pages:
        body = "\n\n".join(p["content"] for p in ws_pages)
        parts.append(f"<world_setting>\n{body}\n</world_setting>")

    if char_pages:
        body = "\n\n".join(p["content"] for p in char_pages)
        parts.append(f"<characters>\n{body}\n</characters>")

    if outline_pages:
        body = "\n\n".join(p["content"] for p in outline_pages)
        parts.append(f"<outline>\n{body}\n</outline>")

    if chronicle_text:
        parts.append(f"<chronicle>\n{chronicle_text}\n</chronicle>")

    prev_chapters = [p for p in story_pages if p["type"] == "chapter"]
    if prev_chapters:
        body = "\n\n".join(p["content"][:2000] for p in prev_chapters)
        parts.append(f"<previous_chapters>\n{body}\n</previous_chapters>")

    if detail_pages:
        body = "\n\n".join(p["content"] for p in detail_pages)
        parts.append(f"<relevant_details>\n{body}\n</relevant_details>")

    return "\n\n".join(parts) if parts else ""
