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
    for index, step in enumerate(trace.steps, start=1):
        output.append(f"--- STEP {index} (id: {step.id}) ---")
        output.append(f"Agent: {step.agent_name}")
        output.append(f"Type: {step.step_type}")
        output.append(f"Status: {step.status}")
        if step.tool_name:
            output.append(f"Tool: {step.tool_name}({step.tool_args})")
        if step.tool_result:
            output.append(f"Tool result: {step.tool_result}")
        output.append(f"Input: {step.input_prompt}")
        output.append(f"Output: {step.output_response}")
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
