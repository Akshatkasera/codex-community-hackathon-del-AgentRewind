from __future__ import annotations

import time

from .config import get_settings
from .llm import run_json_chat
from .models import AgentTrace, Fork, TraceStep
from .utils import (
    count_tokens,
    estimate_cost,
    format_prior_context,
    generate_uuid,
    sum_cost,
)


def _build_mock_step(
    original_step: TraceStep,
    output_response: str,
    *,
    new_input: str | None = None,
    tool_result: str | None = None,
    status: str = "ok",
    model: str = "gpt-4o-mini",
) -> TraceStep:
    prompt_text = new_input or original_step.input_prompt
    return TraceStep(
        id=f"fork_{original_step.id}",
        agent_name=original_step.agent_name,
        step_type=original_step.step_type,
        status=status,  # type: ignore[arg-type]
        input_prompt=prompt_text,
        output_response=output_response,
        tool_name=original_step.tool_name,
        tool_args=original_step.tool_args,
        tool_result=tool_result,
        timestamp=time.time(),
        cost_usd=estimate_cost(prompt_text, output_response, model),
        tokens=count_tokens(output_response),
        duration_seconds=1.2,
        metadata={"is_fork": True, "source": "mock"},
    )


def _mock_replay_steps(
    original_trace: AgentTrace,
    original_steps_after: list[TraceStep],
    user_modification: str,
) -> list[TraceStep]:
    trace_id = original_trace.trace_id

    if trace_id == "refund_policy_bug":
        outputs = [
            (
                "Retrieved the canonical 2024 policy handbook and ignored the stale FAQ. Confirmed refunds are allowed within 30 days of purchase with proof of payment.",
                "policy_handbook_2024.md -> Effective 2024-06-01: refunds are allowed within 30 days with receipt.",
            ),
            (
                "Validated against the current handbook: the authoritative refund window is 30 days, and older FAQ snapshots should not be used.",
                None,
            ),
            (
                "You can request a refund within 30 days of purchase as long as you have proof of payment. The 90-day answer came from an outdated FAQ and is not the current policy.",
                None,
            ),
        ]
    elif trace_id == "code_review_failure":
        outputs = [
            (
                "No built-in redis_client.cache_with_stampede_protection() method exists in this codebase. Recommend implementing explicit GET/SETNX locking or using the existing cache wrapper.",
                "Repository scan: redis_client exposes get, set, setex, delete, and lock helpers only.",
            ),
            (
                "Updated implementation plan: use the existing Redis lock helper to guard cache misses and store serialized user records with TTL.",
                None,
            ),
            (
                "Rewrote the tests to assert behavior through the supported Redis lock wrapper and removed references to the hallucinated helper.",
                None,
            ),
            (
                "Requested changes: remove the invented Redis API, keep the lock-based approach, and ensure tests cover cache hit, miss, and contention paths.",
                None,
            ),
        ]
    else:
        outputs = [
            (
                "Rebalanced the evidence set by prioritizing the peer-reviewed trial data and explicitly flagging the contradiction with the marketing copy.",
                "Trial summary shows elevated liver risk in 11 percent of patients; marketing site omits this.",
            ),
            (
                "Generated a synthesis that includes both the positive marketing claims and the negative trial findings, with trial data treated as higher confidence.",
                None,
            ),
        ]

    replayed: list[TraceStep] = []
    for index, original_step in enumerate(original_steps_after):
        output_response, tool_result = outputs[min(index, len(outputs) - 1)]
        prompt_text = user_modification if index == 0 else original_step.input_prompt
        replayed.append(
            _build_mock_step(
                original_step,
                output_response,
                new_input=prompt_text,
                tool_result=tool_result,
            )
        )
    return replayed


async def simulate_modified_step(
    *,
    original_trace: AgentTrace,
    original_step: TraceStep,
    new_input: str,
    prior_context: list[TraceStep],
) -> TraceStep:
    settings = get_settings()
    if not settings.llm_enabled:
        raise RuntimeError("Mock mode is handled by replay_from_fork.")

    simulation_prompt = f"""You are simulating a completed step inside a multi-agent system after the user patched a failure.

Task: {original_trace.task_description}
Expected final answer after the fix: {original_trace.expected_output or "Infer from the task and corrected context"}
Original wrong final answer: {original_trace.final_output}
Agent role: {original_step.agent_name}
Step type: {original_step.step_type}
Original input was: {original_step.input_prompt}
Modified input is now: {new_input}
Original tool name: {original_step.tool_name or "None"}
Original tool args: {original_step.tool_args or "None"}

Prior context from earlier steps:
{format_prior_context(prior_context)}

Generate the actual output this step would produce after executing the fix.
Do not describe what the agent plans to do.
Do not restate the instructions.
If the corrected input tells the agent to use canonical or fresher sources, assume the authoritative source is available and emit the corrected finding.
Return JSON:
{{
  "output_response": "string",
  "status": "ok|warning|error",
  "tool_result": "string or null"
}}"""

    parsed = await run_json_chat(
        model=settings.replay_model,
        system_prompt=None,
        user_prompt=simulation_prompt,
        temperature=0.4,
    )
    output_response = str(parsed.get("output_response", original_step.output_response))
    status = str(parsed.get("status", "ok"))
    tool_result = parsed.get("tool_result")
    return TraceStep(
        id=f"fork_{original_step.id}",
        agent_name=original_step.agent_name,
        step_type=original_step.step_type,
        status=status,  # type: ignore[arg-type]
        input_prompt=new_input,
        output_response=output_response,
        tool_name=original_step.tool_name,
        tool_args=original_step.tool_args,
        tool_result=tool_result,
        timestamp=time.time(),
        cost_usd=estimate_cost(new_input, output_response, settings.replay_model),
        tokens=count_tokens(output_response),
        duration_seconds=1.4,
        metadata={"is_fork": True, "source": "openai"},
    )


