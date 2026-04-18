from __future__ import annotations

from .config import get_settings
from .llm import run_json_chat
from .models import AgentTrace, Diagnosis
from .utils import format_trace_for_llm


DIAGNOSIS_SYSTEM_PROMPT = """You are an expert multi-agent AI system debugger with deep knowledge of how LLM-based agents fail.

Your job: analyze a failed agent trace and identify the exact step where things went wrong, explain why in plain English, and suggest a specific fix.

Common failure modes to consider:
1. CONTEXT_DRIFT: Information lost during agent handoffs
2. HALLUCINATION: Agent invented information not in the source
3. STALE_DATA: Tool returned outdated information that was treated as current
4. TOOL_ERROR: Tool was called with wrong arguments or returned bad data
5. PROMPT_AMBIGUITY: Instructions were vague, agent guessed wrong
6. CONSENSUS_HALLUCINATION: Multiple agents agreed on something fabricated
7. MEMORY_PROVENANCE: A bad fact entered memory earlier and was repeated downstream
8. CONTRADICTION_SUPPRESSION: Agents observed conflicting evidence but failed to surface it

Return JSON with this exact schema:
{
  "root_cause_step_id": "s2",
  "confidence": 94,
  "blame_agent": "KnowledgeRetriever",
  "failure_category": "stale_data",
  "explanation": "Plain English explanation, 2-3 sentences max",
  "suggested_fix": "Specific actionable fix the user can apply",
  "fix_target": "tool_args"
}"""


def _mock_diagnosis(trace: AgentTrace, suspected_step_id: str | None = None) -> Diagnosis:
    step_id = suspected_step_id or trace.metadata.get("root_cause_step_id") or trace.steps[0].id
    blame_agent = trace.metadata.get("blame_agent") or next(
        step.agent_name for step in trace.steps if step.id == step_id
    )
    return Diagnosis(
        root_cause_step_id=step_id,
        confidence=int(trace.metadata.get("confidence", 92)),
        blame_agent=blame_agent,
        failure_category=str(trace.metadata.get("failure_category", "tool_error")),
        explanation=str(
            trace.metadata.get(
                "diagnosis_explanation",
                "The system anchored on the wrong intermediate evidence and every downstream step treated it as true.",
            )
        ),
        suggested_fix=str(
            trace.metadata.get(
                "suggested_fix",
                "Rewrite the failing step so it uses the canonical source and carries the corrected fact forward.",
            )
        ),
        fix_target=str(trace.metadata.get("fix_target", "tool_args")),
    )


async def diagnose_failure(
    trace: AgentTrace, suspected_step_id: str | None = None
) -> Diagnosis:
    settings = get_settings()
    if not settings.llm_enabled:
        return _mock_diagnosis(trace, suspected_step_id)

    trace_context = format_trace_for_llm(trace)
    user_prompt = f"""TASK: {trace.task_description}

EXPECTED OUTPUT: {trace.expected_output or "Not provided - infer from context"}

ACTUAL OUTPUT (WRONG): {trace.final_output}

FULL TRACE:
{trace_context}

TRACE ANALYSIS SUMMARY: {trace.analysis.summary if trace.analysis else "No precomputed analysis available"}
PRECOMPUTED REPAIRS: {[suggestion.title for suggestion in trace.analysis.repair_suggestions] if trace.analysis else []}
ABSTENTION SIGNAL: {trace.analysis.abstention_reason if trace.analysis and trace.analysis.abstention_recommended else "Not required"}

Suspected step id: {suspected_step_id or "Not provided - infer it"}

Identify the root cause step. Be specific and confident."""

    parsed = await run_json_chat(
        model=settings.primary_model,
        system_prompt=DIAGNOSIS_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
    )

    return Diagnosis(
        root_cause_step_id=str(
            parsed.get("root_cause_step_id")
            or suspected_step_id
            or trace.metadata.get("root_cause_step_id")
            or trace.steps[0].id
        ),
        confidence=max(1, min(100, int(parsed.get("confidence", 85)))),
        blame_agent=str(parsed.get("blame_agent") or trace.metadata.get("blame_agent") or "Unknown"),
        failure_category=str(
            parsed.get("failure_category")
            or trace.metadata.get("failure_category")
            or "tool_error"
        ).lower(),
        explanation=str(parsed.get("explanation") or trace.metadata.get("diagnosis_explanation")),
        suggested_fix=str(parsed.get("suggested_fix") or trace.metadata.get("suggested_fix")),
        fix_target=str(parsed.get("fix_target") or trace.metadata.get("fix_target") or "tool_args"),
    )
