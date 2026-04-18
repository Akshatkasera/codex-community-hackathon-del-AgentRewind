from __future__ import annotations

import math
from uuid import uuid4

from .models import AgentTrace, TraceStep


MODEL_PRICING = {
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


def count_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def estimate_cost(prompt_text: str, completion_text: str, model: str) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])
    input_tokens = count_tokens(prompt_text)
    output_tokens = count_tokens(completion_text)
    return round(
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"],
        6,
    )


def generate_uuid() -> str:
    return str(uuid4())


def format_trace_for_llm(trace: AgentTrace) -> str:
    output: list[str] = []
    if trace.analysis:
        output.append("=== TRACE ANALYSIS ===")
        output.append(f"Summary: {trace.analysis.summary}")
        if trace.analysis.cluster_labels:
            output.append(f"Clusters: {', '.join(trace.analysis.cluster_labels)}")
        if trace.analysis.root_memory_source_step_ids:
            output.append(
                f"Root memory sources: {', '.join(trace.analysis.root_memory_source_step_ids)}"
            )
        if trace.analysis.contradiction_findings:
            output.append("Contradictions:")
            for finding in trace.analysis.contradiction_findings:
                output.append(
                    f"- {finding.left_step_id} vs {finding.right_step_id}: {finding.summary}"
                )
        if trace.analysis.memory_corruption_issues:
            output.append("Persistent memory issues:")
            for issue in trace.analysis.memory_corruption_issues:
                output.append(
                    f"- {issue.memory_key} from {issue.writer_step_id}: {issue.summary}"
                )
        if trace.analysis.repair_suggestions:
            output.append("Suggested repairs:")
            for suggestion in trace.analysis.repair_suggestions:
                output.append(
                    f"- [{suggestion.target_scope}] {suggestion.title}: {suggestion.patch_hint}"
                )
        if trace.analysis.uncertainty_signals:
            final_signal = trace.analysis.uncertainty_signals[-1]
            output.append(
                f"Final uncertainty: {final_signal.score:.2f} ({final_signal.level})"
            )
        if trace.analysis.abstention_recommended:
            output.append(
                f"Abstention recommended: {trace.analysis.abstention_reason or 'yes'}"
            )
        output.append("")
    for index, step in enumerate(trace.steps, start=1):
        output.append(f"--- STEP {index} (id: {step.id}) ---")
        output.append(f"Agent: {step.agent_name}")
        output.append(f"Type: {step.step_type}")
        output.append(f"Status: {step.status}")
        if step.tool_name:
            output.append(f"Tool: {step.tool_name}({step.tool_args})")
        if step.tool_result:
            output.append(f"Tool result: {step.tool_result}")
        if step.tool_snapshot:
            output.append(
                "Tool snapshot: "
                f"id={step.tool_snapshot.snapshot_id} digest={step.tool_snapshot.result_digest}"
            )
        output.append(f"Input: {step.input_prompt}")
        output.append(f"Output: {step.output_response}")
        if step.claims:
            output.append(f"Claims: {step.claims}")
        if step.memory_reads:
            output.append(f"Memory reads: {step.memory_reads}")
        if step.memory_writes:
            output.append(f"Memory writes: {step.memory_writes}")
        if step.environment_snapshot:
            output.append(
                "Environment snapshot: "
                f"id={step.environment_snapshot.snapshot_id} "
                f"model={step.environment_snapshot.model_name or 'n/a'} "
                f"prompt={step.environment_snapshot.prompt_version or 'n/a'}"
            )
        if step.metadata:
            output.append(f"Metadata: {step.metadata}")
        output.append("")
    return "\n".join(output)


def format_prior_context(steps: list[TraceStep]) -> str:
    if not steps:
        return "No prior context."
    output: list[str] = []
    for index, step in enumerate(steps, start=1):
        output.append(
            f"{index}. {step.agent_name} [{step.step_type}/{step.status}] -> {step.output_response}"
        )
    return "\n".join(output)


def sum_cost(steps: list[TraceStep]) -> float:
    return round(sum(step.cost_usd for step in steps), 6)


def sum_tokens(steps: list[TraceStep]) -> int:
    return sum(step.tokens for step in steps)


def sum_duration(steps: list[TraceStep]) -> float:
    return round(sum(step.duration_seconds for step in steps), 2)
