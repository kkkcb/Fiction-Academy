"""LLM 网关：所有模型调用统一入口。

职责：
- 统一重试/退避（认证错误不重试，限流/网络错误指数退避）
- 结构化输出：chat_json 可选 response_schema（pydantic），解析/校验失败自动重试
- token 用量记录（非流式）
- 流式调用在产出首个 chunk 前失败时自动重试一次
"""
import asyncio
import json
import logging

from openai import (
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    NotFoundError,
)
from pydantic import BaseModel

from backend.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    LLM_TIMEOUT,
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


class LLMError(Exception):
    """LLM 调用最终失败（重试耗尽）。"""


class LLMAuthError(LLMError):
    """API Key 无效或无权限——不应重试，通常需要人工介入。"""


class LLMJSONError(LLMError):
    """模型多次未能返回合法/通过校验的 JSON。"""


_FATAL_ERRORS = (AuthenticationError, NotFoundError, BadRequestError)


def _classify(e: Exception) -> str:
    if isinstance(e, AuthenticationError):
        return "auth"
    if isinstance(e, RateLimitError):
        return "rate_limit"
    if isinstance(e, APITimeoutError):
        return "timeout"
    if isinstance(e, APIConnectionError):
        return "connection"
    return "other"


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            timeout=LLM_TIMEOUT,
        )
    return _client


def _log_usage(tag: str, usage) -> None:
    if usage is None:
        return
    logger.info(
        "[llm] %s prompt_tokens=%d completion_tokens=%d total_tokens=%d",
        tag, getattr(usage, "prompt_tokens", 0),
        getattr(usage, "completion_tokens", 0),
        getattr(usage, "total_tokens", 0),
    )


def _strip_code_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    return content


async def _sleep_backoff(attempt: int) -> None:
    await asyncio.sleep(min((2 ** attempt) * 3, 30))


async def chat_stream(messages: list[dict], system_prompt: str | None = None,
                      model: str = "", temperature: float = 0.8,
                      disable_thinking: bool = False):
    """流式生成。yield (kind, text)，kind ∈ {'reasoning', 'content'}。

    首个 chunk 产出前失败会重试一次（含 usage 不确定的风险）；
    已经开始输出后失败则向上抛出，由调用方决定保留部分输出。
    """
    client = _get_client()
    sys = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    full_messages = [{"role": "system", "content": sys}] + messages

    last_err: Exception | None = None
    emitted = False
    for attempt in range(2):
        try:
            extra = {"extra_body": {"thinking": {"type": "disabled"}}} if disable_thinking else {}
            stream = await client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=full_messages,
                stream=True,
                temperature=temperature,
                max_tokens=LLM_MAX_TOKENS,
                **extra,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                if reasoning:
                    emitted = True
                    yield ("reasoning", reasoning)
                if delta.content:
                    emitted = True
                    yield ("content", delta.content)
            return
        except _FATAL_ERRORS:
            raise
        except Exception as e:
            last_err = e
            if emitted:
                # 已有部分输出，无法安全重放，直接上抛
                raise
            logger.warning("[llm] stream failed before first chunk (attempt %d/2): %s", attempt + 1, e)
            if attempt == 0:
                await _sleep_backoff(attempt)
    raise LLMError(f"stream failed: {last_err}") from last_err


async def chat_text(messages: list[dict], system_prompt: str | None = None,
                    model: str = "", temperature: float = 0.8) -> str:
    client = _get_client()
    sys = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    full_messages = [{"role": "system", "content": sys}] + messages

    last_err: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = await client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=full_messages,
                temperature=temperature,
                max_tokens=LLM_MAX_TOKENS,
            )
            _log_usage("chat_text", getattr(response, "usage", None))
            if getattr(response.choices[0], "finish_reason", None) == "length":
                logger.warning("[llm] chat_text output truncated by max_tokens (%d)", LLM_MAX_TOKENS)
            return response.choices[0].message.content or ""
        except _FATAL_ERRORS as e:
            raise LLMAuthError(str(e)) from e
        except Exception as e:
            last_err = e
            kind = _classify(e)
            if kind == "rate_limit":
                await asyncio.sleep(min(2 ** attempt * 5, 60))
            elif attempt < LLM_MAX_RETRIES - 1:
                await _sleep_backoff(attempt)
            logger.warning("[llm] chat_text failed (%s, attempt %d/%d): %s",
                           kind, attempt + 1, LLM_MAX_RETRIES, e)
    raise LLMError(f"chat_text failed after {LLM_MAX_RETRIES} attempts: {last_err}") from last_err


async def chat_json(messages: list[dict], system_prompt: str | None = None,
                    model: str = "", temperature: float = 0.5,
                    response_schema: type[BaseModel] | None = None) -> dict:
    """结构化输出。失败（解析或 schema 校验不通过）自动重试，重试耗尽抛 LLMJSONError。

    传入 response_schema 时返回 `model_dump()` 后的 dict 并保证通过校验。
    """
    client = _get_client()
    sys = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    full_messages = [{"role": "system", "content": sys}] + messages

    last_err: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES):
        content = ""
        try:
            response = await client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=full_messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                max_tokens=LLM_MAX_TOKENS,
            )
            _log_usage("chat_json", getattr(response, "usage", None))
            content = response.choices[0].message.content or ""
            if getattr(response.choices[0], "finish_reason", None) == "length":
                # 输出被 max_tokens 截断。JSON 模式下服务端可能自动补全括号，
                # 产生"能解析但内容残缺"的结果——必须视为失败重试，否则残数据会被静默存库。
                raise ValueError(
                    f"output truncated by max_tokens ({LLM_MAX_TOKENS}); 内容不完整，拒绝采用"
                )
            data = json.loads(_strip_code_fence(content))
            if response_schema is not None:
                data = response_schema.model_validate(data).model_dump()
            return data
        except _FATAL_ERRORS as e:
            raise LLMAuthError(str(e)) from e
        except (json.JSONDecodeError, ValueError) as e:
            # ValueError 覆盖 pydantic ValidationError（其继承自 ValueError）
            last_err = LLMJSONError(f"invalid JSON/schema: {str(e)[:300]}")
            logger.warning("[llm] chat_json parse/validate failed (attempt %d/%d): %s",
                           attempt + 1, LLM_MAX_RETRIES, str(e)[:200])
            if attempt < LLM_MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
        except Exception as e:
            last_err = e
            kind = _classify(e)
            if kind == "rate_limit":
                await asyncio.sleep(min(2 ** attempt * 5, 60))
            elif attempt < LLM_MAX_RETRIES - 1:
                await _sleep_backoff(attempt)
            logger.warning("[llm] chat_json failed (%s, attempt %d/%d): %s",
                           kind, attempt + 1, LLM_MAX_RETRIES, e)
    raise last_err if isinstance(last_err, LLMError) else LLMError(f"chat_json failed: {last_err}") from last_err
