import { motion } from 'framer-motion'
import type { AgentTrace, Diagnosis, Fork, GeneratedEval, TraceStep } from '../types'

interface ComparePanelProps {
  trace: AgentTrace | null
  fork: Fork | null
  diagnosis: Diagnosis | null
  generatedEval: GeneratedEval | null
  isGeneratingEval: boolean
  onGenerateEval: () => void
}

function sumMetric(steps: TraceStep[], selector: (step: TraceStep) => number) {
  return steps.reduce((total, step) => total + selector(step), 0)
}

export function ComparePanel({
  trace,
  fork,
  diagnosis,
  generatedEval,
  isGeneratingEval,
  onGenerateEval,
}: ComparePanelProps) {
  if (!trace || !fork) {
    return (
      <section className="panel compare-panel empty-panel">
        <div className="empty-state">
          <p className="empty-symbol">&lt;/&gt;</p>
          <h2>Comparison appears after replay</h2>
          <p>
            Fork the broken step and AgentRewind will render the old vs new
            branch here.
          </p>
        </div>
      </section>
    )
  }

  const forkIndex = trace.steps.findIndex((step) => step.id === fork.fork_point_step_id)
  const originalBranch = trace.steps.slice(forkIndex)
  const originalCost = sumMetric(originalBranch, (step) => step.cost_usd)
  const newCost = sumMetric(fork.replayed_steps, (step) => step.cost_usd)
  const originalTokens = sumMetric(originalBranch, (step) => step.tokens)
  const newTokens = sumMetric(fork.replayed_steps, (step) => step.tokens)
  const originalDuration = sumMetric(originalBranch, (step) => step.duration_seconds)
  const newDuration = sumMetric(fork.replayed_steps, (step) => step.duration_seconds)

  return (
    <section className="panel compare-panel">
      <div className="panel-header">
        <p className="eyebrow">Diff / Compare</p>
        <h2>Fork Outcome</h2>
      </div>

      <div className="compare-grid">
        <motion.div className="compare-card compare-card-bad" layout>
          <div className="compare-label">Original Output</div>
          <pre className="compare-body">{trace.final_output}</pre>
        </motion.div>

        <motion.div className="compare-card compare-card-good" layout>
          <div className="compare-label">Forked Output</div>
          <pre className="compare-body">{fork.new_final_output}</pre>
        </motion.div>
      </div>

      <div className="ground-truth">
        <div className="compare-label">Expected Answer</div>
        <p>{trace.expected_output}</p>
      </div>

      <div className="metric-row">
        <div className="metric-card delta-card">
          <span className="metric-label">Cost</span>
          <div>
            <span className="strikethrough">${originalCost.toFixed(4)}</span>
            <strong>${newCost.toFixed(4)}</strong>
          </div>
        </div>
        <div className="metric-card delta-card">
          <span className="metric-label">Tokens</span>
          <div>
            <span className="strikethrough">{originalTokens}</span>
            <strong>{newTokens}</strong>
          </div>
        </div>
        <div className="metric-card delta-card">
          <span className="metric-label">Duration</span>
          <div>
            <span className="strikethrough">{originalDuration.toFixed(1)}s</span>
            <strong>{newDuration.toFixed(1)}s</strong>
          </div>
        </div>
      </div>

      <div className="assessment-box">
        <span className="assessment-status">
          {fork.quality_improved ? 'QUALITY IMPROVED' : 'NEEDS MORE WORK'}
        </span>
        <p>{fork.assessment}</p>
        {diagnosis ? <p>Fix target: {diagnosis.fix_target}</p> : null}
      </div>

      <button
        type="button"
        className="secondary-button"
        onClick={onGenerateEval}
        disabled={isGeneratingEval}
      >
        {isGeneratingEval ? 'Generating Eval...' : 'Generate Regression Eval'}
      </button>

      {generatedEval ? (
        <div className="eval-box">
          <div className="compare-label">Regression Eval JSON</div>
          <pre className="code-surface">{JSON.stringify(generatedEval, null, 2)}</pre>
        </div>
      ) : null}
    </section>
  )
}
