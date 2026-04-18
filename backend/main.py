from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.diagnosis_engine import diagnose_failure
from app.eval_generator import generate_eval_from_fork
from app.models import (
    AgentTrace,
    Diagnosis,
    DiagnosisRequest,
    EvalRequest,
    Fork,
    GeneratedEval,
    ReplayRequest,
    TraceSummary,
)
from app.replay_engine import replay_from_fork
from app.trace_repository import repository


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("agentrewind")

settings = get_settings()

app = FastAPI(title="AgentRewind API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def load_demo_traces() -> None:
    repository.reload()
    logger.info(
        "Loaded %s demo traces. LLM mode=%s key_source=%s",
        len(repository.list_traces()),
        "openai" if settings.llm_enabled else "mock",
        settings.api_key_source,
    )


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "trace_count": len(repository.list_traces()),
        "llm_mode": "openai" if settings.llm_enabled else "mock",
        "primary_model": settings.primary_model,
        "replay_model": settings.replay_model,
    }


@app.get("/api/traces", response_model=list[TraceSummary])
async def list_traces() -> list[TraceSummary]:
    return repository.list_traces()


@app.get("/api/traces/{trace_id}", response_model=AgentTrace)
async def get_trace(trace_id: str) -> AgentTrace:
    trace = repository.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace


@app.post("/api/diagnose", response_model=Diagnosis)
async def diagnose(request: DiagnosisRequest) -> Diagnosis:
    trace = repository.get_trace(request.trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")

    logger.info("Diagnosing trace=%s suspected_step=%s", request.trace_id, request.suspected_step_id)
    return await diagnose_failure(trace, request.suspected_step_id)


@app.post("/api/replay", response_model=Fork)
async def replay(request: ReplayRequest) -> Fork:
    trace = repository.get_trace(request.trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")

    logger.info("Replaying trace=%s from step=%s", request.trace_id, request.fork_step_id)
    try:
        fork = await replay_from_fork(trace, request.fork_step_id, request.user_modification)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    repository.save_fork(fork)
    return fork


@app.post("/api/evals", response_model=GeneratedEval)
async def generate_eval(request: EvalRequest) -> GeneratedEval:
    trace = repository.get_trace(request.trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")

    fork = repository.get_fork(request.fork_id)
    if fork is None:
        raise HTTPException(status_code=404, detail="Fork not found.")

    diagnosis = request.diagnosis or await diagnose_failure(trace, fork.fork_point_step_id)
    logger.info("Generating eval trace=%s fork=%s", request.trace_id, request.fork_id)
    generated_eval = await generate_eval_from_fork(trace, fork, diagnosis)
    repository.save_eval(generated_eval)
    return generated_eval
