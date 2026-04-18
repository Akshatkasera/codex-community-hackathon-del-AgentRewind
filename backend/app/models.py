from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


StepType = Literal["llm", "tool", "analysis", "review"]
StepStatus = Literal["ok", "warning", "error"]
FixTarget = Literal["prompt", "tool_args", "handoff", "source_selection", "response"]
ProvenanceKind = Literal["tool_snapshot", "memory_carryover", "direct_handoff", "inferred"]
ContradictionStatus = Literal["unresolved", "explained", "resolved"]
RepairScope = Literal[
    "prompt",
    "retrieval_policy",
    "tool_contract",
    "memory_guard",
    "workflow",
    "abstain_policy",
]
UncertaintyLevel = Literal["low", "medium", "high", "critical"]
ImportFramework = Literal[
    "auto",
    "agentrewind",
    "langgraph",
    "crewai",
    "autogen",
    "openai_agents",
    "generic",
]


class ToolSnapshot(BaseModel):
    snapshot_id: str
    tool_name: str
    captured_at: float | None = None
    normalized_args: dict[str, Any] | str | None = None
    result: Any | None = None
    result_digest: str
    deterministic_replay: bool = True
    invalidation_reason: str | None = None


class ContradictionFinding(BaseModel):
    finding_id: str
    left_step_id: str
    right_step_id: str
    conflict_type: str
    summary: str
    severity: int = 1
    left_claim: str
    right_claim: str
    status: ContradictionStatus = "unresolved"


class RepairSuggestion(BaseModel):
    suggestion_id: str
    title: str
    summary: str
    target_scope: RepairScope
    target_step_id: str | None = None
    patch_hint: str
    confidence: int = 70
    auto_applicable: bool = False


class ProvenanceLink(BaseModel):
    link_id: str
    claim: str
    producer_step_id: str
    consumer_step_id: str
    provenance_kind: ProvenanceKind
    evidence: str


class MemoryCorruptionIssue(BaseModel):
    issue_id: str
    memory_key: str
    writer_step_id: str
    impacted_step_ids: list[str] = Field(default_factory=list)
    summary: str
    severity: int = 1
    persistent: bool = False
    recurrence_count: int = 1


class UncertaintySignal(BaseModel):
    step_id: str
    score: float
    level: UncertaintyLevel
    reasons: list[str] = Field(default_factory=list)
    propagated_from_step_ids: list[str] = Field(default_factory=list)
    should_abstain: bool = False
    suggested_response: str | None = None


class VersionedArtifact(BaseModel):
    artifact_id: str
    artifact_type: str
    name: str
    version: str
    digest: str
    source: str


class EnvironmentSnapshot(BaseModel):
    snapshot_id: str
    step_id: str | None = None
    captured_at: float | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    tool_versions: list[VersionedArtifact] = Field(default_factory=list)
    memory_digest: str | None = None
    config_flags: dict[str, Any] = Field(default_factory=dict)
    auth_scope: str | None = None
    clock_version: str | None = None


class ReplayAudit(BaseModel):
    environment_snapshot_id: str | None = None
    snapshot_coverage: float = 0.0
    deterministic_step_ids: list[str] = Field(default_factory=list)
    simulated_step_ids: list[str] = Field(default_factory=list)
    version_mismatch_step_ids: list[str] = Field(default_factory=list)
    missing_artifacts: list[str] = Field(default_factory=list)
    reused_snapshot_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FailureCluster(BaseModel):
    cluster_id: str
    label: str
    summary: str
    trace_ids: list[str] = Field(default_factory=list)
    shared_signals: list[str] = Field(default_factory=list)
    failure_categories: list[str] = Field(default_factory=list)
    recommended_scopes: list[str] = Field(default_factory=list)
    recurring_memory_keys: list[str] = Field(default_factory=list)


class TraceAnalysis(BaseModel):
    deterministic_replay_step_ids: list[str] = Field(default_factory=list)
    deterministic_replay_coverage: float = 0.0
    contradiction_findings: list[ContradictionFinding] = Field(default_factory=list)
    provenance_links: list[ProvenanceLink] = Field(default_factory=list)
    repair_suggestions: list[RepairSuggestion] = Field(default_factory=list)
    memory_corruption_issues: list[MemoryCorruptionIssue] = Field(default_factory=list)
    uncertainty_signals: list[UncertaintySignal] = Field(default_factory=list)
    contradictory_step_ids: list[str] = Field(default_factory=list)
    root_memory_source_step_ids: list[str] = Field(default_factory=list)
    cluster_ids: list[str] = Field(default_factory=list)
    cluster_labels: list[str] = Field(default_factory=list)
    environment_coverage: float = 0.0
    final_uncertainty: float = 0.0
    abstention_recommended: bool = False
    abstention_reason: str | None = None
    summary: str = ""


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
    claims: list[str] = Field(default_factory=list)
    memory_reads: list[str] = Field(default_factory=list)
    memory_writes: list[str] = Field(default_factory=list)
    tool_snapshot: ToolSnapshot | None = None
    environment_snapshot: EnvironmentSnapshot | None = None
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
    analysis: TraceAnalysis | None = None
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
    deterministic_replay_step_ids: list[str] = Field(default_factory=list)
    snapshot_miss_step_ids: list[str] = Field(default_factory=list)
    remaining_contradictions: list[ContradictionFinding] = Field(default_factory=list)
    provenance_links: list[ProvenanceLink] = Field(default_factory=list)
    repair_suggestions: list[RepairSuggestion] = Field(default_factory=list)
    memory_corruption_issues: list[MemoryCorruptionIssue] = Field(default_factory=list)
    uncertainty_signals: list[UncertaintySignal] = Field(default_factory=list)
    abstention_recommended: bool = False
    abstention_reason: str | None = None
    replay_audit: ReplayAudit | None = None


class GeneratedEval(BaseModel):
    eval_id: str
    trigger_pattern: str
    assertions: list[dict[str, Any]]
    created_from_trace_id: str
    fix_description: str


class DiagnosisRequest(BaseModel):
    trace_id: str
    suspected_step_id: str | None = None
    model: str | None = None


class ReplayRequest(BaseModel):
    trace_id: str
    fork_step_id: str
    user_modification: str
    model: str | None = None


class EvalRequest(BaseModel):
    trace_id: str
    fork_id: str
    diagnosis: Diagnosis | None = None


class ImportTraceRequest(BaseModel):
    framework_hint: ImportFramework = "auto"
    payload: Any
    source_name: str | None = None
    title_override: str | None = None
    task_description_override: str | None = None


class ImportedTraceResult(BaseModel):
    framework_detected: ImportFramework
    adapter_notes: list[str] = Field(default_factory=list)
    trace: AgentTrace
