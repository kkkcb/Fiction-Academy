"""章纲 Agent —— 每章的执行清单生成器。

三段式写章的第一段：备稿。
基于骨架点位约束 + 倒推因果链 + 伏笔表，生成这一章的执行清单。
"""
import json
import logging

from backend.agents.base import chat_json

logger = logging.getLogger(__name__)

CHAPTER_PLAN_PROMPT = """你是一位资深网文编辑。你的任务是为小说的某一章生成详细的「章纲」——
这是每章的执行清单，让写作从"即兴创作"变成"按清单执行"。

章纲标准格式：
【第X章：章节名】
- 视点人物：本章以谁的视角展开
- 核心冲突：阻碍目标的是什么
- 本章爽点：类型（信息差/共情/逆袭/升级）+ 设计
- 断章钩子：结尾留什么悬念
- 推进线索：主线/感情线/暗线，推进了哪条
- 伏笔：本章埋设 / 回收的伏笔

你的核心原则：
1. 严格遵守骨架约束（世界观力量体系、人物行为锚点和红线、倒推因果链）
2. 章纲要具体可执行，不要空泛（"主角遇到困难"是坏的，"主角在拍卖会被反派抬价刁难"是好的）
3. 爽点设计要符合节奏（这章该是小爽点还是大爽点）
4. 钩子必须勾人，让读者想看下一章
5. 如果有该回收的伏笔，必须在本章回收"""


async def generate_chapter_plan(
    chapter_number: int,
    skeleton_context: str,
    recent_summary: str,
    pending_foreshadows: list[dict],
    user_hint: str = "",
) -> dict:
    """生成章纲。

    skeleton_context: 骨架点位的结构化摘要（故事核/世界观/人物/大纲）
    recent_summary: 近章剧情摘要（State 复利）
    pending_foreshadows: 该回收的伏笔列表 [{content, setup_chapter, payoff_chapter}]
    user_hint: 用户对这章的额外要求
    返回: {chapter_title, pov, core_conflict, reward, hook, threads, foreshadows_setup, foreshadows_payoff}
    """
    foreshadow_text = ""
    if pending_foreshadows:
        lines = []
        for f in pending_foreshadows:
            lines.append(
                f"- [{f.get('setup_chapter','?')}章埋设 → {f.get('payoff_chapter','?')}章回收] {f.get('content','')}"
            )
        foreshadow_text = "\n".join(lines)
    else:
        foreshadow_text = "（本章无必须回收的伏笔）"

    hint_section = f"\n## 作者对这章的额外要求\n{user_hint}" if user_hint else ""

    prompt = f"""## 骨架约束（必须严格遵守）
{skeleton_context}

## 近章剧情摘要（衔接前文，不要重复）
{recent_summary or "（这是第一章，无前文摘要）"}

## 本章该回收的伏笔
{foreshadow_text}
{hint_section}

## 当前任务
为【第{chapter_number}章】生成章纲。

输出JSON：
{{
  "chapter_title": "章节名（10字以内，要有吸引力）",
  "pov": "视点人物",
  "core_conflict": "核心冲突（具体，不要空泛）",
  "reward": {{
    "type": "信息差/共情/逆袭/升级",
    "design": "爽点设计（具体场景）"
  }},
  "hook": "断章钩子（结尾留什么悬念）",
  "threads": ["推进的主线/感情线/暗线"],
  "foreshadows_setup": ["本章新埋设的伏笔（如有）"],
  "foreshadows_payoff": ["本章回收的伏笔（必须来自上面的待回收列表）"],
  "chapter_types": ["本章粗分类（1-3个，按主次排序）：埋伏笔/推剧情/爽点爆发/高潮/过渡铺垫/人物塑造"],
  "estimated_words": 3200
}}"""

    messages = [{"role": "user", "content": prompt}]
    result = await chat_json(messages, system_prompt=CHAPTER_PLAN_PROMPT, temperature=0.7)
    return result


def format_chapter_plan_markdown(plan: dict, chapter_number: int) -> tuple[str, dict]:
    """把章纲转成 Markdown + metadata。

    返回: (content_markdown, metadata_json)
    """
    title = plan.get("chapter_title", f"第{chapter_number}章")
    reward = plan.get("reward", {})
    if isinstance(reward, str):
        reward = {"type": "", "design": reward}

    raw_types = plan.get("chapter_types") or plan.get("chapter_type") or []
    chapter_types = [str(t).strip() for t in (raw_types if isinstance(raw_types, list) else [raw_types]) if str(t).strip()]
    est_words = plan.get("estimated_words", 3200)
    type_line = (f"**本章类型**：{' + '.join(chapter_types)} | **目标字数**：{est_words}字"
                 if chapter_types else "")
    lines = [
        f"# 第{chapter_number}章：{title}",
        "",
        type_line,
        f"**视点人物**：{plan.get('pov', '')}",
        "",
        f"**核心冲突**：{plan.get('core_conflict', '')}",
        "",
        f"**本章爽点**（{reward.get('type', '')}）：{reward.get('design', '')}",
        "",
        f"**断章钩子**：{plan.get('hook', '')}",
        "",
    ]
    threads = plan.get("threads", [])
    if threads:
        lines.append("**推进线索**：")
        for t in threads:
            lines.append(f"- {t}")
        lines.append("")

    setup = plan.get("foreshadows_setup", [])
    payoff = plan.get("foreshadows_payoff", [])
    if setup or payoff:
        lines.append("**伏笔**：")
        for s in setup:
            lines.append(f"- 埋设：{s}")
        for p in payoff:
            lines.append(f"- 回收：{p}")

    content = "\n".join(lines)
    metadata = {
        "chapter_number": chapter_number,
        "chapter_title": title,
        "pov": plan.get("pov", ""),
        "core_conflict": plan.get("core_conflict", ""),
        "reward_type": reward.get("type", ""),
        "reward_design": reward.get("design", ""),
        "hook": plan.get("hook", ""),
        "threads": threads,
        "foreshadows_setup": setup,
        "foreshadows_payoff": payoff,
        "chapter_types": chapter_types,
        "estimated_words": plan.get("estimated_words", 3200),
    }
    return content, metadata
