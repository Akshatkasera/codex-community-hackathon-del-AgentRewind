import type {
  AgentTrace,
  Diagnosis,
  FailureCluster,
  Fork,
  GeneratedEval,
  HealthResponse,
  ImportedTraceResult,
  ImportFramework,
  TraceSummary,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      detail = payload.detail ?? detail
    } catch {
      // Ignore parse errors and use the HTTP status line.
    }
    throw new Error(detail)
  }

  return response.json() as Promise<T>
}

export function fetchHealth() {
  return request<HealthResponse>('/health')
}

export function fetchTraces() {
  return request<TraceSummary[]>('/api/traces')
}

export function fetchClusters() {
  return request<FailureCluster[]>('/api/clusters')
}

export function fetchTrace(traceId: string) {
  return request<AgentTrace>(`/api/traces/${traceId}`)
}

export function diagnoseTrace(traceId: string, suspectedStepId?: string) {
  return request<Diagnosis>('/api/diagnose', {
    method: 'POST',
    body: JSON.stringify({
      trace_id: traceId,
      suspected_step_id: suspectedStepId ?? null,
    }),
  })
}

export function replayTrace(
  traceId: string,
  forkStepId: string,
  userModification: string,
) {
  return request<Fork>('/api/replay', {
    method: 'POST',
    body: JSON.stringify({
      trace_id: traceId,
      fork_step_id: forkStepId,
      user_modification: userModification,
    }),
  })
}

export function generateEval(
  traceId: string,
  forkId: string,
  diagnosis: Diagnosis | null,
) {
  return request<GeneratedEval>('/api/evals', {
    method: 'POST',
    body: JSON.stringify({
      trace_id: traceId,
      fork_id: forkId,
      diagnosis,
    }),
  })
}

export function importTrace(options: {
  frameworkHint: ImportFramework
  payload: unknown
  sourceName?: string | null
  titleOverride?: string | null
  taskDescriptionOverride?: string | null
}) {
  return request<ImportedTraceResult>('/api/imports', {
    method: 'POST',
    body: JSON.stringify({
      framework_hint: options.frameworkHint,
      payload: options.payload,
      source_name: options.sourceName ?? null,
      title_override: options.titleOverride ?? null,
      task_description_override: options.taskDescriptionOverride ?? null,
    }),
  })
}
