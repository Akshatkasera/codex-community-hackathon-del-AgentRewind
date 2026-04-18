import type {
  AgentTrace,
  AsyncJob,
  Diagnosis,
  FailureCluster,
  Fork,
  GeneratedEval,
  HealthResponse,
  ImportedTraceResult,
  ImportFramework,
  TraceSummary,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')
const DEFAULT_TIMEOUT_MS = 30_000
const POLL_INTERVAL_MS = 1_250
const API_TOKEN_STORAGE_KEY = 'agentrewind.apiToken'
let asyncJobsEnabled = true

type RequestOptions = RequestInit & {
  timeoutMs?: number
}

export function readStoredApiToken() {
  try {
    return window.localStorage.getItem(API_TOKEN_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function writeStoredApiToken(token: string) {
  try {
    const normalized = token.trim()
    if (normalized) {
      window.localStorage.setItem(API_TOKEN_STORAGE_KEY, normalized)
    } else {
      window.localStorage.removeItem(API_TOKEN_STORAGE_KEY)
    }
  } catch {
    // Ignore storage failures and keep using the in-memory token only.
  }
}

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const controller = new AbortController()
  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const headers = new Headers(init?.headers ?? {})
  const apiToken = readStoredApiToken()
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (apiToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${apiToken}`)
  }

  const abortExternalSignal = () => controller.abort()
  init?.signal?.addEventListener('abort', abortExternalSignal, { once: true })
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    })
  } catch (error) {
    if (init?.signal?.aborted) {
      throw new Error('Request was cancelled.')
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds.`)
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
    init?.signal?.removeEventListener('abort', abortExternalSignal)
  }

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

async function delay(durationMs: number, signal?: AbortSignal | null) {
  await new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      signal?.removeEventListener('abort', handleAbort)
      resolve()
    }, durationMs)
    const handleAbort = () => {
      window.clearTimeout(timeoutId)
      signal?.removeEventListener('abort', handleAbort)
      reject(new Error('Request was cancelled.'))
    }
    signal?.addEventListener('abort', handleAbort, { once: true })
  })
}

async function waitForJob<TResult>(
  submittedJob: AsyncJob,
  options?: RequestOptions,
): Promise<TResult> {
  const startedAt = Date.now()
  const overallTimeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS
  while (true) {
    if (options?.signal?.aborted) {
      throw new Error('Request was cancelled.')
    }
    const elapsedMs = Date.now() - startedAt
    if (elapsedMs >= overallTimeoutMs) {
      throw new Error(`Request timed out after ${Math.round(overallTimeoutMs / 1000)} seconds.`)
    }
    const remainingTimeoutMs = Math.max(5_000, overallTimeoutMs - elapsedMs)
    const job = await request<AsyncJob<TResult>>(`/api/jobs/${submittedJob.job_id}`, {
      signal: options?.signal,
      timeoutMs: Math.min(remainingTimeoutMs, DEFAULT_TIMEOUT_MS),
    })
    if (job.status === 'completed') {
      return job.result as TResult
    }
    if (job.status === 'failed') {
      throw new Error(job.error ?? 'Background job failed.')
    }
    await delay(POLL_INTERVAL_MS, options?.signal)
  }
}

export async function fetchHealth(options?: RequestOptions) {
  const health = await request<HealthResponse>('/health', options)
  asyncJobsEnabled = health.async_jobs
  return health
}

export function fetchTraces(options?: RequestOptions) {
  return request<TraceSummary[]>('/api/traces', options)
}

export function fetchClusters(options?: RequestOptions) {
  return request<FailureCluster[]>('/api/clusters', options)
}

export function fetchTrace(traceId: string, options?: RequestOptions) {
  return request<AgentTrace>(`/api/traces/${traceId}`, options)
}

export function diagnoseTrace(
  params: {
    traceId: string
    suspectedStepId?: string
    model?: string
    trace?: AgentTrace | null
  },
  options?: RequestOptions,
) {
  const payload = {
    trace_id: params.traceId,
    suspected_step_id: params.suspectedStepId ?? null,
    model: params.model ?? null,
    trace: params.trace ?? null,
  }
  if (asyncJobsEnabled) {
    return request<AsyncJob>('/api/diagnose/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
      ...options,
    }).then((submittedJob) => waitForJob<Diagnosis>(submittedJob, options))
  }
  return request<Diagnosis>('/api/diagnose', {
    method: 'POST',
    body: JSON.stringify(payload),
    ...options,
  })
}

export function replayTrace(
  params: {
    traceId: string
    forkStepId: string
    userModification: string
    model?: string
    trace?: AgentTrace | null
  },
  options?: RequestOptions,
) {
  const payload = {
    trace_id: params.traceId,
    fork_step_id: params.forkStepId,
    user_modification: params.userModification,
    model: params.model ?? null,
    trace: params.trace ?? null,
  }
  if (asyncJobsEnabled) {
    return request<AsyncJob>('/api/replay/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
      ...options,
    }).then((submittedJob) => waitForJob<Fork>(submittedJob, options))
  }
  return request<Fork>('/api/replay', {
    method: 'POST',
    body: JSON.stringify(payload),
    ...options,
  })
}

export function generateEval(
  params: {
    traceId: string
    forkId: string
    diagnosis: Diagnosis | null
    trace?: AgentTrace | null
    fork?: Fork | null
  },
  options?: RequestOptions,
) {
  const payload = {
    trace_id: params.traceId,
    fork_id: params.forkId,
    diagnosis: params.diagnosis,
    trace: params.trace ?? null,
    fork: params.fork ?? null,
  }
  if (asyncJobsEnabled) {
    return request<AsyncJob>('/api/evals/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
      ...options,
    }).then((submittedJob) => waitForJob<GeneratedEval>(submittedJob, options))
  }
  return request<GeneratedEval>('/api/evals', {
    method: 'POST',
    body: JSON.stringify(payload),
    ...options,
  })
}

export function importTrace(options: {
  frameworkHint: ImportFramework
  payload: unknown
  sourceName?: string | null
  titleOverride?: string | null
  taskDescriptionOverride?: string | null
  timeoutMs?: number
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
    timeoutMs: options.timeoutMs,
  })
}
