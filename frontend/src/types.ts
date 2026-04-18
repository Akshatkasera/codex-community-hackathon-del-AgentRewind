export type StepType = 'llm' | 'tool' | 'analysis' | 'review'
export type StepStatus = 'ok' | 'warning' | 'error'
export type ContradictionStatus = 'unresolved' | 'explained' | 'resolved'
export type ImportFramework =
  | 'auto'
  | 'agentrewind'
  | 'langgraph'
  | 'crewai'
  | 'autogen'
  | 'openai_agents'
  | 'generic'
export type RepairScope =
  | 'prompt'
  | 'retrieval_policy'
  | 'tool_contract'
  | 'memory_guard'
  | 'workflow'
  | 'abstain_policy'
export type ProvenanceKind =
  | 'tool_snapshot'
  | 'memory_carryover'
  | 'direct_handoff'
  | 'inferred'
export type UncertaintyLevel = 'low' | 'medium' | 'high' | 'critical'
export type AsyncJobKind = 'diagnosis' | 'replay' | 'eval'
export type AsyncJobStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface ToolSnapshot {
  snapshot_id: string
  tool_name: string
  captured_at?: number | null
  normalized_args?: Record<string, unknown> | string | null
  result?: unknown
  result_digest: string
  deterministic_replay: boolean
  invalidation_reason?: string | null
}

export interface ContradictionFinding {
  finding_id: string
  left_step_id: string
  right_step_id: string
  conflict_type: string
  summary: string
  severity: number
  left_claim: string
  right_claim: string
  status: ContradictionStatus
}

export interface RepairSuggestion {
  suggestion_id: string
  title: string
  summary: string
  target_scope: RepairScope
  target_step_id?: string | null
  patch_hint: string
  confidence: number
  auto_applicable: boolean
}

export interface ProvenanceLink {
  link_id: string
  claim: string
  producer_step_id: string
  consumer_step_id: string
  provenance_kind: ProvenanceKind
  evidence: string
}

export interface MemoryCorruptionIssue {
  issue_id: string
  memory_key: string
  writer_step_id: string
  impacted_step_ids: string[]
  summary: string
  severity: number
  persistent: boolean
  recurrence_count: number
}

export interface UncertaintySignal {
  step_id: string
  score: number
  level: UncertaintyLevel
  reasons: string[]
  propagated_from_step_ids: string[]
  should_abstain: boolean
  suggested_response?: string | null
}

export interface VersionedArtifact {
  artifact_id: string
  artifact_type: string
  name: string
  version: string
  digest: string
  source: string
}

export interface EnvironmentSnapshot {
  snapshot_id: string
  step_id?: string | null
  captured_at?: number | null
  model_name?: string | null
  prompt_version?: string | null
  tool_versions: VersionedArtifact[]
  memory_digest?: string | null
  config_flags: Record<string, unknown>
  auth_scope?: string | null
  clock_version?: string | null
}

export interface ReplayAudit {
  environment_snapshot_id?: string | null
  snapshot_coverage: number
  deterministic_step_ids: string[]
  simulated_step_ids: string[]
  version_mismatch_step_ids: string[]
  missing_artifacts: string[]
  reused_snapshot_ids: string[]
  notes: string[]
}

export interface FailureCluster {
  cluster_id: string
  label: string
  summary: string
  trace_ids: string[]
  shared_signals: string[]
  failure_categories: string[]
  recommended_scopes: string[]
  recurring_memory_keys: string[]
}

export interface TraceAnalysis {
  deterministic_replay_step_ids: string[]
  deterministic_replay_coverage: number
  contradiction_findings: ContradictionFinding[]
  provenance_links: ProvenanceLink[]
  repair_suggestions: RepairSuggestion[]
  memory_corruption_issues: MemoryCorruptionIssue[]
  uncertainty_signals: UncertaintySignal[]
  contradictory_step_ids: string[]
  root_memory_source_step_ids: string[]
  cluster_ids: string[]
  cluster_labels: string[]
  environment_coverage: number
  final_uncertainty: number
  abstention_recommended: boolean
  abstention_reason?: string | null
  summary: string
}

export interface TraceStep {
  id: string
  agent_name: string
  step_type: StepType
  status: StepStatus
  tool_name?: string | null
  tool_args?: Record<string, unknown> | string | null
  tool_result?: unknown
  input_prompt: string
  output_response: string
  timestamp: number
  cost_usd: number
  tokens: number
  duration_seconds: number
  claims: string[]
  memory_reads: string[]
  memory_writes: string[]
  tool_snapshot?: ToolSnapshot | null
  environment_snapshot?: EnvironmentSnapshot | null
  metadata: Record<string, unknown>
}

export interface AgentTrace {
  trace_id: string
  title: string
  task_description: string
  expected_output?: string | null
  final_output: string
  steps: TraceStep[]
  failure_summary?: string | null
  tags: string[]
  analysis?: TraceAnalysis | null
  metadata: Record<string, unknown>
}

export interface TraceSummary {
  trace_id: string
  title: string
  task_description: string
  failure_summary?: string | null
  tags: string[]
}

export interface Diagnosis {
  root_cause_step_id: string
  confidence: number
  blame_agent: string
  failure_category: string
  explanation: string
  suggested_fix: string
  fix_target: string
}

export interface Fork {
  fork_id: string
  original_trace_id: string
  fork_point_step_id: string
  user_modification: string
  replayed_steps: TraceStep[]
  new_final_output: string
  new_success: boolean
  cost_delta: number
  quality_improved: boolean
  assessment?: string | null
  deterministic_replay_step_ids: string[]
  snapshot_miss_step_ids: string[]
  remaining_contradictions: ContradictionFinding[]
  provenance_links: ProvenanceLink[]
  repair_suggestions: RepairSuggestion[]
  memory_corruption_issues: MemoryCorruptionIssue[]
  uncertainty_signals: UncertaintySignal[]
  abstention_recommended: boolean
  abstention_reason?: string | null
  replay_audit?: ReplayAudit | null
}

export interface GeneratedEval {
  eval_id: string
  trigger_pattern: string
  assertions: Array<Record<string, unknown>>
  created_from_trace_id: string
  fix_description: string
}

export interface HealthResponse {
  status: string
  trace_count: number
  llm_mode: 'openai' | 'mock'
  available_models: string[]
  primary_model: string
  replay_model: string
  cluster_count?: number
  auth_required: boolean
  storage_backend: string
  async_jobs: boolean
  rate_limit_requests_per_minute: number
  rate_limit_heavy_requests_per_minute: number
}

export interface ImportedTraceResult {
  framework_detected: ImportFramework
  adapter_notes: string[]
  trace: AgentTrace
}

export interface AsyncJob<T = unknown> {
  job_id: string
  kind: AsyncJobKind
  status: AsyncJobStatus
  trace_id?: string | null
  created_at: number
  updated_at: number
  request_id?: string | null
  result?: T | null
  error?: string | null
}
