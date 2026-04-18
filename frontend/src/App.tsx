import { useDeferredValue, useEffect, useState, useTransition } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import './App.css'
import { diagnoseTrace, fetchHealth, fetchTrace, fetchTraces, generateEval, replayTrace } from './api'
import { ComparePanel } from './components/ComparePanel'
import { StepInspector } from './components/StepInspector'
import { TimelinePanel } from './components/TimelinePanel'
import type {
  AgentTrace,
  Diagnosis,
  Fork,
  GeneratedEval,
  HealthResponse,
  TraceSummary,
} from './types'

function App() {
  const [traceSummaries, setTraceSummaries] = useState<TraceSummary[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [activeTraceId, setActiveTraceId] = useState<string | null>(null)
  const [trace, setTrace] = useState<AgentTrace | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null)
  const [fork, setFork] = useState<Fork | null>(null)
  const [generatedEval, setGeneratedEval] = useState<GeneratedEval | null>(null)
  const [draftInput, setDraftInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isTraceLoading, startTraceTransition] = useTransition()
  const [isDiagnosing, setIsDiagnosing] = useState(false)
  const [isReplaying, setIsReplaying] = useState(false)
  const [isGeneratingEval, setIsGeneratingEval] = useState(false)
  const deferredSelectedStepId = useDeferredValue(selectedStepId)

  const selectedStep = resolveSelectedStep(trace, fork, deferredSelectedStepId)

  useEffect(() => {
    async function bootstrap() {
      try {
        const [traceList, apiHealth] = await Promise.all([fetchTraces(), fetchHealth()])
        startTraceTransition(() => {
          setTraceSummaries(traceList)
          setHealth(apiHealth)
          setActiveTraceId(traceList[0]?.trace_id ?? null)
        })
      } catch (bootstrapError) {
        setError(getErrorMessage(bootstrapError))
      }
    }

    bootstrap()
  }, [])

  useEffect(() => {
    if (!activeTraceId) {
      return
    }

    async function loadTrace(traceId: string) {
      try {
        setError(null)
        setDiagnosis(null)
        setFork(null)
        setGeneratedEval(null)
        const loadedTrace = await fetchTrace(traceId)
        startTraceTransition(() => {
          setTrace(loadedTrace)
          setSelectedStepId(loadedTrace.steps[0]?.id ?? null)
          setDraftInput(
            readMetadataString(loadedTrace.metadata.corrected_step_input) ??
              loadedTrace.steps[0]?.input_prompt ??
              '',
          )
        })
      } catch (traceError) {
        setError(getErrorMessage(traceError))
      }
    }

    loadTrace(activeTraceId)
  }, [activeTraceId])

  useEffect(() => {
    if (!trace) {
      return
    }

    async function runDiagnosis(targetTrace: AgentTrace) {
      try {
        setIsDiagnosing(true)
        const result = await diagnoseTrace(targetTrace.trace_id)
        setDiagnosis(result)
        setSelectedStepId(result.root_cause_step_id)
        const rootCauseStep = targetTrace.steps.find(
          (step) => step.id === result.root_cause_step_id,
        )
        setDraftInput(
          readMetadataString(targetTrace.metadata.corrected_step_input) ??
            rootCauseStep?.input_prompt ??
            '',
        )
      } catch (diagnosisError) {
        setError(getErrorMessage(diagnosisError))
      } finally {
        setIsDiagnosing(false)
      }
    }

    runDiagnosis(trace)
  }, [trace])

  async function handleReplay() {
    if (!trace || !selectedStepId) {
      return
    }

    try {
      setError(null)
      setIsReplaying(true)
      const result = await replayTrace(trace.trace_id, selectedStepId, draftInput)
      setFork(result)
      setGeneratedEval(null)
      setSelectedStepId(result.replayed_steps[0]?.id ?? result.fork_point_step_id)
    } catch (replayError) {
      setError(getErrorMessage(replayError))
    } finally {
      setIsReplaying(false)
    }
  }

  async function handleGenerateEval() {
    if (!trace || !fork) {
      return
    }

    try {
      setError(null)
      setIsGeneratingEval(true)
      const result = await generateEval(trace.trace_id, fork.fork_id, diagnosis)
      setGeneratedEval(result)
    } catch (evalError) {
      setError(getErrorMessage(evalError))
    } finally {
      setIsGeneratingEval(false)
    }
  }

  function handleSelectStep(nextStepId: string) {
    setSelectedStepId(nextStepId)
    const originalStep = trace?.steps.find((step) => step.id === nextStepId)
    if (originalStep) {
      setDraftInput(originalStep.input_prompt)
    }
  }

  return (
    <div className="shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Multi-Agent System Debugger</p>
          <h1>AgentRewind</h1>
          <p className="headline-copy">
            Rewind a broken agent trace, patch the failing handoff, then replay
            the branch forward with OpenAI in the loop.
          </p>
        </div>
        <div className="status-rail">
          <div className="status-card">
            <span className="status-card-label">Mode</span>
            <strong>{health?.llm_mode === 'openai' ? 'OpenAI Live' : 'Mock'}</strong>
          </div>
          <div className="status-card">
            <span className="status-card-label">Diagnose</span>
            <strong>{health?.primary_model ?? '...'}</strong>
          </div>
          <div className="status-card">
            <span className="status-card-label">Replay</span>
            <strong>{health?.replay_model ?? '...'}</strong>
          </div>
        </div>
      </header>

      <AnimatePresence>
        {error ? (
          <motion.div
            className="error-banner"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            {error}
          </motion.div>
        ) : null}
      </AnimatePresence>

      <div className="workspace">
        <TimelinePanel
          traces={traceSummaries}
          activeTraceId={activeTraceId}
          currentTraceTitle={trace?.title ?? 'Loading trace'}
          steps={trace?.steps ?? []}
          fork={fork}
          diagnosis={diagnosis}
          selectedStepId={selectedStepId}
          onSelectTrace={(nextTraceId) => setActiveTraceId(nextTraceId)}
          onSelectStep={(nextStepId) => handleSelectStep(nextStepId)}
        />

        <StepInspector
          trace={trace}
          selectedStep={selectedStep}
          diagnosis={diagnosis}
          draftInput={draftInput}
          onDraftInputChange={setDraftInput}
          onReplay={handleReplay}
          isReplaying={isReplaying}
        />

        <ComparePanel
          trace={trace}
          fork={fork}
          diagnosis={diagnosis}
          generatedEval={generatedEval}
          isGeneratingEval={isGeneratingEval}
          onGenerateEval={handleGenerateEval}
        />
      </div>

      <footer className="footer-note">
        <span>{isTraceLoading ? 'Loading trace...' : `${traceSummaries.length} demo traces armed`}</span>
        <span>{isDiagnosing ? 'Running AI diagnosis...' : 'Diagnosis ready'}</span>
      </footer>
    </div>
  )
}

function resolveSelectedStep(
  trace: AgentTrace | null,
  fork: Fork | null,
  stepId: string | null,
) {
  if (!trace || !stepId) {
    return null
  }
  return (
    trace.steps.find((step) => step.id === stepId) ??
    fork?.replayed_steps.find((step) => step.id === stepId) ??
    null
  )
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message
  }
  return 'Something failed while talking to the backend.'
}

function readMetadataString(value: unknown) {
  return typeof value === 'string' ? value : null
}

export default App
