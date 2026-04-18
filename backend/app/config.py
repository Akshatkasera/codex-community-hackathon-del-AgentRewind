from __future__ import annotations

import os
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


def _parse_origin_list(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    parsed = tuple(origin.strip() for origin in value.split(",") if origin.strip())
    return parsed or default


def _parse_string_list(value: str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not value:
        return default
    parsed = tuple(item.strip() for item in value.split(",") if item.strip())
    return parsed or default


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _running_on_vercel() -> bool:
    return _parse_bool(os.getenv("VERCEL"), default=False) or bool(
        os.getenv("VERCEL_URL")
    )


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    api_key_source: str
    use_mock_llm: bool
    serverless_mode: bool
    auth_tokens: tuple[str, ...]
    available_models: tuple[str, ...]
    primary_model: str
    replay_model: str
    judge_model: str
    frontend_origin: str
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    require_https: bool
    state_db_path: Path
    imported_trace_dir: Path
    llm_timeout_seconds: float
    llm_max_retries: int
    llm_max_concurrency: int
    import_max_payload_bytes: int
    import_max_steps: int
    import_max_text_chars: int
    import_max_list_entries: int
    llm_max_trace_chars: int
    rate_limit_requests_per_minute: int
    rate_limit_heavy_requests_per_minute: int
    job_worker_concurrency: int
    job_retention_seconds: int

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key) and not self.use_mock_llm

    @property
    def auth_required(self) -> bool:
        return bool(self.auth_tokens)

    @property
    def async_jobs_enabled(self) -> bool:
        return not self.serverless_mode

    @property
    def storage_backend_label(self) -> str:
        return "sqlite (ephemeral)" if self.serverless_mode else "sqlite"

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
    running_on_vercel = _running_on_vercel()
    frontend_origin_default = (
        f"https://{os.environ['VERCEL_URL']}"
        if os.getenv("VERCEL_URL")
        else "http://localhost:5173"
    )
    state_db_path = Path(
        os.getenv(
            "AGENTREWIND_STATE_DB_PATH",
            "/tmp/agentrewind.sqlite3"
            if running_on_vercel
            else str(ROOT_DIR / "state" / "agentrewind.sqlite3"),
        )
    )
    imported_trace_dir = Path(
        os.getenv(
            "AGENTREWIND_IMPORTED_TRACE_DIR",
            "/tmp/agentrewind-imported-traces"
            if running_on_vercel
            else str(ROOT_DIR / "imported_traces"),
        )
    )
    if not state_db_path.is_absolute():
        state_db_path = (ROOT_DIR / state_db_path).resolve()
    if not imported_trace_dir.is_absolute():
        imported_trace_dir = (ROOT_DIR / imported_trace_dir).resolve()
    api_key = os.getenv("OPENAI_API_KEY")
    api_key_source = "environment" if api_key else "missing"

    primary_model = os.getenv("OPENAI_PRIMARY_MODEL", "gpt-4o")
    replay_model = os.getenv("OPENAI_REPLAY_MODEL", "gpt-4o-mini")
    judge_model = os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o")
    configured_models = _parse_model_list(
        os.getenv("AGENTREWIND_AVAILABLE_MODELS"), default_models
    )
    available_models = tuple(
        dict.fromkeys((*configured_models, primary_model, replay_model, judge_model))
    )
    frontend_origin = os.getenv("AGENTREWIND_FRONTEND_ORIGIN", frontend_origin_default)
    cors_origins = _parse_origin_list(
        os.getenv("AGENTREWIND_CORS_ORIGINS"),
        (frontend_origin,)
        if running_on_vercel
        else (frontend_origin, "http://127.0.0.1:5173"),
    )
    trusted_hosts = _parse_string_list(
        os.getenv("AGENTREWIND_TRUSTED_HOSTS"),
        ("localhost", "127.0.0.1", "testserver", "*.vercel.app")
        if running_on_vercel
        else ("localhost", "127.0.0.1", "testserver"),
    )
    auth_tokens = _parse_string_list(os.getenv("AGENTREWIND_AUTH_TOKENS"))

    return Settings(
        openai_api_key=api_key,
        api_key_source=api_key_source,
        use_mock_llm=_parse_bool(os.getenv("AGENTREWIND_USE_MOCK_LLM"), default=False),
        serverless_mode=running_on_vercel,
        auth_tokens=auth_tokens,
        available_models=available_models,
        primary_model=primary_model,
        replay_model=replay_model,
        judge_model=judge_model,
        frontend_origin=frontend_origin,
        cors_origins=cors_origins,
        trusted_hosts=trusted_hosts,
        require_https=_parse_bool(os.getenv("AGENTREWIND_REQUIRE_HTTPS"), default=False),
        state_db_path=state_db_path,
        imported_trace_dir=imported_trace_dir,
        llm_timeout_seconds=max(
            5.0,
            _parse_float(os.getenv("AGENTREWIND_LLM_TIMEOUT_SECONDS"), default=45.0),
        ),
        llm_max_retries=max(
            0,
            _parse_int(os.getenv("AGENTREWIND_LLM_MAX_RETRIES"), default=2),
        ),
        llm_max_concurrency=max(
            1,
            _parse_int(os.getenv("AGENTREWIND_LLM_MAX_CONCURRENCY"), default=8),
        ),
        import_max_payload_bytes=max(
            32_768,
            _parse_int(
                os.getenv("AGENTREWIND_IMPORT_MAX_PAYLOAD_BYTES"),
                default=2_000_000,
            ),
        ),
        import_max_steps=max(
            1,
            _parse_int(os.getenv("AGENTREWIND_IMPORT_MAX_STEPS"), default=250),
        ),
        import_max_text_chars=max(
            200,
            _parse_int(os.getenv("AGENTREWIND_IMPORT_MAX_TEXT_CHARS"), default=6_000),
        ),
        import_max_list_entries=max(
            5,
            _parse_int(os.getenv("AGENTREWIND_IMPORT_MAX_LIST_ENTRIES"), default=50),
        ),
        llm_max_trace_chars=max(
            2_000,
            _parse_int(os.getenv("AGENTREWIND_LLM_MAX_TRACE_CHARS"), default=24_000),
        ),
        rate_limit_requests_per_minute=max(
            0,
            _parse_int(
                os.getenv("AGENTREWIND_RATE_LIMIT_REQUESTS_PER_MINUTE"),
                default=240,
            ),
        ),
        rate_limit_heavy_requests_per_minute=max(
            0,
            _parse_int(
                os.getenv("AGENTREWIND_RATE_LIMIT_HEAVY_REQUESTS_PER_MINUTE"),
                default=40,
            ),
        ),
        job_worker_concurrency=max(
            1,
            _parse_int(
                os.getenv("AGENTREWIND_JOB_WORKER_CONCURRENCY"),
                default=4,
            ),
        ),
        job_retention_seconds=max(
            60,
            _parse_int(
                os.getenv("AGENTREWIND_JOB_RETENTION_SECONDS"),
                default=86_400,
            ),
        ),
    )
