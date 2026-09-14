"""提示词库 —— 全应用所有 LLM 提示词的集中清单 + 在线编辑。

GET    /api/prompts          分组清单（含 key/是否被自定义/编辑时间）
PUT    /api/prompts/{key}    保存自定义（写 prompt_overrides，调用点即时生效）
DELETE /api/prompts/{key}    恢复代码默认值

清单条目直接 import 代码里的真实常量作默认值；用户编辑存库，
调用方统一走 services/prompt_store.prompt(key, DEFAULT)。
新增提示词时：定义成模块级常量 + 调用点包 prompt() + 在 _entries() 登记一行。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.authors import AUTHORS
from backend.agents.personas import POINT_PERSONAS
from backend.agents import chapter_plan, reviewer, style_editor, chronicle, guide, expert_panel
from backend.api import chat, points, chapter_writing, kg, workspace, assistants, materials
from backend.services import lint, goal, volume_outline, story_web, douyin
from backend.services import prompt_store

router = APIRouter(prefix="/api/prompts")

# 点位代码 → 中文名（与前端导航一致）
_POINT_LABELS = {
    "story_core": "故事核",
    "world_setting": "世界观",
    "character_setting": "核心人物",
    "outline_reverse": "倒推大纲",
    "outline": "正向大纲",
}


def _e(group: str, key: str, node: str, name: str, source: str, text: str, note: str = "",
       editable: bool = True) -> dict:
    return {
        "group": group,
        "key": key,
        "node": node,
        "name": name,
        "source": source,
        "text": text,
        "note": note,
        "chars": len(text),
        "editable": editable,
    }


def _entries() -> list[dict]:
    es: list[dict] = []

    # ---- 创作对话 ----
    es.append(_e(
        "创作对话", "studio.chat", "工作室对话", "创作对话系统提示词（模板）", "backend/api/chat.py",
        chat.STUDIO_CHAT_PROMPT_TEMPLATE,
        "每条消息实时拼装：{style_dna} 注入项目选定作者的文风 DNA（可在「作者设定集」单独改），"
        "{name} 为作者名；后接检索到的项目设定与骨架进度总览",
    ))
    es.append(_e(
        "创作对话", "default.assistant", "普通对话", "默认助手系统提示词", "backend/config.py",
        _config.SYSTEM_PROMPT, "非 studio/点位对话的兜底人格（很少用到）",
    ))
    for a in assistants.BUILTIN_ASSISTANTS:
        es.append(_e(
            "创作对话", f"assistant.builtin.{a['id']}", "可切换助理", f"内置助理：{a['name']}",
            "backend/api/assistants.py", a["system_prompt"],
            a.get("description", "") + "（存在助理表，保存直接写表、对话里即时生效）",
        ))
    es.append(_e(
        "创作对话", "outline.interview", "大纲语音访谈", "访谈主持人系统提示词", "backend/api/chat.py",
        chat.OUTLINE_INTERVIEW_PROMPT, "语音访谈模式：一次一问敲定倒推五问+正向三问",
    ))
    es.append(_e(
        "创作对话", "chat.punctuate", "语音输入", "转写加标点提示词", "backend/api/chat.py",
        chat.PUNCTUATE_PROMPT, "只加标点不改字；失败时原样返回",
    ))

    # ---- 作者设定集 ----
    for key, a in AUTHORS.items():
        es.append(_e(
            "作者设定集", f"author.{key}", f"作者·{a['name']}", f"{a['name']}（{a['label']}）文风 DNA",
            "backend/agents/authors.py", a["style_dna"],
            f"擅长：{a.get('blurb', '')}；参考：{a.get('reference', '')}（key={key}）",
        ))

    # ---- 点位人格 ----
    for point, (persona_name, prompt_text) in POINT_PERSONAS.items():
        es.append(_e(
            "点位人格", f"persona.{point}", _POINT_LABELS.get(point, point),
            f"{persona_name}（点位专属人格）", "backend/agents/personas.py", prompt_text,
        ))
    es.append(_e(
        "点位人格", "guide.system", "全点位", "策划引导系统提示词", "backend/agents/guide.py",
        guide.GUIDE_SYSTEM_PROMPT, "旧点位流程的引导对话人格",
    ))
    es.append(_e(
        "点位人格", "points.summarize", "点位存档", "点位总结系统提示词", "backend/api/points.py",
        points.SUMMARIZE_POINT_SYSTEM_PROMPT, "「总结并存档」：把对话提炼成点位结构化设定",
    ))
    es.append(_e(
        "点位人格", "points.auto_generate", "点位生成", "点位自动生成系统提示词", "backend/api/points.py",
        points.AUTO_GENERATE_SYSTEM_PROMPT, "从模糊创意直接生成完整点位设定（/build 等）",
    ))
    es.append(_e(
        "点位人格", "studio.sort_edit", "studio 分拣", "设定分拣编辑提示词", "backend/api/chat.py",
        chat.SORT_EDIT_PROMPT, "/distill：把新对话按点位归类合并（配合分拣规则 user prompt）",
    ))

    # ---- 专家圆桌 ----
    for i in expert_panel.EXPERTS:
        es.append(_e(
            "专家圆桌", f"expert.{i['key']}", "圆桌成员", f"{i['name']}",
            "backend/agents/expert_panel.py", i["system_prompt"], i.get("perspective", ""),
        ))
    es.append(_e(
        "专家圆桌", "expert.synthesis", "圆桌裁决", "统率者汇总系统提示词", "backend/agents/expert_panel.py",
        expert_panel.LEADER_SYNTHESIS_PROMPT, "汇总各专家意见产出最终结论",
    ))

    # ---- 章节写作流水线 ----
    es.append(_e(
        "章节写作", "chapter.writer", "写章", "执笔通用规则系统提示词", "backend/api/chapter_writing.py",
        chapter_writing.CHAPTER_WRITER_SYSTEM_PROMPT,
        "实际 system = 作者文风 DNA（作者设定集可改）+ 本规则 + 项目上下文",
    ))
    es.append(_e(
        "章节写作", "chapter.plan", "章纲", "章纲生成提示词", "backend/agents/chapter_plan.py",
        chapter_plan.CHAPTER_PLAN_PROMPT, "写章前先产出该章的详细章纲",
    ))
    es.append(_e(
        "章节写作", "chapter.review", "审校", "独立审校系统提示词", "backend/agents/reviewer.py",
        reviewer.REVIEW_PROMPT, "写完的章节对照约束复核，决定是否返工",
    ))
    es.append(_e(
        "章节写作", "chapter.style_edit", "文风修订", "仿人改写系统提示词", "backend/agents/style_editor.py",
        style_editor.STYLE_AUDIT_PROMPT, "把「不像人写的」段落改像人写",
    ))
    es.append(_e(
        "章节写作", "chronicle.update", "编年史", "编年史更新提示词", "backend/agents/chronicle.py",
        chronicle.CHRONICLE_PROMPT, "新章节完成后更新故事编年记录",
    ))
    es.append(_e(
        "章节写作", "workspace.chapter_summary", "章节摘要", "章节摘要提示词", "backend/api/workspace.py",
        workspace.CHAPTER_SUMMARY_PROMPT, "章节浓缩 200-300 字供后续上下文引用",
    ))

    # ---- 大纲与卷纲 ----
    es.append(_e(
        "大纲与卷纲", "volume.outline", "卷纲", "卷纲生成系统提示词", "backend/services/volume_outline.py",
        volume_outline.VOLUME_PROMPT, "基于整本骨架产出 40 章/卷的分卷规划",
    ))
    es.append(_e(
        "大纲与卷纲", "storyweb.summary", "故事网", "章节结构化总结提示词", "backend/services/story_web.py",
        story_web.WEB_PROMPT, "章节 → 结构化 JSON 总结（故事网数据源）",
    ))

    # ---- 工作台辅助 ----
    es.append(_e(
        "工作台辅助", "workspace.sync", "条目同步", "工作台同步系统提示词", "backend/api/workspace.py",
        workspace.SYNC_WORKSPACE_PROMPT, "对比 AI 回复与已有条目，找出需更新的内容",
    ))
    es.append(_e(
        "工作台辅助", "workspace.inspiration", "灵感提取", "灵感整理系统提示词", "backend/api/workspace.py",
        workspace.INSPIRATION_PROMPT, "从用户消息提取创作灵感与设定",
    ))
    es.append(_e(
        "工作台辅助", "workspace.questions", "待确认问题", "关键问题提取提示词", "backend/api/workspace.py",
        workspace.EXTRACT_QUESTIONS_PROMPT, "分析项目状态找出需用户确认的问题",
    ))
    for point, p in workspace.SUMMARIZE_MSG_PROMPTS.items():
        es.append(_e(
            "工作台辅助", f"workspace.summarize.{point}", f"消息总结·{_POINT_LABELS.get(point, point)}",
            f"{_POINT_LABELS.get(point, point)}消息总结提示词", "backend/api/workspace.py", p,
        ))

    # ---- 知识图谱 / 设定检查 / 目标 ----
    es.append(_e(
        "图谱与检查", "kg.extract", "知识图谱", "实体关系抽取系统提示词", "backend/api/kg.py",
        kg.EXTRACT_SYSTEM_PROMPT, "从对话/文本抽取实体、关系、事件构建图谱",
    ))
    es.append(_e(
        "图谱与检查", "lint.system", "一致性检查", "设定一致性检测系统提示词", "backend/services/lint.py",
        lint.LINT_SYSTEM_PROMPT, "全项目设定找矛盾、冲突、缺漏",
    ))
    es.append(_e(
        "图谱与检查", "goal.completeness", "目标·完整性", "完整性分析系统提示词", "backend/services/goal.py",
        goal.COMPLETENESS_SYSTEM_PROMPT, "创作目标第一步：分析项目完整性",
    ))
    es.append(_e(
        "图谱与检查", "goal.plan", "目标·拆解", "步骤拆解系统提示词", "backend/services/goal.py",
        goal.PLAN_SYSTEM_PROMPT, "创作目标第二步：拆解为可执行步骤",
    ))
    es.append(_e(
        "图谱与检查", "goal.execute", "目标·执行", "步骤执行系统提示词", "backend/services/goal.py",
        goal.EXECUTE_SYSTEM_PROMPT, "创作目标第三步：执行单个创作任务",
    ))

    # ---- 素材库 ----
    es.append(_e(
        "素材库", "materials.summary", "热榜", "热点补充信息提示词", "backend/api/materials.py",
        materials.SUMMARY_PROMPT, "给每条热点标题写一句 35 字内补充说明",
    ))
    es.append(_e(
        "素材库", "douyin.comment", "抖音评论区", "评论区提炼系统提示词", "backend/services/douyin.py",
        douyin.DOUYIN_COMMENT_PROMPT, "概括评论区核心观点/争议/情绪",
    ))
    return es


class PromptOverrideBody(BaseModel):
    text: str


# ============================================================
# 热更新层：保存/恢复覆盖时直接改写运行时对象，改完即时生效（无需重启）。
# 常量在其定义模块内被引用（读模块全局），setattr 即生效；
# AUTHORS/EXPERTS/POINT_PERSONAS/SUMMARIZE_MSG_PROMPTS 是共享 dict，
# 就地改成员即可被所有调用点看到。
# ============================================================
import backend.config as _config  # noqa: E402
import backend.api.chat as _chat_mod  # noqa: E402
import backend.api.points as _points_mod  # noqa: E402
import backend.api.chapter_writing as _chapter_writing_mod  # noqa: E402
import backend.api.workspace as _workspace_mod  # noqa: E402
import backend.api.kg as _kg_mod  # noqa: E402
import backend.api.materials as _materials_mod  # noqa: E402
import backend.services.lint as _lint_mod  # noqa: E402
import backend.services.goal as _goal_mod  # noqa: E402
import backend.services.volume_outline as _volume_mod  # noqa: E402
import backend.services.story_web as _storyweb_mod  # noqa: E402
import backend.services.douyin as _douyin_mod  # noqa: E402

# key → 代码默认文本快照（导入时拍下，恢复默认时用）
_ORIGINALS: dict[str, str] = {e["key"]: e["text"] for e in _entries()}

_MODULE_ATTR_PATCH: dict[str, list[tuple[object, str]]] = {
    "studio.chat": [(_chat_mod, "STUDIO_CHAT_PROMPT_TEMPLATE")],
    # chat 顶层 from config import SYSTEM_PROMPT，两处绑定都要改
    "default.assistant": [(_config, "SYSTEM_PROMPT"), (_chat_mod, "SYSTEM_PROMPT")],
    "outline.interview": [(_chat_mod, "OUTLINE_INTERVIEW_PROMPT")],
    "chat.punctuate": [(_chat_mod, "PUNCTUATE_PROMPT")],
    "studio.sort_edit": [(_chat_mod, "SORT_EDIT_PROMPT")],
    "points.summarize": [(_points_mod, "SUMMARIZE_POINT_SYSTEM_PROMPT")],
    # chat 内对它的 import 在函数体内，每次调用重绑，补 points 一处即可
    "points.auto_generate": [(_points_mod, "AUTO_GENERATE_SYSTEM_PROMPT")],
    "chapter.writer": [(_chapter_writing_mod, "CHAPTER_WRITER_SYSTEM_PROMPT")],
    "chapter.plan": [(chapter_plan, "CHAPTER_PLAN_PROMPT")],
    "chapter.review": [(reviewer, "REVIEW_PROMPT")],
    "chapter.style_edit": [(style_editor, "STYLE_AUDIT_PROMPT")],
    "chronicle.update": [(chronicle, "CHRONICLE_PROMPT")],
    "guide.system": [(guide, "GUIDE_SYSTEM_PROMPT")],
    "expert.synthesis": [(expert_panel, "LEADER_SYNTHESIS_PROMPT")],
    "workspace.sync": [(_workspace_mod, "SYNC_WORKSPACE_PROMPT")],
    "workspace.inspiration": [(_workspace_mod, "INSPIRATION_PROMPT")],
    "workspace.questions": [(_workspace_mod, "EXTRACT_QUESTIONS_PROMPT")],
    "workspace.chapter_summary": [(_workspace_mod, "CHAPTER_SUMMARY_PROMPT")],
    "kg.extract": [(_kg_mod, "EXTRACT_SYSTEM_PROMPT")],
    "lint.system": [(_lint_mod, "LINT_SYSTEM_PROMPT")],
    "goal.completeness": [(_goal_mod, "COMPLETENESS_SYSTEM_PROMPT")],
    "goal.plan": [(_goal_mod, "PLAN_SYSTEM_PROMPT")],
    "goal.execute": [(_goal_mod, "EXECUTE_SYSTEM_PROMPT")],
    "volume.outline": [(_volume_mod, "VOLUME_PROMPT")],
    "storyweb.summary": [(_storyweb_mod, "WEB_PROMPT")],
    "materials.summary": [(_materials_mod, "SUMMARY_PROMPT")],
    "douyin.comment": [(_douyin_mod, "DOUYIN_COMMENT_PROMPT")],
}


def _apply_patch(key: str, text: str) -> None:
    """把文本写进运行时对象（模块常量 / 共享 dict 成员）。"""
    if key in _MODULE_ATTR_PATCH:
        for mod, attr in _MODULE_ATTR_PATCH[key]:
            setattr(mod, attr, text)
        return
    if key.startswith("author."):
        AUTHORS[key.split(".", 1)[1]]["style_dna"] = text
        return
    if key.startswith("persona."):
        pt = key.split(".", 1)[1]
        if pt in POINT_PERSONAS:
            POINT_PERSONAS[pt] = (POINT_PERSONAS[pt][0], text)
        return
    if key.startswith("expert."):
        ek = key.split(".", 1)[1]
        for x in expert_panel.EXPERTS:
            if x["key"] == ek:
                x["system_prompt"] = text
        return
    if key.startswith("workspace.summarize."):
        pt = key.rsplit(".", 1)[1]
        if pt in _workspace_mod.SUMMARIZE_MSG_PROMPTS:
            _workspace_mod.SUMMARIZE_MSG_PROMPTS[pt] = text
        return


async def apply_saved_overrides() -> int:
    """启动时重放 DB 里的全部覆盖（重启后恢复自定义）。返回应用条数。"""
    overrides = await prompt_store.all_overrides()
    for key, text in overrides.items():
        _apply_patch(key, text)
    return len(overrides)


def _find_entry(entries: list[dict], key: str) -> dict | None:
    return next((e for e in entries if e["key"] == key), None)


@router.get("")
async def list_prompts():
    entries = _entries()
    overrides = await prompt_store.all_overrides()
    overridden_count = 0
    # 内置助理的真身在 assistants 表：展示库里的实时值，与代码默认不同则视为已自定义
    db = None
    for e in entries:
        if e["key"].startswith("assistant.builtin."):
            from backend.database import get_db as _gdb, fetch_one as _fone
            db = db or await _gdb()
            aid = e["key"].split("assistant.builtin.", 1)[1]
            row = await _fone(db, "SELECT system_prompt, updated_at FROM assistants WHERE id = ?", (aid,))
            if row and row["system_prompt"]:
                e["text"] = row["system_prompt"]
                e["chars"] = len(row["system_prompt"])
                e["overridden"] = row["system_prompt"] != _ORIGINALS.get(e["key"])
                e["edited_at"] = row["updated_at"]
                if e["overridden"]:
                    overridden_count += 1
                continue
        ov = overrides.get(e["key"])
        if ov is not None:
            e["text"] = ov
            e["chars"] = len(ov)
            e["overridden"] = True
            overridden_count += 1
        else:
            e["overridden"] = False

    # 覆盖条目（非助理）的编辑时间
    from backend.database import get_db as _gdb, fetch_all as _fall
    if any(e["overridden"] and not e["key"].startswith("assistant.builtin.") for e in entries):
        db = db or await _gdb()
        rows = await _fall(db, "SELECT key, updated_at FROM prompt_overrides")
        stamps = {r["key"]: r["updated_at"] for r in rows}
        for e in entries:
            if e["overridden"] and not e["key"].startswith("assistant.builtin."):
                e["edited_at"] = stamps.get(e["key"])
    for e in entries:
        e.setdefault("edited_at", None)

    groups: list[dict] = []
    for e in entries:
        if not groups or groups[-1]["group"] != e["group"]:
            groups.append({"group": e["group"], "count": 0})
        groups[-1]["count"] += 1
    return {"total": len(entries), "overridden": overridden_count, "groups": groups, "items": entries}


def _builtin_assistant_default(key: str) -> tuple[str, str]:
    """(assistant_id, 代码默认文本)"""
    aid = key.split("assistant.builtin.", 1)[1]
    for a in assistants.BUILTIN_ASSISTANTS:
        if a["id"] == aid:
            return aid, a["system_prompt"]
    raise HTTPException(status_code=404, detail=f"未知的助理：{key}")


async def _current_effective(key: str, entry: dict) -> str:
    """保存/恢复前的现行文本（用于入档历史）。"""
    if key.startswith("assistant.builtin."):
        from backend.database import get_db as _gdb, fetch_one as _fone
        aid, _default = _builtin_assistant_default(key)
        row = await _fone(await _gdb(), "SELECT system_prompt FROM assistants WHERE id = ?", (aid,))
        return (row and row["system_prompt"]) or _default
    ov = (await prompt_store.all_overrides()).get(key)
    return ov if ov is not None else _ORIGINALS.get(key, entry["text"])


async def _write_assistant(key: str, text: str) -> None:
    """内置助理：直接写 assistants 表（对话每请求读库，即时生效）。"""
    from backend.database import get_db as _gdb
    aid, _ = _builtin_assistant_default(key)
    db = await _gdb()
    await db.execute(
        "UPDATE assistants SET system_prompt = ?, updated_at = datetime('now') WHERE id = ?",
        (text, aid),
    )
    await db.commit()


@router.put("/{key}")
async def save_prompt_override(key: str, body: PromptOverrideBody):
    entries = _entries()
    entry = _find_entry(entries, key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"未知的提示词：{key}")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="提示词不能为空")

    # 旧版入档：任何一次修改都不丢历史
    current = await _current_effective(key, entry)
    if current != text:
        await prompt_store.add_history(key, current)

    if key.startswith("assistant.builtin."):
        await _write_assistant(key, text)
    else:
        await prompt_store.set_override(key, text)
        _apply_patch(key, text)
    return {"ok": True, "key": key, "chars": len(text)}


@router.delete("/{key}")
async def reset_prompt_override(key: str):
    entries = _entries()
    entry = _find_entry(entries, key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"未知的提示词：{key}")

    # 恢复前同样入档当前版本
    current = await _current_effective(key, entry)
    if current != _ORIGINALS.get(key):
        await prompt_store.add_history(key, current)

    if key.startswith("assistant.builtin."):
        aid, default = _builtin_assistant_default(key)
        await _write_assistant(key, default)
    else:
        await prompt_store.clear_override(key)
        _apply_patch(key, _ORIGINALS.get(key, entry["text"]))
    return {"ok": True, "key": key, "cleared": True}


@router.get("/{key}/history")
async def prompt_history(key: str):
    entries = _entries()
    if not _find_entry(entries, key):
        raise HTTPException(status_code=404, detail=f"未知的提示词：{key}")
    rows = await prompt_store.get_history(key)
    for r in rows:
        r["chars"] = len(r["text"])
        r["preview"] = r["text"].strip().replace("\n", " ")[:64]
    return {"key": key, "items": rows}
