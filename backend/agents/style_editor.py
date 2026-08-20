"""AI味审查 Agent —— 每章写完后针对性优化 AI 痕迹。

独立于写作者（"修复者不能给自己打分"），专门识别并改写 AI 统计特征：
- 高频套话词（仿佛/宛如/似乎/不禁/一丝/渐渐/淡淡...）
- 句长均匀、三连排比、"不是...而是..."句式
- 空洞的环境/心理描写（无信息量的氛围渲染）
- 情绪直给（"愤怒""悲伤"而非动作呈现）
- 对话无毛边、人人腔调相同

输出：优化后的完整正文 + 修改点清单。
"""
import logging
import re
import statistics

from backend.agents.base import chat_json

logger = logging.getLogger(__name__)

# 统计层黑名单（与执笔铁律一致）
AI_WORDS = [
    "仿佛", "宛如", "似乎", "不禁", "一丝", "格外", "渐渐", "淡淡",
    "静静", "悄然", "瞬间", "微微", "轻轻", "缓缓", "弥漫", "嘴角",
    "眼神", "忽然", "空气", "某种", "莫名",
]

STYLE_AUDIT_PROMPT = """你是一位资深网文编辑 + 反AI检测专家。你面前是一章刚写好的小说，你的任务是**逐段识别并改写所有有AI味道的表达**，让文风完全人化。

## 你要找的AI痕迹（逐条排查）

### A. 高频套话词（出现即改写）
仿佛、宛如、似乎、不禁、一丝、渐渐、淡淡、静静、悄然、瞬间、微微、轻轻、缓缓、弥漫、嘴角、眼神、忽然、莫名
改法示例：
- "仿佛在诉说着什么" → 直接写它在干什么
- "一丝不安" → "心里咯噔一下" 或 删掉用动作表达
- "渐渐远去" → "走远了" 或 "走没影了"
- "嘴角微微上扬" → "笑了" 或 具体写他做了什么

### B. 句式统计特征
- 三连排比（"X了，Y了，Z了"）→ 改成不对称表达
- "不是...而是..." → 直接说是什么
- 句长均匀 → 加入长句（30字+）和极短句（5字内）的交错
- 段落等长 → 制造长短差

### C. 内容层面
- 空洞环境描写（"空气中弥漫着紧张的气氛"）→ 删掉或换具体感官
- 情绪直给（"他很愤怒""感到悲伤"）→ 用动作/生理反应/对话呈现
- 对话无毛边 → 加省略、打断、口语碎片、方言习惯
- 描写过于工整对仗 → 加一点"跑偏"的细节

## 改写原则
1. **情节、人物、对话内容、伏笔、数字、专有名词完全不变**
2. 只改表达方式，不改信息
3. 保持网文口语感，不要文艺腔
4. 宁可粗糙一点也不要精致均匀
5. 每处修改都要在 changes 里记录

输出 JSON：
{
  "revised_text": "优化后的完整章节正文（纯文本）",
  "changes": [
    {"type": "高频词|句式|情绪直给|空洞描写|对话毛边", "original": "原文片段", "revised": "改后片段", "reason": "一句说明"}
  ],
  "ai_score_before": "估计原稿AI概率(0-100)",
  "ai_score_after": "估计改后AI概率(0-100)"
}"""


def stat_ai_flags(text: str) -> list[str]:
    """统计层体检（同执笔后置检查的维度）。"""
    flags = []
    for w in AI_WORDS:
        n = text.count(w)
        if n > 2:
            flags.append(f"“{w}”x{n}")
    sents = [x.strip() for x in re.split(r"[。！？]", text) if x.strip()]
    lens = [len(x) for x in sents]
    if len(lens) > 5 and statistics.mean(lens) > 0:
        cv = statistics.stdev(lens) / statistics.mean(lens)
        if cv < 0.50:
            flags.append(f"句长CV={cv:.2f}")
    tri = len(re.findall(r"[\u4e00-\u9fff]{1,3}，[\u4e00-\u9fff]{1,3}，[\u4e00-\u9fff]{1,3}[，。]", text))
    if tri > 4:
        flags.append(f"三连排比x{tri}")
    if text.count("不是") + text.count("而是") > 4:
        flags.append("不是/而是句式多")
    return flags


async def audit_and_rewrite(chapter_content: str) -> dict:
    """审查并改写一章的 AI 痕迹。

    返回 {revised_text, changes, ai_score_before, ai_score_after, stat_flags}。
    失败时 revised_text 为空，调用方保留原稿。
    """
    stat_flags = stat_ai_flags(chapter_content)

    prompt = (
        f"（统计层体检提示，供参考：{'; '.join(stat_flags) or '统计层未超标，但仍需逐段排查内容层AI味'}）\n\n"
        f"章节正文：\n{chapter_content[:12000]}"
    )

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=STYLE_AUDIT_PROMPT,
            temperature=0.4,
        )
    except Exception as e:
        logger.warning("[style-editor] audit failed: %s", e)
        return {"revised_text": "", "changes": [], "stat_flags": stat_flags,
                "ai_score_before": None, "ai_score_after": None, "error": str(e)[:100]}

    revised = (result.get("revised_text") or "").strip()
    # 合理性检查：改写后不能太短（丢内容）或完全一样
    if revised and len(revised) > len(chapter_content) * 0.6 and revised[:50] != chapter_content[:50]:
        return {
            "revised_text": revised,
            "changes": result.get("changes") or [],
            "stat_flags": stat_flags,
            "ai_score_before": result.get("ai_score_before"),
            "ai_score_after": result.get("ai_score_after"),
        }
    return {"revised_text": "", "changes": result.get("changes") or [], "stat_flags": stat_flags,
            "ai_score_before": result.get("ai_score_before"), "ai_score_after": None}
