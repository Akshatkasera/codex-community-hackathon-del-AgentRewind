from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_model_list(
    value: str | None, default: tuple[str, ...]
) -> tuple[str, ...]:
    if not value:
        return default
    parsed = tuple(
        model.strip() for model in value.split(",") if model.strip()
    )
    return parsed or default


def _extract_api_key_from_prompt(prompt_path: Path) -> str | None:
    if not prompt_path.exists():
        return None
    contents = prompt_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"(sk-[A-Za-z0-9_\-]+)", contents)
    if match:
        return match.group(1)
    return None


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    api_key_source: str
    use_mock_llm: bool
    available_models: tuple[str, ...]
    primary_model: str
    replay_model: str
    judge_model: str
    frontend_origin: str
    prompt_path: Path

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key) and not self.use_mock_llm

    def resolve_model(self, model_override: str | None, *, fallback: str) -> str:
        if not model_override:
            return fallback
        if model_override not in self.available_models:
            raise ValueError(
                f"Unsupported model '{model_override}'. Choose one of: {', '.join(self.available_models)}."
            )
        return model_override


@lru_cache
def get_settings() -> Settings:
    default_models = ("gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini")
    prompt_path = Path(
        os.getenv("AGENTREWIND_PROMPT_PATH", r"C:\Users\aksha\Downloads\prompt.md")
    )
    api_key = os.getenv("OPENAI_API_KEY")
    api_key_source = "environment"

    if not api_key:
        api_key = _extract_api_key_from_prompt(prompt_path)
        api_key_source = "prompt.md" if api_key else "missing"

    primary_model = os.getenv("OPENAI_PRIMARY_MODEL", "gpt-4o")
    replay_model = os.getenv("OPENAI_REPLAY_MODEL", "gpt-4o-mini")
    judge_model = os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o")
    configured_models = _parse_model_list(
        os.getenv("AGENTREWIND_AVAILABLE_MODELS"), default_models
    )
    available_models = tuple(
        dict.fromkeys((*configured_models, primary_model, replay_model, judge_model))
    )

    return Settings(
        openai_api_key=api_key,
        api_key_source=api_key_source,
        use_mock_llm=_parse_bool(os.getenv("AGENTREWIND_USE_MOCK_LLM"), default=False),
        available_models=available_models,
        primary_model=primary_model,
        replay_model=replay_model,
        judge_model=judge_model,
        frontend_origin=os.getenv(
            "AGENTREWIND_FRONTEND_ORIGIN", "http://localhost:5173"
        ),
        prompt_path=prompt_path,
    )
