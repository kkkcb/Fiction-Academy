import json
import logging
from typing import Literal

from backend.agents.base import chat_json, chat_text
from backend.agents.guide_prompts import POINT_CONFIGS

logger = logging.getLogger(__name__)

PointType = Literal["story_core", "world_setting", "character_setting", "outline", "outline_reverse"]

POINT_ORDER: list[PointType] = [
    "story_core",
    "world_setting",
    "character_setting",
    "outline_reverse",
    "outline",
]

POINT_LABELS = {
    "story_core": "故事核",
    "world_setting": "世界观",
    "character_setting": "核心人物",
    "outline_reverse": "倒推大纲",
    "outline": "正向大纲",
}

GUIDE_SYSTEM_PROMPT = """你是一位资深网文策划，正在通过对话引导作者建立小说的核心骨架。

你的核心职责：
1. 每次只聚焦当前点位的一个关键问题，不要一次问太多
2. 每个问题都要解释"为什么问这个"——让作者理解这个设定如何影响后续创作
3. 基于作者的回答，结构化提取关键字段
4. 用专业的网文视角给出反馈和引导（如指出爽点潜力、设定风险）
5. 当作者回答模糊时，主动追问或给出 2-3 个选项供选择

记住：你不是在填表，而是在和作者共创。每个回答都应该让你更理解这个故事的方向。"""


def _build_context_summary(existing_points: dict) -> str:
    parts = []
    for pt in POINT_ORDER:
        if pt in existing_points:
            data = existing_points[pt]
            label = POINT_LABELS[pt]
            title = data.get("title", "")
            meta = data.get("metadata", {})
            if meta:
                parts.append(f"【{label}】{title}\n已确定：{json.dumps(meta, ensure_ascii=False)}")
            else:
                parts.append(f"【{label}】{title}")
    return "\n\n".join(parts) if parts else "（尚未确定任何点位）"


async def guide_step(
    current_point: PointType,
    step: str,
    user_reply: str,
    existing_points: dict,
    conversation_history: list[dict] = None,
) -> dict:
    """执行一步引导对话。

    step: "intro"（点位开场）| "extract"（提取作者回答）| "next_question"（继续追问）
    返回：{reply, extracted_fields, is_complete}
    """
    label = POINT_LABELS[current_point]
    config = POINT_CONFIGS.get(current_point, {})
    context_summary = _build_context_summary(existing_points)
    history_text = ""
    if conversation_history:
        history_text = "\n".join(
            f"{'作者' if m.get('role') == 'user' else '策划'}：{m.get('content', '')}"
            for m in conversation_history[-8:]
        )

    if step == "intro":
        intro_text = config.get("intro", f"现在开始【{label}】点位的引导。")
        prompt = f"""{intro_text}

## 已确定的背景
{context_summary}

## 你的任务
基于已确定的背景和上面的开场，向作者发起【{label}】的引导对话。

要求：
1. 用开场里的核心问题作为切入点，但根据已确定的背景做个性化调整
2. 简要说明这个点位的作用（1-2句）
3. 提出第一个最关键的问题
4. 解释为什么这个问题重要
5. 如果合适，给出 2-3 个方向供作者参考

输出JSON：
{{
  "reply": "你对作者说的话（包含问题）",
  "focus_field": "本轮聚焦的字段名（英文）"
}}"""
        messages = [{"role": "user", "content": prompt}]
        result = await chat_json(messages, system_prompt=GUIDE_SYSTEM_PROMPT, temperature=0.6)
        return {
            "reply": result.get("reply", ""),
            "focus_field": result.get("focus_field", ""),
            "extracted_fields": {},
            "is_complete": False,
        }

    fields_def = config.get("fields", {})
    complete_fields = config.get("complete_fields", [])
    fields_hint = json.dumps(fields_def, ensure_ascii=False, indent=2)
    complete_hint = ", ".join(complete_fields) if complete_fields else "（无硬性必填）"

    prompt = f"""## 已确定的背景
{context_summary}

## 当前点位：【{label}】

## 该点位需要确定的字段
{fields_hint}

## 硬性完成字段（必须确定才算完成）
{complete_hint}

## 对话历史
{history_text}

## 作者最新回答
{user_reply}

## 你的任务
1. 判断作者的回答是否足够明确（不是敷衍或"都行"）
2. 如果明确：从回答中提取出对应字段的值，填入 extracted_fields（只填能确定的，不编造）
3. 检查硬性完成字段是否都已确定（结合已确定的历史 metadata 一起判断）
4. 如果信息还不充分，提出下一个关键问题；如果充分，总结并标记完成

输出JSON：
{{
  "reply": "你的回应（肯定好点子 + 解释价值，或下一个问题）",
  "extracted_fields": {{}},
  "is_complete": false
}}"""

    messages = [{"role": "user", "content": prompt}]
    result = await chat_json(messages, system_prompt=GUIDE_SYSTEM_PROMPT, temperature=0.6)
    return {
        "reply": result.get("reply", ""),
        "extracted_fields": result.get("extracted_fields", {}),
        "is_complete": bool(result.get("is_complete", False)),
    }


async def detect_skeleton_completeness(points_data: dict) -> dict:
    """评估骨架完成度，返回每个点位的状态。"""
    result = {}
    for pt in POINT_ORDER:
        if pt in points_data:
            data = points_data[pt]
            content = data.get("content", "")
            metadata = data.get("metadata", {})
            content_len = len(content) if content else 0
            meta_filled = len(metadata) if isinstance(metadata, dict) else 0

            if content_len > 50 and meta_filled > 0:
                status = "done"
            elif content_len > 0 or meta_filled > 0:
                status = "partial"
            else:
                status = "empty"
            result[pt] = {
                "status": status,
                "label": POINT_LABELS[pt],
            }
        else:
            result[pt] = {
                "status": "missing",
                "label": POINT_LABELS[pt],
            }

    done_count = sum(1 for v in result.values() if v["status"] == "done")
    result["_summary"] = {
        "total": len(POINT_ORDER),
        "done": done_count,
        "percentage": int(done_count / len(POINT_ORDER) * 100),
        "is_skeleton_ready": done_count >= 4,
    }
    return result


async def check_write_readiness(points_data: dict) -> dict:
    """写章前检查：哪些关键点位缺失。"""
    completeness = await detect_skeleton_completeness(points_data)
    missing = []
    for pt in POINT_ORDER:
        st = completeness[pt]["status"]
        if st in ("missing", "empty"):
            missing.append({
                "point": pt,
                "label": POINT_LABELS[pt],
                "severity": "high" if pt in ("story_core", "outline") else "medium",
            })
        elif st == "partial":
            missing.append({
                "point": pt,
                "label": POINT_LABELS[pt],
                "severity": "low",
            })

    return {
        "ready": len([m for m in missing if m["severity"] == "high"]) == 0,
        "missing": missing,
        "completeness": completeness["_summary"],
    }
