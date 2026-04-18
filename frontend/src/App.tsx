import { useDeferredValue, useEffect, useState, useTransition, type ChangeEvent } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import './App.css'
import {
  diagnoseTrace,
  fetchClusters,
  fetchHealth,
  fetchTrace,
  fetchTraces,
  generateEval,
  importTrace,
  replayTrace,
} from './api'
import { ComparePanel } from './components/ComparePanel'
import { StepInspector } from './components/StepInspector'
import { TimelinePanel } from './components/TimelinePanel'
import type {
  AgentTrace,
  Diagnosis,
  FailureCluster,
  Fork,
  GeneratedEval,
  HealthResponse,
  ImportFramework,
  TraceSummary,
} from './types'

const importFrameworkOptions: Array<{
  value: ImportFramework
  label: string
  description: string
}> = [
  { value: 'auto', label: 'Auto Detect', description: 'Detect the source format automatically.' },
  { value: 'langgraph', label: 'LangGraph', description: 'Node/event exports from LangGraph.' },
  { value: 'crewai', label: 'CrewAI', description: 'Crew and task execution exports.' },
  { value: 'autogen', label: 'AutoGen', description: 'Conversation or message exports.' },
  { value: 'openai_agents', label: 'Agents SDK', description: 'Items or span exports.' },
  { value: 'agentrewind', label: 'AgentRewind', description: 'Already normalized run data.' },
  { value: 'generic', label: 'Generic JSON', description: 'Fallback for custom step or event lists.' },
]

