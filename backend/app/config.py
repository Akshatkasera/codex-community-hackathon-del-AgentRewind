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
    primary_model: str
    replay_model: str
    judge_model: str
    frontend_origin: str
    prompt_path: Path

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key) and not self.use_mock_llm


@lru_cache
def get_settings() -> Settings:
    prompt_path = Path(
        os.getenv("AGENTREWIND_PROMPT_PATH", r"C:\Users\aksha\Downloads\prompt.md")
    )
    api_key = os.getenv("OPENAI_API_KEY")
    api_key_source = "environment"

    if not api_key:
        api_key = _extract_api_key_from_prompt(prompt_path)
        api_key_source = "prompt.md" if api_key else "missing"

    return Settings(
        openai_api_key=api_key,
        api_key_source=api_key_source,
        use_mock_llm=_parse_bool(os.getenv("AGENTREWIND_USE_MOCK_LLM"), default=False),
        primary_model=os.getenv("OPENAI_PRIMARY_MODEL", "gpt-4o"),
        replay_model=os.getenv("OPENAI_REPLAY_MODEL", "gpt-4o-mini"),
        judge_model=os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o"),
        frontend_origin=os.getenv(
            "AGENTREWIND_FRONTEND_ORIGIN", "http://localhost:5173"
        ),
        prompt_path=prompt_path,
    )
