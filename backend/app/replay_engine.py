from __future__ import annotations

import time

from .analysis_engine import enrich_trace
from .config import get_settings
from .llm import run_json_chat
from .models import (
    AgentTrace,
    ContradictionFinding,
    Fork,
    MemoryCorruptionIssue,
    ProvenanceLink,
    RepairSuggestion,
    ReplayAudit,
    TraceAnalysis,
    TraceStep,
    UncertaintySignal,
)
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
        claims=[],
        memory_reads=list(original_step.memory_reads),
        memory_writes=[],
        tool_snapshot=original_step.tool_snapshot,
        environment_snapshot=original_step.environment_snapshot,
        metadata={"is_fork": True, "source": "mock", "replay_mode": "simulated"},
    )


def _mock_replay_steps(
    original_trace: AgentTrace,
    original_steps_after: list[TraceStep],
    user_modification: str,
    *,
    model: str,
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
                model=model,
            )
        )
    return replayed


def _replay_step_from_snapshot(
    original_step: TraceStep,
    *,
    new_input: str | None = None,
) -> TraceStep:
    prompt_text = new_input or original_step.input_prompt
    return TraceStep(
        id=f"fork_{original_step.id}",
        agent_name=original_step.agent_name,
        step_type=original_step.step_type,
        status=original_step.status,
        input_prompt=prompt_text,
        output_response=original_step.output_response,
        tool_name=original_step.tool_name,
        tool_args=original_step.tool_args,
        tool_result=(
            original_step.tool_snapshot.result
            if original_step.tool_snapshot is not None
            else original_step.tool_result
        ),
        timestamp=time.time(),
        cost_usd=0.0,
        tokens=count_tokens(original_step.output_response),
        duration_seconds=0.05,
        claims=list(original_step.claims),
        memory_reads=list(original_step.memory_reads),
        memory_writes=list(original_step.memory_writes),
        tool_snapshot=original_step.tool_snapshot,
        environment_snapshot=original_step.environment_snapshot,
        metadata={
            **original_step.metadata,
            "is_fork": True,
            "source": "deterministic_snapshot",
            "replay_mode": "deterministic_snapshot",
        },
    )


async def simulate_modified_step(
    *,
    original_trace: AgentTrace,
    original_step: TraceStep,
    new_input: str,
    prior_context: list[TraceStep],
    replay_model: str,
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
        model=replay_model,
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
        cost_usd=estimate_cost(new_input, output_response, replay_model),
        tokens=count_tokens(output_response),
        duration_seconds=1.4,
        claims=[],
        memory_reads=list(original_step.memory_reads),
        memory_writes=[],
        environment_snapshot=original_step.environment_snapshot,
        metadata={
            "is_fork": True,
            "source": "openai",
            "replay_mode": "simulated",
            "selected_model": replay_model,
        },
    )


async def simulate_subsequent_step(
    *,
    original_trace: AgentTrace,
    original_step: TraceStep,
    updated_prior_context: list[TraceStep],
    replay_model: str,
) -> TraceStep:
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
        model=replay_model,
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
        cost_usd=estimate_cost(original_step.input_prompt, output_response, replay_model),
        tokens=count_tokens(output_response),
        duration_seconds=1.25,
        claims=[],
        memory_reads=list(original_step.memory_reads),
        memory_writes=[],
        environment_snapshot=original_step.environment_snapshot,
        metadata={
            "is_fork": True,
            "source": "openai",
            "replay_mode": "simulated",
            "selected_model": replay_model,
        },
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


def _fork_analysis(
    *,
    original_trace: AgentTrace,
    steps_before: list[TraceStep],
    replayed_steps: list[TraceStep],
) -> tuple[list[TraceStep], TraceAnalysis | None]:
    fork_trace = enrich_trace(
        AgentTrace(
            trace_id=f"{original_trace.trace_id}_fork_preview",
            title=f"{original_trace.title} Fork Preview",
            task_description=original_trace.task_description,
            expected_output=original_trace.expected_output,
            final_output=replayed_steps[-1].output_response,
            steps=steps_before + replayed_steps,
            failure_summary=original_trace.failure_summary,
            tags=original_trace.tags,
            metadata=original_trace.metadata,
        )
    )
    enriched_replayed_steps = fork_trace.steps[len(steps_before) :]
    return enriched_replayed_steps, fork_trace.analysis


def _environment_mismatch(step: TraceStep, replay_model: str) -> str | None:
    snapshot = step.environment_snapshot
    if snapshot is None:
        return f"{step.id}:missing_environment_snapshot"
    if step.step_type != "tool" and snapshot.model_name and snapshot.model_name != replay_model:
        return f"{step.id}:model_version_mismatch({snapshot.model_name}->{replay_model})"
    if not snapshot.prompt_version:
        return f"{step.id}:missing_prompt_version"
    if step.tool_name and not snapshot.tool_versions:
        return f"{step.id}:missing_tool_version"
    return None