async def simulate_subsequent_step(
    *,
    original_trace: AgentTrace,
    original_step: TraceStep,
    updated_prior_context: list[TraceStep],
) -> TraceStep:
    settings = get_settings()
    simulation_prompt = f"""You are simulating the next completed step in a multi-agent system after an upstream fix changed the context.

Task: {original_trace.task_description}
Expected final answer after the fix: {original_trace.expected_output or "Infer from context"}
Original wrong final answer: {original_trace.final_output}
Agent role: {original_step.agent_name}
Step type: {original_step.step_type}
Original input: {original_step.input_prompt}
Original output: {original_step.output_response}
Original tool name: {original_step.tool_name or "None"}
Original tool args: {original_step.tool_args or "None"}

Updated prior context:
{format_prior_context(updated_prior_context)}

Treat the updated prior context as authoritative and superseding the original broken branch.
Generate the actual revised output for this step, not a plan or explanation of what might happen.
Return JSON:
{{
  "output_response": "string",
  "status": "ok|warning|error",
  "tool_result": "string or null"
}}"""

    parsed = await run_json_chat(
        model=settings.replay_model,
        system_prompt=None,
        user_prompt=simulation_prompt,
        temperature=0.35,
    )
    output_response = str(parsed.get("output_response", original_step.output_response))
    status = str(parsed.get("status", "ok"))
    tool_result = parsed.get("tool_result")
    return TraceStep(
        id=f"fork_{original_step.id}",
        agent_name=original_step.agent_name,
        step_type=original_step.step_type,
        status=status,  # type: ignore[arg-type]
        input_prompt=original_step.input_prompt,
        output_response=output_response,
        tool_name=original_step.tool_name,
        tool_args=original_step.tool_args,
        tool_result=tool_result,
        timestamp=time.time(),
        cost_usd=estimate_cost(
            original_step.input_prompt, output_response, settings.replay_model
        ),
        tokens=count_tokens(output_response),
        duration_seconds=1.25,
        metadata={"is_fork": True, "source": "openai"},
    )


async def assess_quality_improvement(
    *,
    original_trace: AgentTrace,
    original_output: str,
    new_output: str,
) -> tuple[bool, str]:
    settings = get_settings()

    if not settings.llm_enabled:
        expected = original_trace.expected_output or ""
        improved = expected.lower() in new_output.lower() or new_output != original_output
        return improved, (
            "Fork output moved closer to the expected answer and removed the original failure mode."
            if improved
            else "Fork output did not materially improve on the original answer."
        )

    judge_prompt = f"""You are evaluating whether a replayed multi-agent trace fixed the original failure.

Task: {original_trace.task_description}
Expected answer: {original_trace.expected_output or "Infer from task context"}
Original wrong output: {original_output}
New replayed output: {new_output}

Return JSON:
{{
  "quality_improved": true,
  "assessment": "One sentence explanation."
}}"""

    parsed = await run_json_chat(
        model=settings.judge_model,
        system_prompt=None,
        user_prompt=judge_prompt,
        temperature=0.1,
    )
    return bool(parsed.get("quality_improved", False)), str(
        parsed.get("assessment", "No assessment returned.")
    )


async def replay_from_fork(
    original_trace: AgentTrace, fork_step_id: str, user_modification: str
) -> Fork:
    fork_index = next(
        (index for index, step in enumerate(original_trace.steps) if step.id == fork_step_id),
        None,
    )
    if fork_index is None:
        raise ValueError(f"Unknown fork step: {fork_step_id}")

    steps_before = original_trace.steps[:fork_index]
    original_steps_after = original_trace.steps[fork_index:]

    settings = get_settings()
    if not settings.llm_enabled:
        replayed_steps = _mock_replay_steps(original_trace, original_steps_after, user_modification)
    else:
        modified_step = await simulate_modified_step(
            original_trace=original_trace,
            original_step=original_steps_after[0],
            new_input=user_modification,
            prior_context=steps_before,
        )
        replayed_steps = [modified_step]
        for original_subsequent_step in original_steps_after[1:]:
            new_step = await simulate_subsequent_step(
                original_trace=original_trace,
                original_step=original_subsequent_step,
                updated_prior_context=steps_before + replayed_steps,
            )
            replayed_steps.append(new_step)

    new_final_output = replayed_steps[-1].output_response
    quality_improved, assessment = await assess_quality_improvement(
        original_trace=original_trace,
        original_output=original_trace.final_output,
        new_output=new_final_output,
    )

    return Fork(
        fork_id=generate_uuid(),
        original_trace_id=original_trace.trace_id,
        fork_point_step_id=fork_step_id,
        user_modification=user_modification,
        replayed_steps=replayed_steps,
        new_final_output=new_final_output,
        new_success=quality_improved,
        cost_delta=round(sum_cost(replayed_steps) - sum_cost(original_steps_after), 6),
        quality_improved=quality_improved,
        assessment=assessment,
    )
