"""审校 Agent —— Loop 的验证器。

核心原则（来自 Loop Engineering）：
"修复者不能给自己打分。" 写章 Agent 不能自检，必须换独立 Agent 验证。

审校维度（逐条核对，不是模糊评分）：
1. 人设红线违反（对照 character_setting.red_lines）
2. 力量体系开挂（对照 world_setting.power_limit）
3. 因果链断裂（对照 outline_reverse，这章是否在推进既定因果）
4. 该回收的伏笔漏了（对照 foreshadow 表）
5. 章纲执行度（核心冲突/爽点/钩子是否按章纲执行）
6. 节奏（爽点密度/钩子强度——温和提醒）
"""
import json
import logging

from backend.agents.base import chat_json

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """你是一位严格独立的网文审校编辑。你的职责是核对刚写完的章节是否违反了既定约束。

你不是在评价文笔好坏，而是在做**逐条合规性核对**——像质检员检查产品是否达标。

核对原则：
1. 每一项必须明确 PASS / FAIL / WARN，不能模糊
2. FAIL 必须给出具体证据（引用章节里的原文片段）
3. WARN 是温和提醒（如节奏偏慢），不阻塞发布
4. 只核对有据可查的约束，不要主观发挥
5. 你和写作者是不同角色，不要因为是"自己人"就放水"""


async def review_chapter(
    chapter_content: str,
    chapter_plan: dict,
    character_constraints: dict,
    world_constraints: dict,
    outline_reverse: dict,
    pending_foreshadows: list[dict],
) -> dict:
    """独立审校一章内容。

    返回：
    {
        "overall": "pass" | "fail" | "warn",
        "issues": [
            {
                "dimension": "人设红线|力量体系|因果链|伏笔|章纲执行|节奏",
                "severity": "fail" | "warn",
                "description": "问题描述",
                "evidence": "章节原文片段",
                "suggestion": "修改建议"
            }
        ],
        "summary": "一句话总结"
    }
    """
    char_text = _format_character_constraints(character_constraints)
    world_text = _format_world_constraints(world_constraints)
    plan_text = _format_chapter_plan(chapter_plan)
    outline_text = _format_outline_reverse(outline_reverse)
    foreshadow_text = _format_foreshadows(pending_foreshadows)

    prompt = f"""## 待审校章节内容
{chapter_content[:6000]}

## 本章章纲（执行标准）
{plan_text}

## 约束1：人物红线
{char_text}

## 约束2：世界观力量体系
{world_text}

## 约束3：倒推因果链（本章应在推进的因果）
{outline_text}

## 约束4：本章该回收的伏笔
{foreshadow_text}

## 你的审校任务
逐条核对以下维度，每条给出 PASS / FAIL / WARN：

1. **人设红线**：主角是否做了"绝对不会做的事"？
2. **力量体系**：是否出现了违反硬限制的能力使用（无代价开挂）？
3. **因果链**：本章是否在推进倒推链上的既定因果？还是凭空冒出无关情节？
4. **伏笔回收**：该回收的伏笔是否都回收了？
5. **章纲执行度**：核心冲突、爽点设计、断章钩子是否按章纲执行？
6. **节奏**：爽点密度是否足够？开头是否有冲突？结尾是否有钩子？（WARN 级）

输出JSON：
{{
  "overall": "pass 或 fail 或 warn",
  "issues": [
    {{
      "dimension": "维度名",
      "severity": "fail 或 warn",
      "description": "具体问题",
      "evidence": "章节原文片段（如有违反）",
      "suggestion": "修改建议"
    }}
  ],
  "summary": "一句话总结审校结果"
}}

注意：
- overall=fail 当且仅当存在任意一条 severity=fail 的 issue
- 没有问题的维度不需要列出（只列 FAIL 和 WARN）
- PASS 的维度在 summary 里概括即可"""

    messages = [{"role": "user", "content": prompt}]
    result = await chat_json(messages, system_prompt=REVIEW_PROMPT, temperature=0.3)
    return result