def _build_replay_audit(
    *,
    original_steps_after: list[TraceStep],
    replayed_steps: list[TraceStep],
    deterministic_replay_step_ids: list[str],
    settings_replay_model: str,
) -> ReplayAudit:
    snapshot_ids_by_step = {
        step.id: step.environment_snapshot.snapshot_id
        for step in original_steps_after
        if step.environment_snapshot is not None
    }
    reused_snapshot_ids = [
        snapshot_ids_by_step[step_id]
        for step_id in deterministic_replay_step_ids
        if step_id in snapshot_ids_by_step
    ]
    mismatches = [
        mismatch
        for step in original_steps_after
        for mismatch in [_environment_mismatch(step, settings_replay_model)]
        if mismatch is not None
    ]
    missing_artifacts = [
        step.id
        for step in original_steps_after
        if step.environment_snapshot is None
        or (step.tool_name and not step.environment_snapshot.tool_versions)
    ]
    simulated_step_ids = [step.id for step in replayed_steps if step.metadata.get("source") != "deterministic_snapshot"]
    coverage = (
        round(
            len([step for step in replayed_steps if step.environment_snapshot is not None])
            / len(replayed_steps),
            2,
        )
        if replayed_steps
        else 0.0
    )
    notes = [
        "Replay reuses deterministic tool snapshots where the captured environment is complete.",
        "Steps without a compatible environment snapshot fall back to simulation.",
    ]
    return ReplayAudit(
        environment_snapshot_id=reused_snapshot_ids[0] if reused_snapshot_ids else None,
        snapshot_coverage=coverage,
        deterministic_step_ids=deterministic_replay_step_ids,
        simulated_step_ids=simulated_step_ids,
        version_mismatch_step_ids=mismatches,
        missing_artifacts=missing_artifacts,
        reused_snapshot_ids=reused_snapshot_ids,
        notes=notes,
    )


async def replay_from_fork(
    original_trace: AgentTrace,
    fork_step_id: str,
    user_modification: str,
    replay_model_override: str | None = None,
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
    selected_replay_model = settings.resolve_model(
        replay_model_override, fallback=settings.replay_model
    )
    deterministic_replay_step_ids: list[str] = []
    snapshot_miss_step_ids: list[str] = []
    if not settings.llm_enabled:
        replayed_steps = _mock_replay_steps(
            original_trace,
            original_steps_after,
            user_modification,
            model=selected_replay_model,
        )
    else:
        fork_step = original_steps_after[0]
        if (
            fork_step.tool_snapshot is not None
            and fork_step.environment_snapshot is not None
            and user_modification.strip() == fork_step.input_prompt.strip()
        ):
            modified_step = _replay_step_from_snapshot(fork_step, new_input=user_modification)
            deterministic_replay_step_ids.append(fork_step.id)
        else:
            if fork_step.tool_snapshot is not None:
                snapshot_miss_step_ids.append(fork_step.id)
            modified_step = await simulate_modified_step(
                original_trace=original_trace,
                original_step=fork_step,
                new_input=user_modification,
                prior_context=steps_before,
                replay_model=selected_replay_model,
            )
        replayed_steps = [modified_step]
        for original_subsequent_step in original_steps_after[1:]:
            if (
                original_subsequent_step.tool_snapshot is not None
                and original_subsequent_step.environment_snapshot is not None
            ):
                new_step = _replay_step_from_snapshot(original_subsequent_step)
                deterministic_replay_step_ids.append(original_subsequent_step.id)
            else:
                if original_subsequent_step.tool_snapshot is not None:
                    snapshot_miss_step_ids.append(original_subsequent_step.id)
                new_step = await simulate_subsequent_step(
                    original_trace=original_trace,
                    original_step=original_subsequent_step,
                    updated_prior_context=steps_before + replayed_steps,
                    replay_model=selected_replay_model,
                )
            replayed_steps.append(new_step)

    new_final_output = replayed_steps[-1].output_response
    quality_improved, assessment = await assess_quality_improvement(
        original_trace=original_trace,
        original_output=original_trace.final_output,
        new_output=new_final_output,
    )
    replayed_steps, fork_analysis = _fork_analysis(
        original_trace=original_trace,
        steps_before=steps_before,
        replayed_steps=replayed_steps,
    )
    remaining_contradictions = (
        [
            finding
            for finding in (fork_analysis.contradiction_findings if fork_analysis else [])
            if finding.left_step_id.startswith("fork_") or finding.right_step_id.startswith("fork_")
        ]
        if fork_analysis
        else []
    )
    provenance_links = (
        [
            link
            for link in (fork_analysis.provenance_links if fork_analysis else [])
            if link.consumer_step_id.startswith("fork_") or link.producer_step_id.startswith("fork_")
        ]
        if fork_analysis
        else []
    )
    memory_corruption_issues: list[MemoryCorruptionIssue] = (
        [
            issue
            for issue in (fork_analysis.memory_corruption_issues if fork_analysis else [])
            if issue.writer_step_id.startswith("fork_")
            or any(step_id.startswith("fork_") for step_id in issue.impacted_step_ids)
        ]
        if fork_analysis
        else []
    )
    uncertainty_signals: list[UncertaintySignal] = (
        [
            signal
            for signal in (fork_analysis.uncertainty_signals if fork_analysis else [])
            if signal.step_id.startswith("fork_")
        ]
        if fork_analysis
        else []
    )
    repair_suggestions: list[RepairSuggestion] = list(fork_analysis.repair_suggestions) if fork_analysis else []
    replay_audit = _build_replay_audit(
        original_steps_after=original_steps_after,
        replayed_steps=replayed_steps,
        deterministic_replay_step_ids=deterministic_replay_step_ids,
        settings_replay_model=selected_replay_model,
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
        deterministic_replay_step_ids=deterministic_replay_step_ids,
        snapshot_miss_step_ids=snapshot_miss_step_ids,
        remaining_contradictions=remaining_contradictions,
        provenance_links=provenance_links,
        repair_suggestions=repair_suggestions,
        memory_corruption_issues=memory_corruption_issues,
        uncertainty_signals=uncertainty_signals,
        abstention_recommended=bool(fork_analysis and fork_analysis.abstention_recommended),
        abstention_reason=fork_analysis.abstention_reason if fork_analysis else None,
        replay_audit=replay_audit,
    )
