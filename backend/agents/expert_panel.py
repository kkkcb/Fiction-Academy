"""专家圆桌会诊 · 故事核专家统率全局，五位专家分工协作 + 主线策划最终裁决"""
import json
import asyncio
import logging
from backend.agents.base import chat_stream

logger = logging.getLogger(__name__)

EXPERTS = [
    {
        "key": "story_core",
        "name": "主线策划",
        "perspective": "故事核 / 商业定位（统率者）",
        "is_leader": True,
        "system_prompt": """你是【主线策划】，本次专家圆桌会议的统率者，也是故事核专家。
你掌握着整部作品的灵魂——核心爽点、商业定位与核心矛盾，一切设定都要服务于它。
你的视角：
- 这个设定最核心的"爽点"在哪？读者为什么要追？
- 一句话核心是否清晰、是否独特、是否有传播力？
- 商业定位对不对（目标读者群、类型标签、竞品差异化）
- 核心矛盾冲突够不够强？
发言要求：直击要害，给出具体判断和可操作建议，不要泛泛而谈。""",
    },
    {
        "key": "world_setting",
        "name": "世界观架构师",
        "perspective": "力量体系 / 世界规则 / 金手指",
        "is_leader": False,
        "system_prompt": """你是【世界观架构师】，专精于构建自洽、有层次的世界观体系。
你的视角：
- 力量体系（修炼等级/能力分级）是否平衡？有没有天花板和限制？
- 金手指有没有破绽？会不会导致后续无法控制？
- 世界规则是否自洽？社会结构、势力分布是否合理？
- 有没有留出"成长空间"让主角逐步变强？
发言要求：关注逻辑闭环和设定一致性，指出潜在的崩坏风险。""",
    },
    {
        "key": "character_setting",
        "name": "人物塑造师",
        "perspective": "角色动机 / 人设弧线 / 情感共鸣",
        "is_leader": False,
        "system_prompt": """你是【人物塑造师】，擅长设计立体、有记忆点的角色。
你的视角：
- 角色的核心欲望和内在动机是否成立？
- 人设有没有"反差感"和"记忆点"？
- 成长弧线是否自然？会不会OOC（人设崩坏）？
- 配角是否各司其职、不抢主角风头？
发言要求：关注角色的真实感和情感张力，让读者能共情。""",
    },
    {
        "key": "outline_reverse",
        "name": "逆向架构师",
        "perspective": "结局倒推 / 关键转折 / 因果链",
        "is_leader": False,
        "system_prompt": """你是【逆向架构师】，擅长从终点倒推整个故事的骨架。
你的视角：
- 如果这个故事要完美收尾，结局应该长什么样？
- 从起点到终点，必须经过哪几个关键转折？
- 因果链是否闭环？每件事是否有"种子"（前面的铺垫）？
- 有没有"一条道走到黑"的风险？哪里可能写不下去？
发言要求：关注结构的完整性和逻辑闭环，确保一切有因有果。""",
    },
    {
        "key": "outline",
        "name": "节奏导演",
        "perspective": "三幕结构 / 节奏把控 / 卷次划分",
        "is_leader": False,
        "system_prompt": """你是【节奏导演】，专精于故事节奏和结构编排。
你的视角：
- 三幕结构是否平衡？起承转合是否流畅？
- 每一卷的高潮点放在哪里？有没有"爽点密度"？
- 节奏会不会拖沓或太赶？哪里需要留白？
- 开篇的黄金三章能不能抓住读者？
发言要求：关注阅读体验和节奏张力，让读者欲罢不能。""",
    },
]

LEADER = EXPERTS[0]

LEADER_SYNTHESIS_PROMPT = """你是【主线策划】，本次专家圆桌会议的统率者，也是故事核专家与最终裁决者。
你掌握着整部作品的灵魂方向——核心爽点与商业价值是最高准绳，一切设定都必须服务于它。

作为统率者，你的最终裁决任务：
1. 综合所有专家的发言，但以「故事核」为最高准绳来裁决
2. 当专家意见冲突时，由你拍板：哪种方案更能强化故事灵魂、更接近读者的爽点
3. 产出一套完整、自洽、可直接落地的综合设定方案

输出要求（Markdown，结构清晰）：
- 「## 故事核定调」：用一句话点明这个故事的核心爽点和商业灵魂
- 「## 圆桌共识」：提炼所有专家达成一致的核心结论
- 「## 关键裁决」：列出有争议的地方及你的最终判断（说明为何这样取舍）
- 「## 执行方案」：给出可直接落地的完整设定
- 语言专业精炼，提炼升华，不要照搬专家原话"""


