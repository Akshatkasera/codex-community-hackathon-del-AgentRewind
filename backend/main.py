from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from app.analysis_engine import enrich_trace
from app.config import get_settings
from app.diagnosis_engine import diagnose_failure
from app.eval_generator import generate_eval_from_fork
from app.import_adapters import import_trace_payload
from app.jobs import job_manager
from app.llm import LLMServiceError
from app.models import (
    AgentTrace,
    AsyncJobRecord,
    Diagnosis,
    DiagnosisRequest,
    EvalRequest,
    FailureCluster,
    Fork,
    GeneratedEval,
    ImportedTraceResult,
    ImportTraceRequest,
    ReplayRequest,
    TraceSummary,
)
from app.rate_limiter import rate_limiter
from app.replay_engine import replay_from_fork
from app.security import request_is_authorized, requires_auth
from app.trace_repository import repository


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("agentrewind")

settings = get_settings()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"

app = FastAPI(title="AgentRewind API", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)
if settings.trusted_hosts:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.trusted_hosts),
    )
if settings.require_https:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()
    rate_limit_limit = 0
    rate_limit_remaining = 0
    rate_limit_retry_after = 0
    try:
        if requires_auth(request.url.path) and not request_is_authorized(request):
            response = _error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API token.",
            )
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        if request.url.path.startswith("/api/"):
            (
                allowed,
                rate_limit_limit,
                rate_limit_remaining,
                rate_limit_retry_after,
            ) = rate_limiter.check_request(request)
            if not allowed:
                response = _error_response(
                    request,
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Retry this request shortly.",
                )
                response.headers["Retry-After"] = str(rate_limit_retry_after)
                response.headers["X-RateLimit-Limit"] = str(rate_limit_limit)
                response.headers["X-RateLimit-Remaining"] = "0"
                return response
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if request.url.path.startswith("/api/") and rate_limit_limit > 0:
            response.headers["X-RateLimit-Limit"] = str(rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_remaining)
        return response
    finally:
        duration_ms = (time.perf_counter() - started_at) * 1000
        status_code = getattr(locals().get("response"), "status_code", 500)
        logger.info(
            "%s %s -> %s request_id=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            status_code,
            request_id,
            duration_ms,
        )


def _error_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    payload = {
        "detail": detail,
        "request_id": request_id,
    }
    response = JSONResponse(status_code=status_code, content=payload)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else None
    detail = "Request validation failed."
    if first_error and isinstance(first_error, dict):
        location = ".".join(str(item) for item in first_error.get("loc", []))
        message = str(first_error.get("msg", "Invalid request payload."))
        detail = f"{location}: {message}" if location else message
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail,
    )


@app.exception_handler(LLMServiceError)
async def llm_service_exception_handler(
    request: Request, exc: LLMServiceError
) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        detail=str(exc),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception(
        "Unhandled server error request_id=%s path=%s",
        getattr(request.state, "request_id", None),
        request.url.path,
        exc_info=exc,
    )
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error.",
    )


@app.on_event("startup")
async def load_demo_traces() -> None:
    repository.reload()
    if settings.async_jobs_enabled:
        await job_manager.start()
    logger.info(
        "Loaded %s demo traces. LLM mode=%s key_source=%s",
        len(repository.list_traces()),
        "openai" if settings.llm_enabled else "mock",
        settings.api_key_source,
    )


@app.on_event("shutdown")
async def shutdown_services() -> None:
    if settings.async_jobs_enabled:
        await job_manager.shutdown()


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "trace_count": len(repository.list_traces()),
        "llm_mode": "openai" if settings.llm_enabled else "mock",
        "available_models": list(settings.available_models),
        "primary_model": settings.primary_model,
        "replay_model": settings.replay_model,
        "cluster_count": len(repository.list_clusters()),
        "auth_required": settings.auth_required,
        "storage_backend": settings.storage_backend_label,
        "async_jobs": settings.async_jobs_enabled,
        "rate_limit_requests_per_minute": settings.rate_limit_requests_per_minute,
        "rate_limit_heavy_requests_per_minute": settings.rate_limit_heavy_requests_per_minute,
    }


@app.get("/api/traces", response_model=list[TraceSummary])
async def list_traces() -> list[TraceSummary]:
    return repository.list_traces()


@app.get("/api/clusters", response_model=list[FailureCluster])
async def list_clusters() -> list[FailureCluster]:
    return repository.list_clusters()


@app.get("/api/traces/{trace_id}", response_model=AgentTrace)
async def get_trace(trace_id: str) -> AgentTrace:
    trace = repository.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace


@app.post("/api/imports", response_model=ImportedTraceResult)
async def import_trace(request: Request) -> ImportedTraceResult:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Import request body is empty.")
    if len(body) > settings.import_max_payload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "Import request exceeds the maximum supported size of "
                f"{settings.import_max_payload_bytes:,} bytes."
            ),
        )
    try:
        parsed_request = ImportTraceRequest.model_validate_json(body)
    except ValidationError as error:
        first_error = error.errors()[0] if error.errors() else {}
        message = str(first_error.get("msg", "Invalid import request payload."))
        raise HTTPException(status_code=422, detail=message) from error
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Import request body is not valid JSON.") from error

    logger.info("Importing trace with framework_hint=%s", parsed_request.framework_hint)
    try:
        imported = import_trace_payload(
            payload=parsed_request.payload,
            framework_hint=parsed_request.framework_hint,
            source_name=parsed_request.source_name,
            title_override=parsed_request.title_override,
            task_description_override=parsed_request.task_description_override,
        )
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    stored_trace = repository.save_imported_trace(imported.trace)
    return ImportedTraceResult(
        framework_detected=imported.framework_detected,
        adapter_notes=imported.adapter_notes,
        trace=stored_trace,
    )


