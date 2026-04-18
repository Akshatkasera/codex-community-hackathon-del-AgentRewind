export type StepType = 'llm' | 'tool' | 'analysis' | 'review'
export type StepStatus = 'ok' | 'warning' | 'error'

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
  primary_model: string
  replay_model: string
}
