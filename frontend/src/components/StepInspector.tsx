import { motion } from 'framer-motion'
import type { AgentTrace, Diagnosis, Fork, TraceStep } from '../types'
import { TypewriterText } from './TypewriterText'

interface StepInspectorProps {
  trace: AgentTrace | null
  fork: Fork | null
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
  fork,
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
          <p>See the step input, output, and fix controls here.</p>
        </div>
      </section>
    )
  }

  const isForkStep = selectedStep.id.startsWith('fork_')
  const isRootCause = diagnosis?.root_cause_step_id === selectedStep.id
  const contradictions = isForkStep
    ? fork?.remaining_contradictions.filter(
        (finding) =>
          finding.left_step_id === selectedStep.id || finding.right_step_id === selectedStep.id,
      ) ?? []
    : trace.analysis?.contradiction_findings.filter(
        (finding) =>
          finding.left_step_id === selectedStep.id || finding.right_step_id === selectedStep.id,
      ) ?? []
  const provenanceLinks = isForkStep
    ? fork?.provenance_links.filter(
        (link) =>
          link.consumer_step_id === selectedStep.id || link.producer_step_id === selectedStep.id,
      ) ?? []
    : trace.analysis?.provenance_links.filter(
        (link) =>
          link.consumer_step_id === selectedStep.id || link.producer_step_id === selectedStep.id,
      ) ?? []
  const memoryIssues = isForkStep
    ? fork?.memory_corruption_issues.filter(
        (issue) =>
          issue.writer_step_id === selectedStep.id || issue.impacted_step_ids.includes(selectedStep.id),
      ) ?? []
    : trace.analysis?.memory_corruption_issues.filter(
        (issue) =>
          issue.writer_step_id === selectedStep.id || issue.impacted_step_ids.includes(selectedStep.id),
      ) ?? []
  const uncertainty = isForkStep
    ? fork?.uncertainty_signals.find((signal) => signal.step_id === selectedStep.id) ?? null
    : trace.analysis?.uncertainty_signals.find((signal) => signal.step_id === selectedStep.id) ?? null

  return (
    <section className="panel inspector-panel">
      <div className="panel-header">
        <p className="eyebrow">Step Details</p>
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
            <span>Problem Step</span>
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
          {isForkStep ? 'Saved Input' : 'Edit This Step'}
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
          <label className="field-label">Tool Data</label>
          <pre className="code-surface">
            {selectedStep.tool_name
              ? `${selectedStep.tool_name}\n${formatJson(selectedStep.tool_args)}`
              : formatJson(selectedStep.tool_result)}
          </pre>
        </div>
      </div>

      {selectedStep.tool_snapshot ? (
        <div className="inspector-block">
          <label className="field-label">Saved Tool Result</label>
          <pre className="code-surface">
            {JSON.stringify(selectedStep.tool_snapshot, null, 2)}
          </pre>
        </div>
      ) : null}

      {selectedStep.environment_snapshot ? (
        <div className="inspector-block">
          <label className="field-label">Saved App State</label>
          <pre className="code-surface">
            {JSON.stringify(selectedStep.environment_snapshot, null, 2)}
          </pre>
        </div>
      ) : null}

      {uncertainty ? (
        <div className="inspector-block">
          <label className="field-label">Confidence Warning</label>
          <div className="signal-card">
            <strong>
              {uncertainty.level} | {uncertainty.score.toFixed(2)}
            </strong>
            <p>{uncertainty.reasons.join('; ')}</p>
            {uncertainty.should_abstain ? <p>{uncertainty.suggested_response}</p> : null}
          </div>
        </div>
      ) : null}

      {contradictions.length > 0 ? (
        <div className="inspector-block">
          <label className="field-label">Conflicts</label>
          <div className="signal-list">
            {contradictions.map((finding) => (
              <div key={finding.finding_id} className="signal-card signal-card-danger">
                <strong>{finding.conflict_type}</strong>
                <p>{finding.summary}</p>
                <pre className="mini-code">
                  {finding.left_claim}
                  {'\nvs\n'}
                  {finding.right_claim}
                </pre>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {provenanceLinks.length > 0 ? (
        <div className="inspector-block">
          <label className="field-label">Where This Memory Came From</label>
          <div className="signal-list">
            {provenanceLinks.map((link) => (
              <div key={link.link_id} className="signal-card">
                <strong>
                  {link.producer_step_id} -&gt; {link.consumer_step_id}
                </strong>
                <p>{link.claim}</p>
                <p>{link.evidence}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {memoryIssues.length > 0 ? (
        <div className="inspector-block">
          <label className="field-label">Bad Memory Impact</label>
          <div className="signal-list">
            {memoryIssues.map((issue) => (
              <div key={issue.issue_id} className="signal-card signal-card-danger">
                <strong>{issue.memory_key}</strong>
                <p>{issue.summary}</p>
                <p>Impacted: {issue.impacted_step_ids.join(', ')}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {!isForkStep ? (
        <button
          type="button"
          className="replay-button"
          onClick={onReplay}
          disabled={isReplaying || !draftInput.trim()}
        >
          {isReplaying ? 'Trying Fix...' : 'Try Fix From Here'}
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