def _format_character_constraints(char_data: dict) -> str:
    if not char_data:
        return "（未设定人物约束，跳过此项）"
    name = char_data.get("name", "主角")
    desire = char_data.get("core_desire", "")
    red_lines = char_data.get("red_lines", [])
    if isinstance(red_lines, str):
        red_lines = [red_lines]
    lines = [f"姓名：{name}", f"核心欲望：{desire}", "绝对不能做的事（红线）："]
    for rl in red_lines:
        lines.append(f"  - {rl}")
    return "\n".join(lines)


def _format_world_constraints(world_data: dict) -> str:
    if not world_data:
        return "（未设定世界观约束，跳过此项）"
    power = world_data.get("power_system", "")
    limit = world_data.get("power_limit", "")
    golden = world_data.get("golden_finger", "")
    return f"力量体系：{power}\n硬限制（必须遵守）：{limit}\n金手指规则：{golden}"


def _format_chapter_plan(plan: dict) -> str:
    if not plan:
        return "（无章纲，跳过此项）"
    reward = plan.get("reward", {})
    if isinstance(reward, str):
        reward = {"type": "", "design": reward}
    lines = [
        f"章节：{plan.get('chapter_title', '')}",
        f"核心冲突：{plan.get('core_conflict', '')}",
        f"爽点（{reward.get('type', '')}）：{reward.get('design', '')}",
        f"断章钩子：{plan.get('hook', '')}",
    ]
    return "\n".join(lines)


def _format_outline_reverse(outline: dict) -> str:
    if not outline:
        return "（未设定倒推大纲，跳过此项）"
    endpoint = outline.get("endpoint_state", "")
    turns = outline.get("key_turning_points", [])
    if isinstance(turns, str):
        turns = [turns]
    lines = [f"终点状态：{endpoint}", "关键转折（必经节点）："]
    for t in turns:
        lines.append(f"  - {t}")
    return "\n".join(lines)


def _format_foreshadows(foreshadows: list[dict]) -> str:
    if not foreshadows:
        return "（本章无必须回收的伏笔）"
    lines = ["该回收的伏笔："]
    for f in foreshadows:
        lines.append(
            f"  - [{f.get('setup_chapter','?')}→{f.get('payoff_chapter','?')}] {f.get('content','')}"
        )
    return "\n".join(lines)


def should_retry(review_result: dict, max_retries: int = 3) -> bool:
    """判断是否应该打回重写。只有 fail 才打回，warn 不阻塞。"""
    if review_result.get("overall") == "fail":
        fails = [i for i in review_result.get("issues", []) if i.get("severity") == "fail"]
        return len(fails) > 0
    return False


def build_revision_feedback(review_result: dict) -> str:
    """把审校结果转成给写章 Agent 的修改指令。"""
    issues = review_result.get("issues", [])
    if not issues:
        return ""
    fails = [i for i in issues if i.get("severity") == "fail"]
    warns = [i for i in issues if i.get("severity") == "warn"]

    lines = ["审校发现问题，请修改后重写：", ""]
    if fails:
        lines.append("【必须修改】")
        for i, issue in enumerate(fails, 1):
            lines.append(f"{i}. [{issue.get('dimension','')}] {issue.get('description','')}")
            if issue.get("evidence"):
                lines.append(f"   原文：{issue['evidence']}")
            if issue.get("suggestion"):
                lines.append(f"   建议：{issue['suggestion']}")
        lines.append("")
    if warns:
        lines.append("【建议优化】")
        for i, issue in enumerate(warns, 1):
            lines.append(f"{i}. [{issue.get('dimension','')}] {issue.get('description','')}")
            if issue.get("suggestion"):
                lines.append(f"   建议：{issue['suggestion']}")

    return "\n".join(lines)