function App() {
  const [traceSummaries, setTraceSummaries] = useState<TraceSummary[]>([])
  const [clusters, setClusters] = useState<FailureCluster[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [analysisModel, setAnalysisModel] = useState('')
  const [retryModel, setRetryModel] = useState('')
  const [activeTraceId, setActiveTraceId] = useState<string | null>(null)
  const [trace, setTrace] = useState<AgentTrace | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null)
  const [fork, setFork] = useState<Fork | null>(null)
  const [generatedEval, setGeneratedEval] = useState<GeneratedEval | null>(null)
  const [draftInput, setDraftInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isImportOpen, setIsImportOpen] = useState(false)
  const [importFrameworkHint, setImportFrameworkHint] = useState<ImportFramework>('auto')
  const [importPayload, setImportPayload] = useState('')
  const [importSourceName, setImportSourceName] = useState('')
  const [importTitleOverride, setImportTitleOverride] = useState('')
  const [importTaskDescriptionOverride, setImportTaskDescriptionOverride] = useState('')
  const [importMessage, setImportMessage] = useState<string | null>(null)
  const [isTraceLoading, startTraceTransition] = useTransition()
  const [isDiagnosing, setIsDiagnosing] = useState(false)
  const [isReplaying, setIsReplaying] = useState(false)
  const [isGeneratingEval, setIsGeneratingEval] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const deferredSelectedStepId = useDeferredValue(selectedStepId)

  const selectedStep = resolveSelectedStep(trace, fork, deferredSelectedStepId)
  const modelOptions = health?.available_models?.length
    ? health.available_models
    : [health?.primary_model, health?.replay_model].filter(
        (modelName): modelName is string => Boolean(modelName),
      )

  useEffect(() => {
    async function bootstrap() {
      try {
        const [traceList, clusterList, apiHealth] = await Promise.all([
          fetchTraces(),
          fetchClusters(),
          fetchHealth(),
        ])
        startTraceTransition(() => {
          setTraceSummaries(traceList)
          setClusters(clusterList)
          setHealth(apiHealth)
          setAnalysisModel(apiHealth.primary_model)
          setRetryModel(apiHealth.replay_model)
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
        const result = await diagnoseTrace(
          targetTrace.trace_id,
          undefined,
          analysisModel || health?.primary_model,
        )
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
  }, [trace, analysisModel, health?.primary_model])

  async function handleReplay() {
    if (!trace || !selectedStepId) {
      return
    }

    try {
      setError(null)
      setIsReplaying(true)
      const result = await replayTrace(
        trace.trace_id,
        selectedStepId,
        draftInput,
        retryModel || health?.replay_model,
      )
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

  async function handleImport() {
    if (!importPayload.trim()) {
      setError('Paste or load JSON run data before importing.')
      return
    }

    let parsedPayload: unknown
    try {
      parsedPayload = JSON.parse(importPayload)
    } catch {
      setError('Import payload is not valid JSON.')
      return
    }

    try {
      setError(null)
      setImportMessage(null)
      setIsImporting(true)
      const result = await importTrace({
        frameworkHint: importFrameworkHint,
        payload: parsedPayload,
        sourceName: importSourceName || null,
        titleOverride: importTitleOverride || null,
        taskDescriptionOverride: importTaskDescriptionOverride || null,
      })
      const [traceList, clusterList, apiHealth] = await Promise.all([
        fetchTraces(),
        fetchClusters(),
        fetchHealth(),
      ])
      startTraceTransition(() => {
        setTraceSummaries(traceList)
        setClusters(clusterList)
        setHealth(apiHealth)
        setActiveTraceId(result.trace.trace_id)
        setTrace(result.trace)
        setSelectedStepId(result.trace.steps[0]?.id ?? null)
        setDraftInput(
          readMetadataString(result.trace.metadata.corrected_step_input) ??
            result.trace.steps[0]?.input_prompt ??
            '',
        )
        setDiagnosis(null)
        setFork(null)
        setGeneratedEval(null)
      })
      setImportMessage(
        `Imported ${result.trace.title} from ${formatImportFramework(result.framework_detected)}. ${result.adapter_notes[0] ?? ''}`,
      )
      setImportPayload('')
      setImportSourceName('')
      setImportTitleOverride('')
      setImportTaskDescriptionOverride('')
      setIsImportOpen(false)
    } catch (importError) {
      setError(getErrorMessage(importError))
    } finally {
      setIsImporting(false)
    }
  }

  async function handleImportFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    try {
      const contents = await file.text()
      setImportPayload(contents)
      setImportSourceName(file.name)
      setImportMessage(`Loaded ${file.name}. Choose a source type or leave auto-detect.`)
    } catch {
      setError('Failed to read the selected file.')
    } finally {
      event.target.value = ''
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
        <div className="brand-block">
          <div className="brand-row">
            <img className="brand-logo" src="/agentrewindlogo.png" alt="AgentRewind logo" />
            <div className="brand-copy">
              <p className="eyebrow">Multi-agent system debugging</p>
              <h1>AgentRewind</h1>
            </div>
          </div>
          <p className="headline-copy">
            Open a failed run, fix the broken step, and see how the result changes.
          </p>
          <div className="hero-actions">
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={() => setIsImportOpen((currentValue) => !currentValue)}
            >
              {isImportOpen ? 'Close Import' : 'Import a Run'}
            </button>
            {importMessage ? <p className="import-message">{importMessage}</p> : null}
          </div>
        </div>
        <div className="status-rail">
          <div className="status-card">
            <span className="status-card-label">Connection</span>
            <strong>{health?.llm_mode === 'openai' ? 'Connected' : 'Demo Mode'}</strong>
          </div>
          <div className="status-card status-card-model">
            <span className="status-card-label">Analysis</span>
            <strong>Choose GPT model</strong>
            <span className="status-card-copy">
              GPT model used to analyze the current run.
            </span>
            <select
              className="status-select"
              value={analysisModel || health?.primary_model || ''}
              onChange={(event) => setAnalysisModel(event.target.value)}
              disabled={health?.llm_mode !== 'openai' || modelOptions.length === 0}
            >
              {modelOptions.map((modelName) => (
                <option key={`analysis-${modelName}`} value={modelName}>
                  {modelName}
                </option>
              ))}
            </select>
          </div>
          <div className="status-card status-card-model">
            <span className="status-card-label">Retry</span>
            <strong>Choose GPT model</strong>
            <span className="status-card-copy">
              GPT model used to retry the run after your fix.
            </span>
            <select
              className="status-select"
              value={retryModel || health?.replay_model || ''}
              onChange={(event) => setRetryModel(event.target.value)}
              disabled={health?.llm_mode !== 'openai' || modelOptions.length === 0}
            >
              {modelOptions.map((modelName) => (
                <option key={`retry-${modelName}`} value={modelName}>
                  {modelName}
                </option>
              ))}
            </select>
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

      <AnimatePresence>
        {isImportOpen ? (
          <motion.section
            className="import-panel"
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
          >
            <div className="panel-header">
              <p className="eyebrow">Import Data</p>
              <h2>Add Your Own Run</h2>
            </div>

            <div className="import-grid">
              <label className="import-field">
                <span className="field-label">Source Type</span>
                <select
                  className="import-select"
                  value={importFrameworkHint}
                  onChange={(event) =>
                    setImportFrameworkHint(event.target.value as ImportFramework)
                  }
                >
                  {importFrameworkOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <span className="import-help">
                  {
                    importFrameworkOptions.find((option) => option.value === importFrameworkHint)
                      ?.description
                  }
                </span>
              </label>

              <label className="import-field">
                <span className="field-label">Title</span>
                <input
                  className="import-input"
                  value={importTitleOverride}
                  onChange={(event) => setImportTitleOverride(event.target.value)}
                  placeholder="Optional run title"
                />
              </label>

              <label className="import-field import-field-wide">
                <span className="field-label">Task</span>
                <input
                  className="import-input"
                  value={importTaskDescriptionOverride}
                  onChange={(event) => setImportTaskDescriptionOverride(event.target.value)}
                  placeholder="Optional task description"
                />
              </label>
            </div>

            <div className="import-upload-row">
              <label className="trace-chip upload-chip">
                <input type="file" accept=".json,application/json" onChange={handleImportFileChange} />
                Load JSON File
              </label>
              <span className="import-help">
                {importSourceName ? `Loaded file: ${importSourceName}` : 'Or paste exported run data below.'}
              </span>
            </div>

            <label className="field-label">Run JSON</label>
            <textarea
              className="inspector-textarea import-textarea"
              value={importPayload}
              onChange={(event) => setImportPayload(event.target.value)}
              placeholder="Paste LangGraph, CrewAI, AutoGen, Agents SDK, AgentRewind, or generic JSON here."
            />

            <div className="import-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={handleImport}
                disabled={isImporting}
              >
                {isImporting ? 'Importing...' : 'Import Run'}
              </button>
              <button
                type="button"
                className="trace-chip"
                onClick={() => setIsImportOpen(false)}
              >
                Cancel
              </button>
            </div>
          </motion.section>
        ) : null}
      </AnimatePresence>

      <div className="workspace">
        <TimelinePanel
          traces={traceSummaries}
          activeTraceId={activeTraceId}
          currentTraceTitle={trace?.title ?? 'Loading run'}
          steps={trace?.steps ?? []}
          fork={fork}
          diagnosis={diagnosis}
          selectedStepId={selectedStepId}
          onSelectTrace={(nextTraceId) => setActiveTraceId(nextTraceId)}
          onSelectStep={(nextStepId) => handleSelectStep(nextStepId)}
        />

        <StepInspector
          trace={trace}
          fork={fork}
          selectedStep={selectedStep}
          diagnosis={diagnosis}
          draftInput={draftInput}
          onDraftInputChange={setDraftInput}
          onReplay={handleReplay}
          isReplaying={isReplaying}
        />

        <ComparePanel
          trace={trace}
          clusters={clusters}
          fork={fork}
          diagnosis={diagnosis}
          generatedEval={generatedEval}
          isGeneratingEval={isGeneratingEval}
          onGenerateEval={handleGenerateEval}
        />
      </div>

      <footer className="footer-note">
        <span>{isTraceLoading ? 'Loading run...' : `${traceSummaries.length} sample runs loaded`}</span>
        <span>{health?.cluster_count ?? clusters.length} issue patterns indexed</span>
        <span>{isDiagnosing ? 'Checking the run...' : 'Analysis ready'}</span>
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

function formatImportFramework(framework: ImportFramework) {
  return importFrameworkOptions.find((option) => option.value === framework)?.label ?? 'Imported data'
}

export default App
