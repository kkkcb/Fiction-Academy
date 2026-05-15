import json
import time
import logging
from openai import AsyncOpenAI

from backend.config import XIAOMI_API_KEY, XIAOMI_BASE_URL, DEFAULT_MODEL

logger = logging.getLogger("llm")

_client: AsyncOpenAI | None = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=XIAOMI_API_KEY,
            base_url=XIAOMI_BASE_URL,
        )
    return _client

SYSTEM_PROMPT = """你是一位专业的小说创作助手。你拥有丰富的小说创作经验，擅长：
- 构建自洽的世界观体系
- 设计立体的角色
- 编写引人入胜的故事情节
- 把控节奏和悬念

你的工作原则：
1. 一切创作必须基于已定稿的世界观，不可矛盾
2. 角色随故事发展自然成长变化
3. 每一章都要有看点和钩子
4. 尊重用户的创作意图，提供专业建议但以用户为准
"""

def resolve_model(model: str = "") -> str:
    return model if model else DEFAULT_MODEL

async def chat_stream(messages: list[dict], system_prompt: str | None = None, model: str = ""):
    client = get_client()
    use_model = resolve_model(model)
    t0 = time.time()
    logger.info("[chat_stream] request started, model=%s, messages=%d", use_model, len(messages))
    stream = await client.chat.completions.create(
        model=use_model,
        temperature=0.8,
        messages=[
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            *messages,
        ],
        stream=True,
    )
    t1 = time.time()
    logger.info("[chat_stream] first response from LLM in %.2fs", t1 - t0)
    chunk_count = 0
    total_chars = 0
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            chunk_count += 1
            total_chars += len(delta.content)
            yield delta.content
    t2 = time.time()
    logger.info("[chat_stream] finished: %d chunks, %d chars, total %.2fs (generate %.2fs)", chunk_count, total_chars, t2 - t0, t2 - t1)

async def chat_text(messages: list[dict], system_prompt: str | None = None, model: str = "") -> str:
    client = get_client()
    use_model = resolve_model(model)
    response = await client.chat.completions.create(
        model=use_model,
        temperature=0.8,
        messages=[
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            *messages,
        ],
    )
    return response.choices[0].message.content

async def chat_json(messages: list[dict], system_prompt: str | None = None, model: str = "") -> dict:
    client = get_client()
    use_model = resolve_model(model)
    response = await client.chat.completions.create(
        model=use_model,
        temperature=0.5,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            *messages,
        ],
    )
    return json.loads(response.choices[0].message.content)