@app.post(
    "/api/diagnose/jobs",
    response_model=AsyncJobRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_diagnosis_job(
    request: Request,
    payload: DiagnosisRequest,
) -> AsyncJobRecord:
    if not settings.async_jobs_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Async jobs are disabled in this deployment. Use /api/diagnose instead.",
        )
    trace = _resolve_trace(payload.trace_id, payload.trace)
    return await job_manager.submit(
        kind="diagnosis",
        trace_id=payload.trace_id,
        request_id=getattr(request.state, "request_id", None),
        request_payload=payload.model_dump(mode="json"),
        runner=lambda: diagnose_failure(
            trace,
            payload.suspected_step_id,
            model_override=payload.model,
        ),
    )


@app.post("/api/diagnose", response_model=Diagnosis)
async def diagnose(request: DiagnosisRequest) -> Diagnosis:
    trace = _resolve_trace(request.trace_id, request.trace)

    logger.info(
        "Diagnosing trace=%s suspected_step=%s model=%s",
        request.trace_id,
        request.suspected_step_id,
        request.model or settings.primary_model,
    )
    try:
        return await diagnose_failure(
            trace, request.suspected_step_id, model_override=request.model
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post(
    "/api/replay/jobs",
    response_model=AsyncJobRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_replay_job(
    request: Request,
    payload: ReplayRequest,
) -> AsyncJobRecord:
    if not settings.async_jobs_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Async jobs are disabled in this deployment. Use /api/replay instead.",
        )
    trace = _resolve_trace(payload.trace_id, payload.trace)

    return await job_manager.submit(
        kind="replay",
        trace_id=payload.trace_id,
        request_id=getattr(request.state, "request_id", None),
        request_payload=payload.model_dump(mode="json"),
        runner=lambda: _run_replay_job(trace, payload),
    )


@app.post("/api/replay", response_model=Fork)
async def replay(request: ReplayRequest) -> Fork:
    trace = _resolve_trace(request.trace_id, request.trace)

    logger.info(
        "Replaying trace=%s from step=%s model=%s",
        request.trace_id,
        request.fork_step_id,
        request.model or settings.replay_model,
    )
    try:
        fork = await replay_from_fork(
            trace,
            request.fork_step_id,
            request.user_modification,
            replay_model_override=request.model,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    repository.save_fork(fork)
    return fork


@app.post(
    "/api/evals/jobs",
    response_model=AsyncJobRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_eval_job(
    request: Request,
    payload: EvalRequest,
) -> AsyncJobRecord:
    if not settings.async_jobs_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Async jobs are disabled in this deployment. Use /api/evals instead.",
        )
    trace = _resolve_trace(payload.trace_id, payload.trace)
    fork = _resolve_fork(payload.fork_id, payload.fork)

    return await job_manager.submit(
        kind="eval",
        trace_id=payload.trace_id,
        request_id=getattr(request.state, "request_id", None),
        request_payload=payload.model_dump(mode="json"),
        runner=lambda: _run_eval_job(trace, fork, payload),
    )


@app.post("/api/evals", response_model=GeneratedEval)
async def generate_eval(request: EvalRequest) -> GeneratedEval:
    trace = _resolve_trace(request.trace_id, request.trace)
    fork = _resolve_fork(request.fork_id, request.fork)

    diagnosis = request.diagnosis or await diagnose_failure(trace, fork.fork_point_step_id)
    logger.info("Generating eval trace=%s fork=%s", request.trace_id, request.fork_id)
    generated_eval = await generate_eval_from_fork(trace, fork, diagnosis)
    repository.save_eval(generated_eval)
    return generated_eval


@app.get("/api/jobs/{job_id}", response_model=AsyncJobRecord)
async def get_job(job_id: str) -> AsyncJobRecord:
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


async def _run_replay_job(trace: AgentTrace, payload: ReplayRequest) -> Fork:
    fork = await replay_from_fork(
        trace,
        payload.fork_step_id,
        payload.user_modification,
        replay_model_override=payload.model,
    )
    repository.save_fork(fork)
    return fork


async def _run_eval_job(
    trace: AgentTrace,
    fork: Fork,
    payload: EvalRequest,
) -> GeneratedEval:
    diagnosis = payload.diagnosis or await diagnose_failure(trace, fork.fork_point_step_id)
    generated_eval = await generate_eval_from_fork(trace, fork, diagnosis)
    repository.save_eval(generated_eval)
    return generated_eval


def _resolve_trace(trace_id: str, inline_trace: AgentTrace | None) -> AgentTrace:
    if inline_trace is not None:
        return inline_trace if inline_trace.analysis is not None else enrich_trace(inline_trace)
    trace = repository.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace


def _resolve_fork(fork_id: str, inline_fork: Fork | None) -> Fork:
    if inline_fork is not None:
        return inline_fork
    fork = repository.get_fork(fork_id)
    if fork is None:
        raise HTTPException(status_code=404, detail="Fork not found.")
    return fork


def _frontend_response(path: str = "") -> FileResponse:
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build not found. Run the AgentRewind startup command first.",
        )

    if path:
        candidate = (FRONTEND_DIST_DIR / path).resolve()
        if candidate.is_file() and FRONTEND_DIST_DIR.resolve() in candidate.parents:
            return FileResponse(candidate)

    return FileResponse(FRONTEND_INDEX_FILE)


@app.get("/", include_in_schema=False)
async def serve_frontend_index() -> FileResponse:
    return _frontend_response()


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend_app(full_path: str) -> FileResponse:
    if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="Not found.")
    return _frontend_response(full_path)
