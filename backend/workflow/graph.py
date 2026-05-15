import json
import asyncio
from typing import Annotated

from langgraph.graph import StateGraph, START, END

from agents.base import BaseAgent
from workflow.state import ChapterState

async def write_node(state: ChapterState) -> dict:
    agent = BaseAgent(state["writer_char"])
    events = state.get("events", [])
    events.append({"type": "agent_start", "agent": "writer", "character": state["writer_char"]["name"]})

    prompt = f"""请根据以下信息创作小说章节。

## 世界观设定
{state.get('world_setting', '暂无')}

## 角色设定
{state.get('character_setting', '暂无')}

## 章节大纲（第{state['chapter_number']}章）
{state.get('chapter_outline', '')}

## 前情提要
{state.get('prev_summaries', '这是第一章，无前情提要')}

## 要求
- 请直接输出章节正文，2500-3500字
- 章末留悬念或钩子
- 严格遵守世界观和角色设定
"""

    if state.get("revision_notes"):
        prompt += f"\n## 修改意见（第{state['revision_count']}轮）\n{state['revision_notes']}\n请根据以上意见修改章节。"

    content = await agent.run_text(prompt)
    events.append({"type": "agent_done", "agent": "writer", "character": state["writer_char"]["name"]})
    return {"chapter_content": content, "events": events}

async def peer_review_node(state: ChapterState) -> dict:
    agent = BaseAgent(state["peer_char"])
    events = state.get("events", [])
    events.append({"type": "agent_start", "agent": "peer", "character": state["peer_char"]["name"]})

    prompt = f"""请以同行作家的身份点评以下章节内容。

## 章节大纲
{state.get('chapter_outline', '')}

## 章节正文
{state['chapter_content']}

请从创意、文风、节奏、可读性等角度给出点评和建议，以JSON格式输出：
{{
  "overall": "总体评价（1-10分）",
  "strengths": ["优点1", "优点2"],
  "suggestions": ["建议1", "建议2"],
  "comment": "一段自由的点评文字"
}}"""

    result = await agent.run_json(prompt)
    events.append({"type": "agent_done", "agent": "peer", "character": state["peer_char"]["name"]})
    return {"peer_feedback": result, "events": events}

async def operator_review_node(state: ChapterState) -> dict:
    agent = BaseAgent(state["operator_char"])
    events = state.get("events", [])
    events.append({"type": "agent_start", "agent": "operator", "character": state["operator_char"]["name"]})

    prompt = f"""请以责编/运营的身份评估以下章节。

## 章节大纲
{state.get('chapter_outline', '')}

## 章节正文
{state['chapter_content']}

请从内容把控、节奏、商业可行性角度评估，以JSON格式输出：
{{
  "pacing": "节奏评估（1-10分）",
  "content_quality": "内容质量（1-10分）",
  "commercial_viability": "商业可行性（1-10分）",
  "suggestions": ["建议1", "建议2"],
  "comment": "一段自由的评估文字"
}}"""

    result = await agent.run_json(prompt)
    events.append({"type": "agent_done", "agent": "operator", "character": state["operator_char"]["name"]})
    return {"operator_feedback": result, "events": events}

async def content_review_node(state: ChapterState) -> dict:
    agent = BaseAgent(state["content_reviewer_char"])
    events = state.get("events", [])

    prompt = f"""请以内容编辑的身份审核以下章节。

## 世界观设定
{state.get('world_setting', '暂无')}

## 角色设定
{state.get('character_setting', '暂无')}

## 章节正文
{state['chapter_content']}

请检查一致性、逻辑、角色行为是否合理，以JSON格式输出：
{{
  "decision": "pass或fail",
  "issues": ["问题1（如有）"],
  "reason": "通过或不通过的原因"
}}"""

    result = await agent.run_json(prompt)
    events.append({"type": "review_result", "agent": "content", "data": result})
    return {"content_result": result, "events": events}

