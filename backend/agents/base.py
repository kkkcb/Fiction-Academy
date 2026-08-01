import json
import asyncio
import logging

from openai import AsyncOpenAI

from backend.config import (
    XIAOMI_API_KEY,
    XIAOMI_BASE_URL,
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    LLM_TIMEOUT,
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=XIAOMI_API_KEY,
            base_url=XIAOMI_BASE_URL,
            timeout=LLM_TIMEOUT,
        )
    return _client


async def chat_stream(messages: list[dict], system_prompt: str | None = None, model: str = "", temperature: float = 0.8):
    """流式生成。yield (kind, text) 元组，kind ∈ {'reasoning', 'content'}。

    reasoning 为模型的思考链（DeepSeek-R1 / GLM 推理模型的 reasoning_content 字段），
    content 为最终回复正文。无推理能力的模型只产出 content。
    """
    client = _get_client()
    sys = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    full_messages = [{"role": "system", "content": sys}] + messages
    stream = await client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=full_messages,
        stream=True,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
        if reasoning:
            yield ("reasoning", reasoning)
        if delta.content:
            yield ("content", delta.content)


async def chat_text(messages: list[dict], system_prompt: str | None = None, model: str = "", temperature: float = 0.8) -> str:
    last_err = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            client = _get_client()
            sys = system_prompt if system_prompt is not None else SYSTEM_PROMPT
            full_messages = [{"role": "system", "content": sys}] + messages
            response = await client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=full_messages,
                temperature=temperature,
                max_tokens=LLM_MAX_TOKENS,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            last_err = e
            is_auth = "401" in str(e) or "auth" in str(e).lower()
            if is_auth and attempt == 0:
                raise
            if attempt < LLM_MAX_RETRIES - 1 and not is_auth:
                wait = (2 ** attempt) * 3 + asyncio.get_event_loop().time() % 2
                logger.warning("LLM chat_text failed (attempt %d/%d), retry in %.1fs: %s", attempt + 1, LLM_MAX_RETRIES, wait, e)
                await asyncio.sleep(wait)
            else:
                logger.error("LLM chat_text failed after %d attempts: %s", LLM_MAX_RETRIES, e)
    raise last_err


async def chat_json(messages: list[dict], system_prompt: str | None = None, model: str = "", temperature: float = 0.5) -> dict:
    last_err = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            client = _get_client()
            sys = system_prompt if system_prompt is not None else SYSTEM_PROMPT
            full_messages = [{"role": "system", "content": sys}] + messages
            response = await client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=full_messages,
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=LLM_MAX_TOKENS,
            )
            content = response.choices[0].message.content or ""
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            return json.loads(content)
        except json.JSONDecodeError as e:
            last_err = e
            logger.warning("LLM returned invalid JSON (attempt %d/%d): %s", attempt + 1, LLM_MAX_RETRIES, str(e)[:200])
            if attempt < LLM_MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return {"error": "json_parse_failed", "raw": content[:500] if 'content' in dir() else ""}
        except Exception as e:
            last_err = e
            is_auth = "401" in str(e) or "auth" in str(e).lower()
            if is_auth and attempt == 0:
                raise
            if attempt < LLM_MAX_RETRIES - 1 and not is_auth:
                wait = (2 ** attempt) * 3
                logger.warning("LLM chat_json failed (attempt %d/%d), retry in %.1fs: %s", attempt + 1, LLM_MAX_RETRIES, wait, e)
                await asyncio.sleep(wait)
            else:
                logger.error("LLM chat_json failed after %d attempts: %s", LLM_MAX_RETRIES, e)
    raise last_err if last_err else RuntimeError("LLM call failed")
