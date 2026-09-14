"""提示词库 —— 全应用所有 LLM 提示词的集中清单。

GET /api/prompts 返回分组条目（节点/名称/代码位置/全文），供前端「提示词库」页面
统一查看、复制与优化。所有条目直接 import 代码里的真实常量，改代码即改清单，
不存在第二份拷贝。新增提示词时：定义成模块级常量 + 在 _entries() 里登记一行。
"""
from fastapi import APIRouter

from backend.config import SYSTEM_PROMPT
from backend.agents.authors import AUTHORS
from backend.agents.personas import POINT_PERSONAS
from backend.agents import chapter_plan, reviewer, style_editor, chronicle, guide, expert_panel
from backend.api import chat, points, chapter_writing, kg, workspace, assistants, materials
from backend.services import lint, goal, volume_outline, story_web, douyin

router = APIRouter(prefix="/api/prompts")

# 点位代码 → 中文名（与前端导航一致）
_POINT_LABELS = {
    "story_core": "故事核",
    "world_setting": "世界观",
    "character_setting": "核心人物",
    "outline_reverse": "倒推大纲",
    "outline": "正向大纲",
}


def _e(group: str, node: str, name: str, source: str, text: str, note: str = "") -> dict:
    return {
        "group": group,
        "node": node,
        "name": name,
        "source": source,
        "text": text,
        "note": note,
        "chars": len(text),
    }


