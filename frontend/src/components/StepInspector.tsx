import { motion } from 'framer-motion'
import type { AgentTrace, Diagnosis, TraceStep } from '../types'
import { TypewriterText } from './TypewriterText'

interface StepInspectorProps {
  trace: AgentTrace | null
  selectedStep: TraceStep | null
  diagnosis: Diagnosis | null
  draftInput: string
  onDraftInputChange: (nextValue: string) => void
  onReplay: () => void
  isReplaying: boolean
}

function formatJson(value: unknown) {
  if (!value) {
    return 'None'
  }
  if (typeof value === 'string') {
    return value
  }
  return JSON.stringify(value, null, 2)
}

export function StepInspector({
  trace,
  selectedStep,
  diagnosis,
  draftInput,
  onDraftInputChange,
  onReplay,
  isReplaying,
}: StepInspectorProps) {
  if (!selectedStep || !trace) {
    return (
      <section className="panel inspector-panel empty-panel">
        <div className="empty-state">
          <p className="empty-symbol">[ ]</p>
          <h2>Click any step to inspect</h2>
          <p>
            AgentRewind shows the failing prompt, the downstream output, and the
            replay controls here.
          </p>
        </div>
      </section>
    )
  }

  const isForkStep = selectedStep.id.startsWith('fork_')
  const isRootCause = diagnosis?.root_cause_step_id === selectedStep.id

  return (
    <section className="panel inspector-panel">
      <div className="panel-header">
        <p className="eyebrow">Step Inspector</p>
        <h2>{selectedStep.agent_name}</h2>
      </div>

      <div className="metadata-grid">
        <div className="meta-chip">{selectedStep.id}</div>
        <div className="meta-chip">{selectedStep.step_type.toUpperCase()}</div>
        <div className={`meta-chip status-${selectedStep.status}`}>
          {selectedStep.status.toUpperCase()}
        </div>
        {diagnosis ? (
          <div className="meta-chip subtle-chip">
            confidence {diagnosis.confidence}%
          </div>
        ) : null}
      </div>

      {isRootCause && diagnosis ? (
        <motion.div
          className="diagnosis-box"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="diagnosis-headline">
            <span>Root Cause</span>
            <span>{diagnosis.failure_category}</span>
          </div>
          <p className="diagnosis-text">
            <TypewriterText key={diagnosis.explanation} text={diagnosis.explanation} />
          </p>
          <p className="diagnosis-fix">{diagnosis.suggested_fix}</p>
        </motion.div>
      ) : null}

      <div className="inspector-block">
        <label className="field-label">
          {isForkStep ? 'Forked Input Snapshot' : 'Editable Step Input'}
        </label>
        <textarea
          className="inspector-textarea"
          value={isForkStep ? selectedStep.input_prompt : draftInput}
          readOnly={isForkStep}
          onChange={(event) => onDraftInputChange(event.target.value)}
        />
      </div>

      <div className="inspector-columns">
        <div className="inspector-block">
          <label className="field-label">Output</label>
          <pre className="code-surface">{selectedStep.output_response}</pre>
        </div>
        <div className="inspector-block">
          <label className="field-label">Tool Context</label>
          <pre className="code-surface">
            {selectedStep.tool_name
              ? `${selectedStep.tool_name}\n${formatJson(selectedStep.tool_args)}`
              : formatJson(selectedStep.tool_result)}
          </pre>
        </div>
      </div>

      {!isForkStep ? (
        <button
          type="button"
          className="replay-button"
          onClick={onReplay}
          disabled={isReplaying || !draftInput.trim()}
        >
          {isReplaying ? 'Replaying...' : 'Replay From This Point'}
        </button>
      ) : null}

      <div className="metric-row">
        <div className="metric-card">
          <span className="metric-label">Cost</span>
          <strong>${selectedStep.cost_usd.toFixed(4)}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">Tokens</span>
          <strong>{selectedStep.tokens}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">Duration</span>
          <strong>{selectedStep.duration_seconds.toFixed(1)}s</strong>
        </div>
      </div>
    </section>
  )
}
