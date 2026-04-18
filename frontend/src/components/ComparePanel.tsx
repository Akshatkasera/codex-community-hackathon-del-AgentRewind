import { motion } from 'framer-motion'
import type {
  AgentTrace,
  Diagnosis,
  FailureCluster,
  Fork,
  GeneratedEval,
  TraceStep,
} from '../types'

interface ComparePanelProps {
  trace: AgentTrace | null
  clusters: FailureCluster[]
  fork: Fork | null
  diagnosis: Diagnosis | null
  generatedEval: GeneratedEval | null
  isGeneratingEval: boolean
  onGenerateEval: () => void
}

function sumMetric(steps: TraceStep[], selector: (step: TraceStep) => number) {
  return steps.reduce((total, step) => total + selector(step), 0)
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

export function ComparePanel({
  trace,
  clusters,
  fork,
  diagnosis,
  generatedEval,
  isGeneratingEval,
  onGenerateEval,
}: ComparePanelProps) {
  if (!trace) {
    return (
      <section className="panel compare-panel empty-panel">
        <div className="empty-state">
          <p className="empty-symbol">&lt;/&gt;</p>
          <h2>Results appear after a run loads</h2>
          <p>AgentRewind will show what changed and whether the fix helped.</p>
        </div>
      </section>
    )
  }

  const activeClusters = clusters.filter((cluster) => cluster.trace_ids.includes(trace.trace_id))
  const analysis = trace.analysis

  return (
    <section className="panel compare-panel">
      <div className="panel-header">
        <p className="eyebrow">Compare</p>
        <h2>{fork ? 'What Changed' : 'Run Insights'}</h2>
      </div>

      <div className="signal-list">
        {activeClusters.map((cluster) => (
          <div key={cluster.cluster_id} className="signal-card">
            <strong>{cluster.label}</strong>
            <p>{cluster.summary}</p>
            <p>
              Signals: {cluster.shared_signals.join(', ') || 'none'} | Categories:{' '}
              {cluster.failure_categories.join(', ')}
            </p>
          </div>
        ))}
      </div>

      <div className="metric-row">
        <div className="metric-card">
          <span className="metric-label">Saved Tool Data</span>
          <strong>{analysis ? formatPercent(analysis.deterministic_replay_coverage) : 'n/a'}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">Saved Version Data</span>
          <strong>{analysis ? formatPercent(analysis.environment_coverage) : 'n/a'}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">Risk Score</span>
          <strong>{analysis ? analysis.final_uncertainty.toFixed(2) : 'n/a'}</strong>
        </div>
      </div>

      {analysis ? (
        <>
          <div className="inspector-block">
            <label className="field-label">Suggested Fixes</label>
            <div className="signal-list">
              {analysis.repair_suggestions.map((suggestion) => (
                <div key={suggestion.suggestion_id} className="signal-card">
                  <strong>{suggestion.title}</strong>
                  <p>{suggestion.summary}</p>
                  <p>
                    Scope: {suggestion.target_scope} | Confidence: {suggestion.confidence}%
                  </p>
                  <pre className="mini-code">{suggestion.patch_hint}</pre>
                </div>
              ))}
            </div>
          </div>

          <div className="inspector-block">
            <label className="field-label">Wrong Memory That Keeps Spreading</label>
            {analysis.memory_corruption_issues.length > 0 ? (
              <div className="signal-list">
                {analysis.memory_corruption_issues.map((issue) => (
                  <div key={issue.issue_id} className="signal-card signal-card-danger">
                    <strong>{issue.memory_key}</strong>
                    <p>{issue.summary}</p>
                    <p>
                      Writer: {issue.writer_step_id} | Impacted: {issue.impacted_step_ids.join(', ')}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="panel-copy">No repeated memory problem was found in this run.</p>
            )}
          </div>

          <div className="inspector-block">
            <label className="field-label">Low Confidence Warnings</label>
            <div className="signal-list">
              {analysis.uncertainty_signals.map((signal) => (
                <div key={signal.step_id} className="signal-card">
                  <strong>
                    {signal.step_id} | {signal.level} | {signal.score.toFixed(2)}
                  </strong>
                  <p>{signal.reasons.join('; ')}</p>
                  {signal.should_abstain ? <p>{signal.suggested_response}</p> : null}
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}

      {!fork ? (
        <div className="empty-state intelligence-empty">
          <p className="empty-symbol">::</p>
          <h2>Run a retry to see the new path</h2>
          <p>The cards above explain the original problem. Retry adds a side-by-side result.</p>
        </div>
      ) : (
        <>
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

          {renderForkMetrics(trace, fork, diagnosis)}

          {fork.replay_audit ? (
            <div className="assessment-box">
              <span className="assessment-status">RETRY CHECK</span>
              <p>Saved tool data used: {formatPercent(fork.replay_audit.snapshot_coverage)}</p>
              <p>Exact replay steps: {fork.replay_audit.deterministic_step_ids.join(', ') || 'none'}</p>
              <p>Estimated steps: {fork.replay_audit.simulated_step_ids.join(', ') || 'none'}</p>
              <p>
                Version changes:{' '}
                {fork.replay_audit.version_mismatch_step_ids.join(', ') || 'none'}
              </p>
              <p>Missing saved data: {fork.replay_audit.missing_artifacts.join(', ') || 'none'}</p>
            </div>
          ) : null}

          <button
            type="button"
            className="secondary-button"
            onClick={onGenerateEval}
            disabled={isGeneratingEval}
          >
            {isGeneratingEval ? 'Creating Test Case...' : 'Create Test Case'}
          </button>

          {generatedEval ? (
            <div className="eval-box">
              <div className="compare-label">Test Case JSON</div>
              <pre className="code-surface">{JSON.stringify(generatedEval, null, 2)}</pre>
            </div>
          ) : null}
        </>
      )}
    </section>
  )
}

function renderForkMetrics(trace: AgentTrace, fork: Fork, diagnosis: Diagnosis | null) {
  const forkIndex = trace.steps.findIndex((step) => step.id === fork.fork_point_step_id)
  const originalBranch = trace.steps.slice(forkIndex)
  const originalCost = sumMetric(originalBranch, (step) => step.cost_usd)
  const newCost = sumMetric(fork.replayed_steps, (step) => step.cost_usd)
  const originalTokens = sumMetric(originalBranch, (step) => step.tokens)
  const newTokens = sumMetric(fork.replayed_steps, (step) => step.tokens)
  const originalDuration = sumMetric(originalBranch, (step) => step.duration_seconds)
  const newDuration = sumMetric(fork.replayed_steps, (step) => step.duration_seconds)

  return (
    <>
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
          {fork.quality_improved ? 'FIX LOOKS BETTER' : 'STILL NEEDS WORK'}
        </span>
        <p>{fork.assessment}</p>
        {diagnosis ? <p>Fix target: {diagnosis.fix_target}</p> : null}
        <p>
          Exact replay: {fork.deterministic_replay_step_ids.length} steps
          {fork.snapshot_miss_step_ids.length > 0
            ? `, missing saved data on ${fork.snapshot_miss_step_ids.join(', ')}`
            : ''}
        </p>
        <p>
          Conflicts left: {fork.remaining_contradictions.length} | Memory links:{' '}
          {fork.provenance_links.length}
        </p>
        <p>
          Memory issues left: {fork.memory_corruption_issues.length} | Hold answer:{' '}
          {fork.abstention_recommended ? 'recommended' : 'not needed'}
        </p>
        {fork.abstention_reason ? <p>{fork.abstention_reason}</p> : null}
      </div>
    </>
  )
}