async def compliance_review_node(state: ChapterState) -> dict:
    agent = BaseAgent(state["compliance_reviewer_char"])
    events = state.get("events", [])

    prompt = f"""请以平台审核的身份检查以下章节的合规性。

## 章节正文
{state['chapter_content']}

请检查是否包含敏感词、涉黄涉政等内容，以JSON格式输出：
{{
  "decision": "pass或fail",
  "issues": ["违规内容（如有）"],
  "reason": "通过或不通过的原因"
}}"""

    result = await agent.run_json(prompt)
    events.append({"type": "review_result", "agent": "compliance", "data": result})
    return {"compliance_result": result, "events": events}

async def reader_feedback_node(state: ChapterState) -> dict:
    agent = BaseAgent(state["reader_char"])
    events = state.get("events", [])

    prompt = f"""请以目标读者的身份评价以下章节。

## 章节正文
{state['chapter_content']}

请从读者体验角度评价，以JSON格式输出：
{{
  "scores": {{
    "thrill": "爽感（1-10）",
    "anticipation": "期待感（1-10）",
    "freshness": "新鲜感（1-10）",
    "logic": "逻辑性（1-10）",
    "pacing": "节奏感（1-10）"
  }},
  "overall": "综合评分（1-10）",
  "comment": "一段自由的读者评论",
  "would_continue_reading": true
}}"""

    result = await agent.run_json(prompt)
    events.append({"type": "reader_feedback", "data": result})
    return {"reader_result": result, "events": events}

def decide_node(state: ChapterState) -> dict:
    content = state.get("content_result", {})
    compliance = state.get("compliance_result", {})
    events = state.get("events", [])

    hard_fails = []
    soft_notes = []

    if compliance.get("decision") == "fail":
        hard_fails.append(f"[合规] {compliance.get('reason', '合规审查不通过')}")
    if content.get("decision") == "fail":
        hard_fails.append(f"[内容] {content.get('reason', '内容审查不通过')}")

    peer = state.get("peer_feedback", {})
    if peer.get("suggestions"):
        soft_notes.append(f"[同行] {'; '.join(peer['suggestions'][:3])}")

    operator = state.get("operator_feedback", {})
    if operator.get("suggestions"):
        soft_notes.append(f"[运营] {'; '.join(operator['suggestions'][:3])}")

    reader = state.get("reader_result", {})
    if reader.get("comment"):
        soft_notes.append(f"[读者] {reader['comment'][:100]}")

    if hard_fails:
        notes = "必须修改:\n" + "\n".join(hard_fails)
        if soft_notes:
            notes += "\n\n建议:\n" + "\n".join(soft_notes)
        events.append({"type": "decision", "decision": "fail", "notes": notes})
        return {"decision": "fail", "revision_notes": notes, "events": events}

    events.append({"type": "decision", "decision": "pass", "notes": ""})
    return {"decision": "pass", "revision_notes": "", "final_content": state.get("chapter_content", ""), "events": events}

def route_decision(state: ChapterState) -> str:
    if state.get("decision") == "pass":
        return "pass"
    if state.get("revision_count", 0) >= state.get("max_revisions", 2):
        return "force_pass"
    return "fail"

def build_graph() -> StateGraph:
    graph = StateGraph(ChapterState)

    graph.add_node("write", write_node)
    graph.add_node("peer_review", peer_review_node)
    graph.add_node("operator_review", operator_review_node)
    graph.add_node("content_review", content_review_node)
    graph.add_node("compliance_review", compliance_review_node)
    graph.add_node("reader_feedback", reader_feedback_node)
    graph.add_node("decide", decide_node)

    graph.add_edge(START, "write")
    graph.add_edge("write", "peer_review")
    graph.add_edge("peer_review", "operator_review")
    graph.add_edge("operator_review", "content_review")
    graph.add_edge("operator_review", "compliance_review")
    graph.add_edge("operator_review", "reader_feedback")
    graph.add_edge("content_review", "decide")
    graph.add_edge("compliance_review", "decide")
    graph.add_edge("reader_feedback", "decide")

    graph.add_conditional_edges("decide", route_decision, {
        "pass": END,
        "fail": "write",
        "force_pass": END,
    })

    return graph.compile()

chapter_graph = build_graph()
