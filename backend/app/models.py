from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


StepType = Literal["llm", "tool", "analysis", "review"]
StepStatus = Literal["ok", "warning", "error"]
FixTarget = Literal["prompt", "tool_args", "handoff", "source_selection", "response"]


class TraceStep(BaseModel):
    id: str
    agent_name: str
    step_type: StepType
    status: StepStatus
    tool_name: str | None = None
    tool_args: dict[str, Any] | str | None = None
    tool_result: Any | None = None
    input_prompt: str
    output_response: str
    timestamp: float
    cost_usd: float = 0.0
    tokens: int = 0
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class AgentTrace(BaseModel):
    trace_id: str
    title: str
    task_description: str
    expected_output: str | None = None
    final_output: str
    steps: list[TraceStep]
    failure_summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class TraceSummary(BaseModel):
    trace_id: str
    title: str
    task_description: str
    failure_summary: str | None = None
    tags: list[str] = Field(default_factory=list)


class Diagnosis(BaseModel):
    root_cause_step_id: str
    confidence: int
    blame_agent: str
    failure_category: str
    explanation: str
    suggested_fix: str
    fix_target: FixTarget


class Fork(BaseModel):
    fork_id: str
    original_trace_id: str
    fork_point_step_id: str
    user_modification: str
    replayed_steps: list[TraceStep]
    new_final_output: str
    new_success: bool
    cost_delta: float
    quality_improved: bool
    assessment: str | None = None


class GeneratedEval(BaseModel):
    eval_id: str
    trigger_pattern: str
    assertions: list[dict[str, Any]]
    created_from_trace_id: str
    fix_description: str


class DiagnosisRequest(BaseModel):
    trace_id: str
    suspected_step_id: str | None = None


class ReplayRequest(BaseModel):
    trace_id: str
    fork_step_id: str
    user_modification: str


class EvalRequest(BaseModel):
    trace_id: str
    fork_id: str
    diagnosis: Diagnosis | None = None