async def run_expert_panel(idea: str, background: str, point_intro: str, point_label: str, rounds: int = 2):
    """运行专家圆桌讨论：统率者定调 → 各专家响应 → 多轮交锋 → 统率者最终裁决。

    故事核专家（主线策划）统率全局：开场定调 + 最终裁决。
    Yields: dict 事件，包含 phase/leader/expert/round/name/perspective/content 等字段。

    客户端断开导致生成器被提前关闭时，finally 会取消所有仍在运行的
    专家任务，避免孤儿 LLM 调用继续烧 token。
    """
    history = {}
    running_tasks: set[asyncio.Task] = set()
    try:
        # ===== Phase 0：统率者定调 =====
        opening_prompt = f"""## 讨论主题
作者正在确定【{point_label}】，提出了以下想法：

{idea}

## 已确定的背景设定
{background}

## 该点位的定义
{point_intro}

你是本次圆桌会议的统率者。请先给出【定调】，为接下来的讨论确立方向：
- 一句话点明这个想法的核心爽点和商业潜力
- 指出最关键的方向性问题（最多2个）
- 为讨论定下基调

控制在 150 字以内，开门见山。"""

        leader_opening = ""
        yield {"phase": "leader_start", "name": LEADER["name"], "perspective": LEADER["perspective"]}
        try:
            async for kind, chunk in chat_stream(
                messages=[{"role": "user", "content": opening_prompt}],
                system_prompt=LEADER["system_prompt"],
                temperature=0.75,
            ):
                if kind == "reasoning":
                    yield {"phase": "leader_thinking_chunk", "chunk": chunk}
                else:
                    leader_opening += chunk
                    yield {"phase": "leader_chunk", "chunk": chunk}
        except Exception as e:
            logger.warning("[expert_panel] leader opening failed: %s", e)
            leader_opening = f"（统率者暂时离线：{e}）"
            yield {"phase": "leader_chunk", "chunk": leader_opening}
        history.setdefault(LEADER["key"], {})[1] = leader_opening
        yield {
            "phase": "leader_done",
            "name": LEADER["name"],
            "perspective": LEADER["perspective"],
            "content": leader_opening,
        }

        others = [e for e in EXPERTS if not e.get("is_leader")]

        # ===== Round 1：各专家响应统率者定调 =====
        yield {"phase": "round_start", "round": 1}
        queue = asyncio.Queue()
        for e in others:
            prompt = f"""## 讨论主题
作者正在确定【{point_label}】，想法：

{idea}

## 已确定的背景设定
{background}

## 该点位的定义
{point_intro}

## 统率者定调（主线策划）
{leader_opening}

请从你的专业视角，回应统率者的定调并分析这个想法：
- 指出亮点和潜力
- 点出隐患和风险
- 给出你的专业建议
控制在 200 字以内，直击要害。"""
            t = asyncio.create_task(_stream_expert(e, prompt, 1, queue))
            running_tasks.add(t)
            t.add_done_callback(running_tasks.discard)

        r1_done = 0
        r1_total = len(others)
        while r1_done < r1_total:
            event = await queue.get()
            if event["phase"] == "expert_done":
                history.setdefault(event["expert"], {})[1] = event["content"]
                r1_done += 1
            yield event

        # ===== Round 2：全员交锋（含统率者本人）=====
        yield {"phase": "round_start", "round": 2}
        r1_summary = "\n\n".join(
            f"【{e['name']}】{history.get(e['key'], {}).get(1, '')}" for e in EXPERTS
        )
        queue2 = asyncio.Queue()
        for e in EXPERTS:
            my_prev = history.get(e["key"], {}).get(1, "")
            prompt = f"""## 你的第一轮发言
{my_prev}

## 第一轮所有发言
{r1_summary}

现在进入第二轮。请回应其他专家的观点：
- 他们说对了吗？有没有你遗漏的风险或机会？
- 有没有需要补充或修正的地方？
- 你坚持什么，让步什么？
控制在 200 字以内。"""
            t = asyncio.create_task(_stream_expert(e, prompt, 2, queue2))
            running_tasks.add(t)
            t.add_done_callback(running_tasks.discard)

        r2_done = 0
        r2_total = len(EXPERTS)
        while r2_done < r2_total:
            event = await queue2.get()
            if event["phase"] == "expert_done":
                history.setdefault(event["expert"], {})[2] = event["content"]
                r2_done += 1
            yield event

        # ===== 最终裁决：统率者汇总 =====
        all_speech_parts = []
        for e in EXPERTS:
            r1 = history.get(e["key"], {}).get(1, "")
            r2 = history.get(e["key"], {}).get(2, "")
            block = f"### {e['name']}（{e['perspective']}）\n第1轮：{r1}"
            if r2:
                block += f"\n第2轮：{r2}"
            all_speech_parts.append(block)
        all_speech = "\n\n".join(all_speech_parts)

        synthesis_prompt = f"""## 讨论主题
作者要确定【{point_label}】，核心想法：{idea}

## 已确定的背景
{background}

## 五位专家的讨论记录（你是统率者，第1轮即你的定调）
{all_speech}

作为统率者，请综合以上讨论，对【{point_label}】做出最终裁决，产出一套完整、自洽、可执行的设定方案。"""

        yield {"phase": "summary_start"}
        summary = ""
        try:
            async for kind, chunk in chat_stream(
                messages=[{"role": "user", "content": synthesis_prompt}],
                system_prompt=LEADER_SYNTHESIS_PROMPT,
                temperature=0.6,
            ):
                if kind == "reasoning":
                    yield {"phase": "summary_thinking_chunk", "chunk": chunk}
                else:
                    summary += chunk
                    yield {"phase": "summary_chunk", "chunk": chunk}
        except Exception as e:
            logger.warning("[expert_panel] summary failed: %s", e)
            summary = f"（裁决生成失败：{e}）"
            yield {"phase": "summary_chunk", "chunk": summary}

        yield {"phase": "summary", "content": summary}

        rounds_data = []
        round_labels = {1: "响应定调", 2: "交锋"}
        for round_num in range(1, rounds + 1):
            entries = []
            for e in EXPERTS:
                content = history.get(e["key"], {}).get(round_num, "")
                if content:
                    entries.append({
                        "name": e["name"],
                        "perspective": e["perspective"],
                        "content": content,
                        "is_leader": bool(e.get("is_leader")),
                    })
            if entries:
                rounds_data.append({
                    "round": round_num,
                    "label": round_labels.get(round_num, f"第{round_num}轮"),
                    "entries": entries,
                })

        record = {
            "kind": "consult_record",
            "leader": {
                "name": LEADER["name"],
                "perspective": LEADER["perspective"],
                "content": leader_opening,
            },
            "rounds": rounds_data,
            "summary": summary,
        }

        yield {"phase": "record", "record": record}

        yield {"phase": "done"}
    finally:
        # 生成器被提前关闭（客户端断开/异常）时，取消所有仍在跑的专家任务
        for t in list(running_tasks):
            if not t.done():
                t.cancel()
        if running_tasks:
            logger.info("[expert_panel] cancelled %d orphan task(s)", len(running_tasks))


