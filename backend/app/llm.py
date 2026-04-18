from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from .config import get_settings


class LLMServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


@lru_cache
def get_openai_client() -> AsyncOpenAI | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


@lru_cache
def get_llm_semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(get_settings().llm_max_concurrency)


async def run_json_chat(
    *,
    model: str,
    system_prompt: str | None,
    user_prompt: str,
    temperature: float = 0.2,
) -> dict[str, Any]:
    client = get_openai_client()
    if client is None:
        raise LLMServiceError("OpenAI client is not configured.", status_code=503)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    try:
        async with get_llm_semaphore():
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
            )
    except RateLimitError as error:
        raise LLMServiceError(
            "OpenAI rate limit reached. Retry this request shortly.",
            status_code=429,
        ) from error
    except APITimeoutError as error:
        raise LLMServiceError(
            "OpenAI request timed out before the model responded.",
            status_code=504,
        ) from error
    except APIConnectionError as error:
        raise LLMServiceError(
            "OpenAI connection failed. Check network connectivity and try again.",
            status_code=503,
        ) from error
    except APIStatusError as error:
        raise LLMServiceError(
            f"OpenAI returned an upstream error ({error.status_code}).",
            status_code=503,
        ) from error
    except OpenAIError as error:
        raise LLMServiceError(
            "OpenAI request failed unexpectedly.",
            status_code=503,
        ) from error

    if not response.choices:
        raise LLMServiceError(
            "OpenAI returned no completion choices for this request.",
            status_code=503,
        )

    content = response.choices[0].message.content
    if not content:
        raise LLMServiceError(
            "OpenAI returned an empty response payload.",
            status_code=503,
        )

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise LLMServiceError(
            "OpenAI returned malformed JSON for a structured response.",
            status_code=503,
        ) from error

    if not isinstance(parsed, dict):
        raise LLMServiceError(
            "OpenAI returned a structured response with an unexpected shape.",
            status_code=503,
        )

    return parsed
