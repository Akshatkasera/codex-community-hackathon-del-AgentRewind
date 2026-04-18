from __future__ import annotations

import json
import math
from uuid import uuid4

from .config import get_settings
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


def truncate_text(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 16:
        return text[:max_chars]
    return f"{text[: max_chars - 16].rstrip()} ...[truncated]"


def _format_for_llm(value: object, *, max_chars: int = 320) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return truncate_text(value, max_chars)
    try:
        serialized = json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        serialized = str(value)
    return truncate_text(serialized, max_chars)


def format_trace_for_llm(trace: AgentTrace) -> str:
    settings = get_settings()
    max_chars = settings.llm_max_trace_chars
    output: list[str] = []
    current_chars = 0

    def append_line(line: str) -> bool:
        nonlocal current_chars
        if current_chars >= max_chars:
            return False
        normalized = line.rstrip()
        projected = current_chars + len(normalized) + 1
        if projected > max_chars:
            remaining = max_chars - current_chars - 1
            if remaining > 24:
                output.append(truncate_text(normalized, remaining))
            output.append("[trace truncated to fit LLM context budget]")
            current_chars = max_chars
            return False
        output.append(normalized)
        current_chars = projected
        return True

    if trace.analysis:
        append_line("=== TRACE ANALYSIS ===")
        append_line(f"Summary: {truncate_text(trace.analysis.summary, 400)}")
        if trace.analysis.cluster_labels:
            append_line(
                f"Clusters: {truncate_text(', '.join(trace.analysis.cluster_labels), 240)}"
            )
        if trace.analysis.root_memory_source_step_ids:
            append_line(
                f"Root memory sources: {', '.join(trace.analysis.root_memory_source_step_ids)}"
            )
        if trace.analysis.contradiction_findings:
            append_line("Contradictions:")
            for finding in trace.analysis.contradiction_findings:
                if not append_line(
                    f"- {finding.left_step_id} vs {finding.right_step_id}: {finding.summary}"
                ):
                    return "\n".join(output)
        if trace.analysis.memory_corruption_issues:
            append_line("Persistent memory issues:")
            for issue in trace.analysis.memory_corruption_issues:
                if not append_line(
                    f"- {issue.memory_key} from {issue.writer_step_id}: {issue.summary}"
                ):
                    return "\n".join(output)
        if trace.analysis.repair_suggestions:
            append_line("Suggested repairs:")
            for suggestion in trace.analysis.repair_suggestions:
                if not append_line(
                    f"- [{suggestion.target_scope}] {suggestion.title}: {suggestion.patch_hint}"
                ):
                    return "\n".join(output)
        if trace.analysis.uncertainty_signals:
            final_signal = trace.analysis.uncertainty_signals[-1]
            append_line(
                f"Final uncertainty: {final_signal.score:.2f} ({final_signal.level})"
            )
        if trace.analysis.abstention_recommended:
            append_line(
                f"Abstention recommended: {trace.analysis.abstention_reason or 'yes'}"
            )
        append_line("")
    for index, step in enumerate(trace.steps, start=1):
        if not append_line(f"--- STEP {index} (id: {step.id}) ---"):
            break
        append_line(f"Agent: {truncate_text(step.agent_name, 120)}")
        append_line(f"Type: {step.step_type}")
        append_line(f"Status: {step.status}")
        if step.tool_name:
            append_line(
                f"Tool: {truncate_text(step.tool_name, 80)}({_format_for_llm(step.tool_args, max_chars=200)})"
            )
        if step.tool_result:
            append_line(f"Tool result: {_format_for_llm(step.tool_result)}")
        if step.tool_snapshot:
            append_line(
                "Tool snapshot: "
                f"id={step.tool_snapshot.snapshot_id} digest={step.tool_snapshot.result_digest}"
            )
        append_line(f"Input: {truncate_text(step.input_prompt, 600)}")
        append_line(f"Output: {truncate_text(step.output_response, 600)}")
        if step.claims:
            append_line(f"Claims: {_format_for_llm(step.claims)}")
        if step.memory_reads:
            append_line(f"Memory reads: {_format_for_llm(step.memory_reads)}")
        if step.memory_writes:
            append_line(f"Memory writes: {_format_for_llm(step.memory_writes)}")
        if step.environment_snapshot:
            append_line(
                "Environment snapshot: "
                f"id={step.environment_snapshot.snapshot_id} "
                f"model={step.environment_snapshot.model_name or 'n/a'} "
                f"prompt={step.environment_snapshot.prompt_version or 'n/a'}"
            )
        if step.metadata:
            append_line(f"Metadata: {_format_for_llm(step.metadata)}")
        if not append_line(""):
            break
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
