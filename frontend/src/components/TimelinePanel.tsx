import type { CSSProperties } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { Diagnosis, Fork, TraceStep, TraceSummary } from '../types'

interface TimelinePanelProps {
  traces: TraceSummary[]
  activeTraceId: string | null
  currentTraceTitle: string
  steps: TraceStep[]
  fork: Fork | null
  diagnosis: Diagnosis | null
  selectedStepId: string | null
  onSelectTrace: (traceId: string) => void
  onSelectStep: (stepId: string) => void
}

const agentPalette = ['#36f3ff', '#8bff8b', '#ffe45e', '#ff63f8', '#ff9d42']

function agentColor(agentName: string) {
  const hash = Array.from(agentName).reduce(
    (accumulator, character) => accumulator + character.charCodeAt(0),
    0,
  )
  return agentPalette[hash % agentPalette.length]
}

function formatCost(cost: number) {
  return `$${cost.toFixed(4)}`
}

function StepCard({
  step,
  index,
  selected,
  dimmed,
  rootCause,
  onClick,
}: {
  step: TraceStep
  index: number
  selected: boolean
  dimmed: boolean
  rootCause: boolean
  onClick: () => void
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      className={[
        'timeline-card',
        selected ? 'is-selected' : '',
        dimmed ? 'is-dimmed' : '',
        rootCause ? 'is-root-cause' : '',
        step.id.startsWith('fork_') ? 'is-forked' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      style={
        {
          '--agent-color': agentColor(step.agent_name),
        } as CSSProperties
      }
      layout
      transition={{ duration: 0.22, ease: 'easeOut' }}
    >
      <div className="timeline-step-top">
        <span className="timeline-step-index">
          {step.id.startsWith('fork_') ? 'F' : 'S'}
          {String(index + 1).padStart(2, '0')}
        </span>
        <span className={`status-pill status-${step.status}`}>
          {step.status === 'ok' ? 'OK' : step.status === 'warning' ? 'WARN' : 'ERR'}
        </span>
      </div>
      <div className="timeline-agent-row">
        <span className="timeline-agent-dot" />
        <span className="timeline-agent-name">{step.agent_name}</span>
      </div>
      <div className="timeline-step-meta">
        <span>{step.step_type.toUpperCase()}</span>
        <span>{formatCost(step.cost_usd)}</span>
      </div>
    </motion.button>
  )
}

export function TimelinePanel({
  traces,
  activeTraceId,
  currentTraceTitle,
  steps,
  fork,
  diagnosis,
  selectedStepId,
  onSelectTrace,
  onSelectStep,
}: TimelinePanelProps) {
  return (
    <aside className="panel timeline-panel">
      <div className="panel-header">
        <p className="eyebrow">Run Timeline</p>
        <h2>{currentTraceTitle}</h2>
      </div>

      <div className="trace-selector">
        {traces.map((trace) => (
          <button
            key={trace.trace_id}
            type="button"
            className={trace.trace_id === activeTraceId ? 'trace-chip is-active' : 'trace-chip'}
            onClick={() => onSelectTrace(trace.trace_id)}
          >
            {trace.title}
          </button>
        ))}
      </div>

      <div className="timeline-scroll">
        {steps.map((step, index) => (
          <StepCard
            key={step.id}
            step={step}
            index={index}
            selected={selectedStepId === step.id}
            dimmed={Boolean(fork)}
            rootCause={diagnosis?.root_cause_step_id === step.id}
            onClick={() => onSelectStep(step.id)}
          />
        ))}

        <AnimatePresence>
          {fork ? (
            <motion.div
              className="fork-separator"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 12 }}
              layout
            >
              <span>New Path</span>
            </motion.div>
          ) : null}
        </AnimatePresence>

        <AnimatePresence>
          {fork
            ? fork.replayed_steps.map((step, index) => (
                <StepCard
                  key={step.id}
                  step={step}
                  index={index}
                  selected={selectedStepId === step.id}
                  dimmed={false}
                  rootCause={false}
                  onClick={() => onSelectStep(step.id)}
                />
              ))
            : null}
        </AnimatePresence>
      </div>
    </aside>
  )
}
