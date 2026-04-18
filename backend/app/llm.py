from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI

from .config import get_settings


@lru_cache
def get_openai_client() -> AsyncOpenAI | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def run_json_chat(
    *,
    model: str,
    system_prompt: str | None,
    user_prompt: str,
    temperature: float = 0.2,
) -> dict[str, Any]:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI client is not configured.")

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)