def _entries() -> list[dict]:
    es: list[dict] = []

    # ---- 创作对话 ----
    es.append(_e(
        "创作对话", "工作室对话", "创作对话系统提示词（模板）", "backend/api/chat.py",
        chat.STUDIO_CHAT_PROMPT_TEMPLATE,
        "每条消息实时拼装：{style_dna} 注入项目选定作者的文风 DNA，{name} 为作者名；"
        "后接检索到的项目设定与骨架进度总览",
    ))
    es.append(_e(
        "创作对话", "普通对话", "默认助手系统提示词", "backend/config.py",
        SYSTEM_PROMPT, "非 studio/点位对话的兜底人格（很少用到）",
    ))
    for a in assistants.BUILTIN_ASSISTANTS:
        es.append(_e(
            "创作对话", "可切换助理", f"内置助理：{a['name']}", "backend/api/assistants.py",
            a["system_prompt"], a.get("description", ""),
        ))
    es.append(_e(
        "创作对话", "大纲语音访谈", "访谈主持人系统提示词", "backend/api/chat.py",
        chat.OUTLINE_INTERVIEW_PROMPT, "语音访谈模式：一次一问敲定倒推五问+正向三问",
    ))
    es.append(_e(
        "创作对话", "语音输入", "转写加标点提示词", "backend/api/chat.py",
        chat.PUNCTUATE_PROMPT, "只加标点不改字；失败时原样返回",
    ))

    # ---- 作者设定集 ----
    for key, a in AUTHORS.items():
        es.append(_e(
            "作者设定集", f"作者·{a['name']}", f"{a['name']}（{a['label']}）文风 DNA",
            "backend/agents/authors.py",
            a["style_dna"],
            f"擅长：{a.get('blurb', '')}；参考：{a.get('reference', '')}（key={key}）",
        ))

    # ---- 点位人格 ----
    for point, (persona_name, prompt) in POINT_PERSONAS.items():
        es.append(_e(
            "点位人格", _POINT_LABELS.get(point, point), f"{persona_name}（点位专属人格）",
            "backend/agents/personas.py", prompt,
        ))
    es.append(_e(
        "点位人格", "全点位", "策划引导系统提示词", "backend/agents/guide.py",
        guide.GUIDE_SYSTEM_PROMPT, "旧点位流程的引导对话人格",
    ))
    es.append(_e(
        "点位人格", "点位存档", "点位总结系统提示词", "backend/api/points.py",
        points.SUMMARIZE_POINT_SYSTEM_PROMPT, "「总结并存档」：把对话提炼成点位结构化设定",
    ))
    es.append(_e(
        "点位人格", "点位生成", "点位自动生成系统提示词", "backend/api/points.py",
        points.AUTO_GENERATE_SYSTEM_PROMPT, "从模糊创意直接生成完整点位设定（/build 等）",
    ))
    es.append(_e(
        "点位人格", "studio 分拣", "设定分拣编辑提示词", "backend/api/chat.py",
        chat.SORT_EDIT_PROMPT, "/distill：把新对话按点位归类合并（配合分拣规则 user prompt）",
    ))

    # ---- 专家圆桌 ----
    for i in expert_panel.EXPERTS:
        es.append(_e(
            "专家圆桌", "圆桌成员", f"{i['name']}", "backend/agents/expert_panel.py",
            i["system_prompt"], i.get("perspective", ""),
        ))
    es.append(_e(
        "专家圆桌", "圆桌裁决", "统率者汇总系统提示词", "backend/agents/expert_panel.py",
        expert_panel.LEADER_SYNTHESIS_PROMPT, "汇总各专家意见产出最终结论",
    ))

    # ---- 章节写作流水线 ----
    es.append(_e(
        "章节写作", "写章", "执笔通用规则系统提示词", "backend/api/chapter_writing.py",
        chapter_writing.CHAPTER_WRITER_SYSTEM_PROMPT,
        "实际 system = 作者文风 DNA + 本规则 + 项目上下文",
    ))
    es.append(_e(
        "章节写作", "章纲", "章纲生成提示词", "backend/agents/chapter_plan.py",
        chapter_plan.CHAPTER_PLAN_PROMPT, "写章前先产出该章的详细章纲",
    ))
    es.append(_e(
        "章节写作", "审校", "独立审校系统提示词", "backend/agents/reviewer.py",
        reviewer.REVIEW_PROMPT, "写完的章节对照约束复核，决定是否返工",
    ))
    es.append(_e(
        "章节写作", "文风修订", "仿人改写系统提示词", "backend/agents/style_editor.py",
        style_editor.STYLE_AUDIT_PROMPT, "把「不像人写的」段落改像人写",
    ))
    es.append(_e(
        "章节写作", "编年史", "编年史更新提示词", "backend/agents/chronicle.py",
        chronicle.CHRONICLE_PROMPT, "新章节完成后更新故事编年记录",
    ))
    es.append(_e(
        "章节写作", "章节摘要", "章节摘要提示词", "backend/api/workspace.py",
        workspace.CHAPTER_SUMMARY_PROMPT, "章节浓缩 200-300 字供后续上下文引用",
    ))

    # ---- 大纲与卷纲 ----
    es.append(_e(
        "大纲与卷纲", "卷纲", "卷纲生成系统提示词", "backend/services/volume_outline.py",
        volume_outline.VOLUME_PROMPT, "基于整本骨架产出 40 章/卷的分卷规划",
    ))
    es.append(_e(
        "大纲与卷纲", "故事网", "章节结构化总结提示词", "backend/services/story_web.py",
        story_web.WEB_PROMPT, "章节 → 结构化 JSON 总结（故事网数据源）",
    ))

    # ---- 工作台辅助 ----
    es.append(_e(
        "工作台辅助", "条目同步", "工作台同步系统提示词", "backend/api/workspace.py",
        workspace.SYNC_WORKSPACE_PROMPT, "对比 AI 回复与已有条目，找出需更新的内容",
    ))
    es.append(_e(
        "工作台辅助", "灵感提取", "灵感整理系统提示词", "backend/api/workspace.py",
        workspace.INSPIRATION_PROMPT, "从用户消息提取创作灵感与设定",
    ))
    es.append(_e(
        "工作台辅助", "待确认问题", "关键问题提取提示词", "backend/api/workspace.py",
        workspace.EXTRACT_QUESTIONS_PROMPT, "分析项目状态找出需用户确认的问题",
    ))
    for point, p in workspace.SUMMARIZE_MSG_PROMPTS.items():
        es.append(_e(
            "工作台辅助", f"消息总结·{_POINT_LABELS.get(point, point)}",
            f"{_POINT_LABELS.get(point, point)}消息总结提示词", "backend/api/workspace.py", p,
        ))

    # ---- 知识图谱 / 设定检查 / 目标 ----
    es.append(_e(
        "图谱与检查", "知识图谱", "实体关系抽取系统提示词", "backend/api/kg.py",
        kg.EXTRACT_SYSTEM_PROMPT, "从对话/文本抽取实体、关系、事件构建图谱",
    ))
    es.append(_e(
        "图谱与检查", "一致性检查", "设定一致性检测系统提示词", "backend/services/lint.py",
        lint.LINT_SYSTEM_PROMPT, "全项目设定找矛盾、冲突、缺漏",
    ))
    es.append(_e(
        "图谱与检查", "目标·完整性", "完整性分析系统提示词", "backend/services/goal.py",
        goal.COMPLETENESS_SYSTEM_PROMPT, "创作目标第一步：分析项目完整性",
    ))
    es.append(_e(
        "图谱与检查", "目标·拆解", "步骤拆解系统提示词", "backend/services/goal.py",
        goal.PLAN_SYSTEM_PROMPT, "创作目标第二步：拆解为可执行步骤",
    ))
    es.append(_e(
        "图谱与检查", "目标·执行", "步骤执行系统提示词", "backend/services/goal.py",
        goal.EXECUTE_SYSTEM_PROMPT, "创作目标第三步：执行单个创作任务",
    ))

    # ---- 素材库 ----
    es.append(_e(
        "素材库", "热榜", "热点补充信息提示词", "backend/api/materials.py",
        materials.SUMMARY_PROMPT, "给每条热点标题写一句 35 字内补充说明",
    ))
    es.append(_e(
        "素材库", "抖音评论区", "评论区提炼系统提示词", "backend/services/douyin.py",
        douyin.DOUYIN_COMMENT_PROMPT, "概括评论区核心观点/争议/情绪",
    ))
    return es


@router.get("")
async def list_prompts():
    entries = _entries()
    groups: list[dict] = []
    for e in entries:
        if not groups or groups[-1]["group"] != e["group"]:
            groups.append({"group": e["group"], "count": 0})
        groups[-1]["count"] += 1
    return {"total": len(entries), "groups": groups, "items": entries}
