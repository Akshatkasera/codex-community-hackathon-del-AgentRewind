from __future__ import annotations

from .config import get_settings
from .llm import run_json_chat
from .models import AgentTrace, Diagnosis, Fork, GeneratedEval
from .utils import generate_uuid


def _mock_eval(trace: AgentTrace, fork: Fork, diagnosis: Diagnosis) -> GeneratedEval:
    if trace.trace_id == "refund_policy_bug":
        assertions = [
            {"type": "contains", "target": "30 days", "critical": True},
            {"type": "not_contains", "target": "90 days", "critical": True},
            {"type": "source_recency_days", "max_age": 180, "critical": False},
        ]
        trigger_pattern = "Questions about refund eligibility, refund window, or return policy."
    elif trace.trace_id == "code_review_failure":
        assertions = [
            {
                "type": "not_contains",
                "target": "cache_with_stampede_protection",
                "critical": True,
            },
            {"type": "contains", "target": "lock", "critical": False},
            {"type": "contains", "target": "TTL", "critical": False},
        ]
        trigger_pattern = "Requests to add caching around the user lookup code path."
    else:
        assertions = [
            {"type": "contains", "target": "peer-reviewed", "critical": True},
            {"type": "contains", "target": "contradiction", "critical": False},
            {"type": "not_contains", "target": "safe with no caveats", "critical": True},
        ]
        trigger_pattern = "Medical or safety research syntheses with mixed-quality evidence."

    return GeneratedEval(
        eval_id=generate_uuid(),
        trigger_pattern=trigger_pattern,
        assertions=assertions,
        created_from_trace_id=trace.trace_id,
        fix_description=fork.user_modification or diagnosis.suggested_fix,
    )


async def generate_eval_from_fork(
    trace: AgentTrace, fork: Fork, diagnosis: Diagnosis
) -> GeneratedEval:
    settings = get_settings()
    if not settings.llm_enabled:
        return _mock_eval(trace, fork, diagnosis)

    prompt = f"""Convert this debugging session into a regression test.

ORIGINAL FAILURE:
- Task: {trace.task_description}
- Wrong output: {trace.final_output}
- Root cause: {diagnosis.explanation}

FIX APPLIED:
- Modified step: {fork.fork_point_step_id}
- User's edit: {fork.user_modification}
- New correct output: {fork.new_final_output}

Generate a JSON test specification with assertions that would catch this bug if it returns. Include positive assertions and negative assertions. Return JSON:
{{
  "trigger_pattern": "natural language pattern of when this test runs",
  "assertions": [
    {{"type": "contains", "target": "...", "critical": true}},
    {{"type": "not_contains", "target": "...", "critical": true}},
    {{"type": "source_recency_days", "max_age": 180, "critical": false}}
  ]
}}"""

    parsed = await run_json_chat(
        model=settings.primary_model,
        system_prompt=None,
        user_prompt=prompt,
        temperature=0.2,
    )

    return GeneratedEval(
        eval_id=generate_uuid(),
        trigger_pattern=str(parsed.get("trigger_pattern", "Fallback trigger pattern missing.")),
        assertions=list(parsed.get("assertions", [])),
        created_from_trace_id=trace.trace_id,
        fix_description=fork.user_modification,
    )