async def _stream_solo(messages, system_prompt, temperature, event_meta, queue, start_phase, chunk_phase, thinking_phase, done_phase):
    """流式消费单次 LLM 调用，逐 chunk 推入 queue，返回 (完整文本, 是否含思考)。"""
    await queue.put({"phase": start_phase, **event_meta})
    full = ""
    has_reasoning = False
    try:
        async for kind, chunk in chat_stream(messages=messages, system_prompt=system_prompt, temperature=temperature):
            if kind == "reasoning":
                has_reasoning = True
                await queue.put({"phase": thinking_phase, **event_meta, "chunk": chunk})
            else:
                full += chunk
                await queue.put({"phase": chunk_phase, **event_meta, "chunk": chunk})
    except Exception as e:
        logger.warning("[expert_panel] stream failed (%s): %s", event_meta.get("name", "?"), e)
        full = f"（生成失败：{e}）"
        await queue.put({"phase": chunk_phase, **event_meta, "chunk": full})
    await queue.put({"phase": done_phase, **event_meta, "content": full, "has_reasoning": has_reasoning})
    return full, has_reasoning


async def _stream_expert(expert: dict, prompt: str, round_num: int, queue: asyncio.Queue):
    """流式消费单个专家发言，逐 chunk 推入 queue，返回完整内容。"""
    meta = {
        "round": round_num,
        "expert": expert["key"],
        "name": expert["name"],
        "perspective": expert["perspective"],
        "is_leader": bool(expert.get("is_leader")),
    }
    result = await _stream_solo(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=expert["system_prompt"],
        temperature=0.75,
        event_meta=meta,
        queue=queue,
        start_phase="expert_start",
        chunk_phase="expert_chunk",
        thinking_phase="expert_thinking_chunk",
        done_phase="expert_done",
    )
    return result[0]
