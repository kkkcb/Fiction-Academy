# -*- coding: utf-8 -*-
"""同一章纲同一上下文：思考模式 vs 非思考模式 各生成一章，对比输出。"""
import asyncio
import io
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

PID = "7df594d9-ed04-446b-b13d-a6e356fad06f"
CH = 1  # 用第1章的章纲做对照


async def build_context():
    from backend.database import get_db, fetch_all, fetch_one
    from backend.api.chapter_writing import (
        SKELETON_TYPES, _format_skeleton_for_plan, _load_recent_chapter_summary, CHAPTER_WRITER_SYSTEM_PROMPT,
    )
    from backend.services.kg import build_kg_injection

    db = await get_db()
    skeleton = await fetch_all(
        db,
        f"""SELECT item_type, title, content, metadata FROM workspace_items
            WHERE project_id = ? AND item_type IN ({','.join('?' * len(SKELETON_TYPES))})
              AND status IN ('finalized', 'locked')""",
        (PID, *SKELETON_TYPES),
    )
    plan_row = await fetch_one(
        db,
        """SELECT content FROM workspace_items WHERE project_id = ? AND item_type='chapter_plan' AND chapter_number = ?""",
        (PID, CH),
    )
    kg = await build_kg_injection(PID, scene="write_chapter", chapter=CH)
    blocks = [
        "## 骨架约束\n" + _format_skeleton_for_plan(skeleton),
        f"## 本章章纲（第{CH}章）\n{plan_row['content']}",
    ]
    if kg:
        blocks.append("## 既定设定（知识图谱）\n" + kg)
    system = CHAPTER_WRITER_SYSTEM_PROMPT + "\n\n" + "\n\n".join(blocks)
    messages = [{"role": "user", "content": "请依据以上全部约束，写出本章正文。"}]
    return system, messages


async def run(mode: str, disable_thinking: bool, system: str, messages: list) -> dict:
    from backend.agents.base import chat_stream
    t0 = time.time()
    content = ""
    reasoning = 0
    async for kind, chunk in chat_stream(messages, system_prompt=system, temperature=1.0,
                                         disable_thinking=disable_thinking):
        if kind == "reasoning":
            reasoning += len(chunk)
        else:
            content += chunk
    return {"mode": mode, "content": content, "reasoning": reasoning, "secs": round(time.time() - t0)}


def stats(text: str) -> str:
    paras = [p for p in text.split("\n") if p.strip()]
    dialogue = sum(1 for p in paras if "“" in p or "”" in p)
    return f"{len(text)}字 | {len(paras)}段 | 含对话段落 {dialogue}（{dialogue * 100 // max(len(paras), 1)}%）"


async def main():
    system, messages = await build_context()
    print("上下文就绪：system", len(system), "字符\n")

    a = await run("非思考", True, system, messages)
    print(f"[非思考] {a['secs']}s | {stats(a['content'])} | 思考字符 {a['reasoning']}")
    io.open("compare_no_thinking.txt", "w", encoding="utf-8").write(a["content"])

    b = await run("思考", False, system, messages)
    print(f"[思考]   {b['secs']}s | {stats(b['content'])} | 思考字符 {b['reasoning']}")
    io.open("compare_thinking.txt", "w", encoding="utf-8").write(b["content"])

    for label, r in (("非思考", a), ("思考", b)):
        paras = [p for p in r["content"].split("\n") if p.strip()]
        print(f"\n===== {label} 开头 =====\n{paras[0][:100] if paras else ''}")
        print(f"===== {label} 结尾 =====\n{(paras[-1] if paras else '')[:100]}")

asyncio.run(main())
