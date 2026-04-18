from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any

from .models import (
    AgentTrace,
    ContradictionFinding,
    EnvironmentSnapshot,
    MemoryCorruptionIssue,
    ProvenanceLink,
    RepairSuggestion,
    ToolSnapshot,
    TraceAnalysis,
    TraceStep,
    UncertaintySignal,
    VersionedArtifact,
)
from .utils import generate_uuid


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "with",
}
POSITIVE_TERMS = {
    "safe",
    "positive",
    "eligible",
    "approved",
    "supported",
    "available",
    "tolerated",
    "favorable",
}
NEGATIVE_TERMS = {
    "unsafe",
    "negative",
    "ineligible",
    "rejected",
    "unsupported",
    "risk",
    "halted",
    "hepatotoxicity",
    "crash",
    "stale",
    "not",
    "no",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _normalize_claim(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9%\s=_-]", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _tokenize_claim(text: str) -> set[str]:
    return {
        token
        for token in _normalize_claim(text).split()
        if token and token not in STOPWORDS
    }


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    raw_segments = re.split(r"[\n\r]+|(?<=[.!?])\s+", str(text))
    sentences = []
    for segment in raw_segments:
        cleaned = segment.strip(" -")
        if len(cleaned) >= 12:
            sentences.append(cleaned)
    return sentences


def _extract_claims(step: TraceStep) -> list[str]:
    source_text = "\n".join(
        [
            step.output_response or "",
            str(step.tool_result) if step.tool_result else "",
        ]
    )
    return _split_sentences(source_text)[:5]


def _polarity(claim: str) -> str | None:
    tokens = _tokenize_claim(claim)
    positive = bool(tokens & POSITIVE_TERMS)
    negative = bool(tokens & NEGATIVE_TERMS)
    if positive and not negative:
        return "positive"
    if negative and not positive:
        return "negative"
    return None


def _extract_numeric_markers(claim: str) -> list[str]:
    return re.findall(
        r"\b\d+(?:\.\d+)?(?:\s*(?:day|days|month|months|year|years|percent|%|hours?))?\b",
        claim.lower(),
    )


def _claim_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize_claim(left)
    right_tokens = _tokenize_claim(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(intersection) / len(union)


def _same_topic(left: str, right: str) -> bool:
    similarity = _claim_similarity(left, right)
    shared_tokens = _tokenize_claim(left) & _tokenize_claim(right)
    return similarity >= 0.22 or len(shared_tokens) >= 3


def _memory_key_label(memory_key: str) -> str:
    return memory_key.split("=", 1)[0].strip().lower()


def _build_snapshot(step: TraceStep) -> ToolSnapshot | None:
    if not step.tool_name:
        return None
    normalized_args: dict[str, Any] | str | None
    if isinstance(step.tool_args, dict):
        normalized_args = json.loads(_canonical_json(step.tool_args))
    else:
        normalized_args = step.tool_args
    snapshot_payload = {
        "tool_name": step.tool_name,
        "normalized_args": normalized_args,
        "tool_result": step.tool_result,
        "output_response": step.output_response,
    }
    snapshot_text = _canonical_json(snapshot_payload)
    return ToolSnapshot(
        snapshot_id=f"snapshot_{step.id}",
        tool_name=step.tool_name,
        captured_at=step.timestamp,
        normalized_args=normalized_args,
        result=step.tool_result,
        result_digest=_digest_text(snapshot_text),
        deterministic_replay=True,
    )


def _infer_environment_snapshot(trace: AgentTrace, step: TraceStep) -> EnvironmentSnapshot:
    if step.environment_snapshot is not None:
        return step.environment_snapshot

    metadata = trace.metadata.get("environment_profile", {})
    model_name = step.metadata.get("model_name")
    if not model_name and step.step_type != "tool":
        model_name = metadata.get("default_model", "gpt-4o-mini")

    prompt_version = step.metadata.get(
        "prompt_version", f"{step.agent_name.lower().replace(' ', '_')}-v1"
    )
    tool_versions: list[VersionedArtifact] = []
    if step.tool_name:
        tool_versions.append(
            VersionedArtifact(
                artifact_id=f"artifact_{step.id}_{step.tool_name}",
                artifact_type="tool",
                name=step.tool_name,
                version=str(step.metadata.get("tool_version", "demo-v1")),
                digest=_digest_text(
                    _canonical_json(
                        {
                            "tool_name": step.tool_name,
                            "tool_args": step.tool_args,
                            "tool_result": step.tool_result,
                        }
                    )
                ),
                source="trace_metadata",
            )
        )
    if model_name:
        tool_versions.append(
            VersionedArtifact(
                artifact_id=f"artifact_{step.id}_model",
                artifact_type="model",
                name=model_name,
                version=str(step.metadata.get("model_version", model_name)),
                digest=_digest_text(model_name),
                source="trace_metadata",
            )
        )
    return EnvironmentSnapshot(
        snapshot_id=f"env_{step.id}",
        step_id=step.id,
        captured_at=step.timestamp,
        model_name=model_name,
        prompt_version=prompt_version,
        tool_versions=tool_versions,
        memory_digest=(
            _digest_text("|".join(sorted(step.memory_reads + step.memory_writes)))
            if step.memory_reads or step.memory_writes
            else None
        ),
        config_flags={
            "lane": step.metadata.get("lane"),
            "source_quality": step.metadata.get("source_quality"),
            "source_age_days": step.metadata.get("source_age_days"),
        },
        auth_scope=str(step.metadata.get("auth_scope", metadata.get("auth_scope", "demo-readonly"))),
        clock_version=str(step.metadata.get("clock_version", int(step.timestamp))),
    )


def _find_contradictions(steps: list[TraceStep]) -> list[ContradictionFinding]:
    findings: list[ContradictionFinding] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for left_index, left_step in enumerate(steps):
        for right_step in steps[left_index + 1 :]:
            if left_step.id == right_step.id:
                continue
            for left_claim in left_step.claims:
                for right_claim in right_step.claims:
                    if not _same_topic(left_claim, right_claim):
                        continue

                    numeric_left = _extract_numeric_markers(left_claim)
                    numeric_right = _extract_numeric_markers(right_claim)
                    polarity_left = _polarity(left_claim)
                    polarity_right = _polarity(right_claim)

                    conflict_type: str | None = None
                    summary: str | None = None
                    severity = 1

                    if numeric_left and numeric_right and numeric_left != numeric_right:
                        conflict_type = "numeric_mismatch"
                        summary = (
                            f"{left_step.agent_name} and {right_step.agent_name} disagree on the concrete value."
                        )
                        severity = 3
                    elif polarity_left and polarity_right and polarity_left != polarity_right:
                        conflict_type = "polarity_conflict"
                        summary = (
                            f"{left_step.agent_name} and {right_step.agent_name} present opposite conclusions."
                        )
                        severity = 2

                    if conflict_type is None or summary is None:
                        continue

                    key = tuple(sorted((left_step.id, right_step.id)) + [conflict_type])
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)

                    findings.append(
                        ContradictionFinding(
                            finding_id=generate_uuid(),
                            left_step_id=left_step.id,
                            right_step_id=right_step.id,
                            conflict_type=conflict_type,
                            summary=summary,
                            severity=severity,
                            left_claim=left_claim,
                            right_claim=right_claim,
                        )
                    )
    return findings


def _build_provenance_links(steps: list[TraceStep]) -> list[ProvenanceLink]:
    links: list[ProvenanceLink] = []
    for consumer_index, consumer_step in enumerate(steps):
        if consumer_index == 0:
            continue
        prior_steps = steps[:consumer_index]

        for memory_key in consumer_step.memory_reads:
            for producer_step in reversed(prior_steps):
                producer_memory_labels = {
                    _memory_key_label(value) for value in producer_step.memory_writes
                }
                if _memory_key_label(memory_key) in producer_memory_labels:
                    links.append(
                        ProvenanceLink(
                            link_id=generate_uuid(),
                            claim=memory_key,
                            producer_step_id=producer_step.id,
                            consumer_step_id=consumer_step.id,
                            provenance_kind="direct_handoff",
                            evidence=f"Consumer explicitly read memory key '{memory_key}'.",
                        )
                    )
                    break

        for claim in consumer_step.claims:
            best_match: tuple[TraceStep, str, float] | None = None
            for producer_step in prior_steps:
                for producer_claim in producer_step.claims:
                    similarity = _claim_similarity(claim, producer_claim)
                    if similarity < 0.36 and producer_claim not in claim and claim not in producer_claim:
                        continue
                    if best_match is None or similarity > best_match[2]:
                        best_match = (producer_step, producer_claim, similarity)

            if best_match is None:
                continue

            producer_step, producer_claim, similarity = best_match
            if producer_step.id == consumer_step.id:
                continue

            provenance_kind = (
                "tool_snapshot" if producer_step.tool_snapshot else "memory_carryover"
            )
            links.append(
                ProvenanceLink(
                    link_id=generate_uuid(),
                    claim=claim,
                    producer_step_id=producer_step.id,
                    consumer_step_id=consumer_step.id,
                    provenance_kind=provenance_kind,
                    evidence=f"Matched to '{producer_claim}' with similarity {similarity:.2f}.",
                )
            )
    return links


def _root_memory_sources(
    links: list[ProvenanceLink], final_step_id: str, first_step_id: str
) -> list[str]:
    producers_by_consumer: dict[str, list[str]] = defaultdict(list)
    for link in links:
        producers_by_consumer[link.consumer_step_id].append(link.producer_step_id)

    roots: set[str] = set()
    frontier = [final_step_id]
    visited: set[str] = set()
    while frontier:
        consumer = frontier.pop()
        if consumer in visited:
            continue
        visited.add(consumer)
        producers = producers_by_consumer.get(consumer, [])
        if not producers:
            roots.add(consumer)
            continue
        for producer in producers:
            if producer == first_step_id:
                roots.add(producer)
            else:
                frontier.append(producer)
    return sorted(roots)


def _build_memory_issues(
    trace: AgentTrace,
    steps: list[TraceStep],
    provenance_links: list[ProvenanceLink],
    contradiction_findings: list[ContradictionFinding],
) -> list[MemoryCorruptionIssue]:
    contradiction_step_ids = {
        finding.left_step_id for finding in contradiction_findings
    } | {finding.right_step_id for finding in contradiction_findings}

    direct_links_by_key: dict[str, list[ProvenanceLink]] = defaultdict(list)
    for link in provenance_links:
        if link.provenance_kind == "direct_handoff":
            direct_links_by_key[_memory_key_label(link.claim)].append(link)

    issues: list[MemoryCorruptionIssue] = []
    recurrence_index: dict[str, int] = defaultdict(int)
    for step in steps:
        suspicious_writer = (
            step.status != "ok"
            or step.id in contradiction_step_ids
            or bool(step.metadata.get("invented_api"))
            or bool(step.metadata.get("canonical_source_missed"))
            or bool(step.metadata.get("ignored_contradiction"))
            or (step.metadata.get("source_age_days") or 0) >= 180
        )
        if not suspicious_writer:
            continue

        for memory_key in step.memory_writes:
            impacted = [
                link.consumer_step_id
                for link in direct_links_by_key.get(_memory_key_label(memory_key), [])
                if link.producer_step_id == step.id
            ]
            reaches_final_step = bool(steps and steps[-1].id in impacted)
            persistent = len(set(impacted)) >= 2 or reaches_final_step
            recurrence_index[_memory_key_label(memory_key)] += 1
            if not impacted:
                continue

            summary = (
                f"{step.agent_name} wrote '{memory_key}' into memory and later steps reused it "
                f"after the writer had already shown signs of failure."
            )
            if reaches_final_step:
                summary += " The corrupted value reached the final answer."

            issues.append(
                MemoryCorruptionIssue(
                    issue_id=generate_uuid(),
                    memory_key=memory_key,
                    writer_step_id=step.id,
                    impacted_step_ids=sorted(set(impacted)),
                    summary=summary,
                    severity=3 if reaches_final_step else 2,
                    persistent=persistent,
                    recurrence_count=1,
                )
            )

    for issue in issues:
        issue.recurrence_count = recurrence_index[_memory_key_label(issue.memory_key)]

    return issues


def _uncertainty_level(score: float) -> str:
    if score < 0.3:
        return "low"
    if score < 0.55:
        return "medium"
    if score < 0.78:
        return "high"
    return "critical"


def _build_uncertainty_signals(
    steps: list[TraceStep],
    contradiction_findings: list[ContradictionFinding],
    provenance_links: list[ProvenanceLink],
    memory_issues: list[MemoryCorruptionIssue],
) -> tuple[list[UncertaintySignal], bool, str | None]:
    contradiction_step_ids = {
        finding.left_step_id for finding in contradiction_findings
    } | {finding.right_step_id for finding in contradiction_findings}
    suspicious_memory_steps = {issue.writer_step_id for issue in memory_issues}
    for issue in memory_issues:
        suspicious_memory_steps.update(issue.impacted_step_ids)

    parents_by_step: dict[str, set[str]] = defaultdict(set)
    for current, step in enumerate(steps):
        if current > 0:
            parents_by_step[step.id].add(steps[current - 1].id)
    for link in provenance_links:
        parents_by_step[link.consumer_step_id].add(link.producer_step_id)

    signals: list[UncertaintySignal] = []
    score_by_step: dict[str, float] = {}
    for step in steps:
        reasons: list[str] = []
        base = {"ok": 0.16, "warning": 0.42, "error": 0.68}[step.status]

        if step.id in contradiction_step_ids:
            base += 0.18
            reasons.append("contradictory evidence touched this step")
        if step.id in suspicious_memory_steps:
            base += 0.15
            reasons.append("memory may be contaminated upstream")
        if step.metadata.get("source_quality") == "low":
            base += 0.14
            reasons.append("source quality is low")
        if (step.metadata.get("source_age_days") or 0) >= 180:
            base += 0.16
            reasons.append("source is stale")
        if step.metadata.get("invented_api"):
            base += 0.24
            reasons.append("step references an unsupported interface")
        if step.metadata.get("ignored_contradiction"):
            base += 0.22
            reasons.append("step flattened conflicting evidence")
        if step.metadata.get("missed_contract_check"):
            base += 0.1
            reasons.append("contract validation was skipped")

        propagated_from = sorted(parents_by_step.get(step.id, set()))
        inherited = 0.0
        if propagated_from:
            inherited = max(score_by_step.get(parent, 0.0) * 0.72 for parent in propagated_from)
            if inherited >= 0.25:
                reasons.append("uncertainty propagated from upstream context")
        score = round(min(0.99, max(base, inherited)), 2)
        level = _uncertainty_level(score)
        should_abstain = step.id == steps[-1].id and (
            score >= 0.74 or len(contradiction_findings) > 0
        )
        suggested_response = None
        if should_abstain:
            suggested_response = (
                "Current evidence is not stable enough for a confident answer. "
                "Surface the conflict, request fresher verification, or abstain."
            )
            reasons.append("final answer should abstain or explicitly hedge")

        signals.append(
            UncertaintySignal(
                step_id=step.id,
                score=score,
                level=level,  # type: ignore[arg-type]
                reasons=reasons or ["no strong uncertainty indicators"],
                propagated_from_step_ids=propagated_from,
                should_abstain=should_abstain,
                suggested_response=suggested_response,
            )
        )
        score_by_step[step.id] = score

    final_signal = signals[-1] if signals else None
    abstention_recommended = bool(final_signal and final_signal.should_abstain)
    abstention_reason = final_signal.suggested_response if final_signal else None
    return signals, abstention_recommended, abstention_reason


def _build_repair_suggestions(
    trace: AgentTrace,
    steps: list[TraceStep],
    contradiction_findings: list[ContradictionFinding],
    memory_issues: list[MemoryCorruptionIssue],
    uncertainty_signals: list[UncertaintySignal],
) -> list[RepairSuggestion]:
    suggestions: list[RepairSuggestion] = []
    seen_titles: set[str] = set()

    def add_suggestion(
        *,
        title: str,
        summary: str,
        target_scope: str,
        patch_hint: str,
        target_step_id: str | None = None,
        confidence: int = 80,
        auto_applicable: bool = False,
    ) -> None:
        if title in seen_titles:
            return
        seen_titles.add(title)
        suggestions.append(
            RepairSuggestion(
                suggestion_id=generate_uuid(),
                title=title,
                summary=summary,
                target_scope=target_scope,  # type: ignore[arg-type]
                target_step_id=target_step_id,
                patch_hint=patch_hint,
                confidence=confidence,
                auto_applicable=auto_applicable,
            )
        )

    failure_category = str(trace.metadata.get("failure_category", "")).lower()
    stale_step = next(
        (
            step
            for step in steps
            if (step.metadata.get("source_age_days") or 0) >= 180
            or step.metadata.get("canonical_source_missed")
        ),
        None,
    )
    if stale_step is not None or failure_category == "stale_data":
        add_suggestion(
            title="Add Canonical Source Gate",
            summary="Force retrieval to rank authoritative sources ahead of stale or archived content.",
            target_scope="retrieval_policy",
            target_step_id=stale_step.id if stale_step else None,
            patch_hint=(
                "Before accepting a source, check freshness and prefer the canonical handbook or "
                "repository contract over FAQs, archives, or marketing pages."
            ),
            confidence=91,
            auto_applicable=True,
        )

    hallucinated_step = next(
        (step for step in steps if step.metadata.get("invented_api")),
        None,
    )
    if hallucinated_step is not None or failure_category == "hallucination":
        add_suggestion(
            title="Verify Tool Contracts Before Use",
            summary="Make the agent inspect the actual interface before coding against it.",
            target_scope="tool_contract",
            target_step_id=hallucinated_step.id if hallucinated_step else None,
            patch_hint=(
                "Require a repository or schema scan step and reject any API name that was not "
                "observed in the codebase or official spec."
            ),
            confidence=94,
            auto_applicable=True,
        )

    if contradiction_findings:
        add_suggestion(
            title="Escalate Contradictions Instead of Flattening Them",
            summary="When two source classes disagree, preserve the disagreement and rank source quality explicitly.",
            target_scope="workflow",
            patch_hint=(
                "Add a contradiction checkpoint that compares claims, annotates source quality, "
                "and blocks optimistic synthesis until the conflict is surfaced."
            ),
            confidence=89,
        )

    if memory_issues:
        issue = memory_issues[0]
        add_suggestion(
            title="Quarantine Corrupted Memory Keys",
            summary="Prevent suspicious memory writes from silently poisoning later steps.",
            target_scope="memory_guard",
            target_step_id=issue.writer_step_id,
            patch_hint=(
                f"Invalidate '{issue.memory_key}' when the writer is stale, contradictory, or warning-level, "
                "and require a clean re-derivation before later agents may read it."
            ),
            confidence=88,
        )

    final_signal = uncertainty_signals[-1] if uncertainty_signals else None
    if final_signal and final_signal.should_abstain:
        add_suggestion(
            title="Add Abstention Thresholds",
            summary="Do not force a confident answer when uncertainty remains high at the final step.",
            target_scope="abstain_policy",
            target_step_id=final_signal.step_id,
            patch_hint=(
                "If unresolved contradictions or high uncertainty survive to the final stage, "
                "switch to a hedged response that asks for verification or states the disagreement."
            ),
            confidence=86,
        )

    if not suggestions:
        add_suggestion(
            title="Tighten Prompt Guardrails",
            summary="The trace does not expose a single dominant failure, so start by constraining the failing prompt.",
            target_scope="prompt",
            patch_hint=(
                "Ask the agent to state assumptions, cite evidence, and refuse to invent missing facts or tools."
            ),
            confidence=70,
        )

    return suggestions


def enrich_trace(trace: AgentTrace) -> AgentTrace:
    enriched = deepcopy(trace)
    for step in enriched.steps:
        if not step.claims:
            step.claims = _extract_claims(step)
        if not step.memory_writes:
            step.memory_writes = step.claims[:3]
        if step.tool_snapshot is None and step.tool_name:
            step.tool_snapshot = _build_snapshot(step)
        step.environment_snapshot = _infer_environment_snapshot(enriched, step)

    contradiction_findings = _find_contradictions(enriched.steps)
    provenance_links = _build_provenance_links(enriched.steps)
    memory_issues = _build_memory_issues(
        enriched, enriched.steps, provenance_links, contradiction_findings
    )
    uncertainty_signals, abstention_recommended, abstention_reason = _build_uncertainty_signals(
        enriched.steps,
        contradiction_findings,
        provenance_links,
        memory_issues,
    )
    repair_suggestions = _build_repair_suggestions(
        enriched,
        enriched.steps,
        contradiction_findings,
        memory_issues,
        uncertainty_signals,
    )
    deterministic_steps = [
        step.id
        for step in enriched.steps
        if step.tool_snapshot is not None and step.tool_snapshot.deterministic_replay
    ]
    contradictory_step_ids = sorted(
        {finding.left_step_id for finding in contradiction_findings}
        | {finding.right_step_id for finding in contradiction_findings}
    )
    root_sources = _root_memory_sources(
        provenance_links,
        final_step_id=enriched.steps[-1].id,
        first_step_id=enriched.steps[0].id,
    )
    replay_coverage = (
        round(len(deterministic_steps) / len(enriched.steps), 2) if enriched.steps else 0.0
    )
    environment_coverage = (
        round(
            len([step for step in enriched.steps if step.environment_snapshot is not None])
            / len(enriched.steps),
            2,
        )
        if enriched.steps
        else 0.0
    )
    final_uncertainty = uncertainty_signals[-1].score if uncertainty_signals else 0.0
    summary_parts = [
        f"{len(deterministic_steps)} deterministic tool snapshots",
        f"{len(contradiction_findings)} contradiction findings",
        f"{len(provenance_links)} provenance links",
        f"{len(memory_issues)} persistent memory issues",
        f"final uncertainty {final_uncertainty:.2f}",
    ]
    enriched.analysis = TraceAnalysis(
        deterministic_replay_step_ids=deterministic_steps,
        deterministic_replay_coverage=replay_coverage,
        contradiction_findings=contradiction_findings,
        provenance_links=provenance_links,
        repair_suggestions=repair_suggestions,
        memory_corruption_issues=memory_issues,
        uncertainty_signals=uncertainty_signals,
        contradictory_step_ids=contradictory_step_ids,
        root_memory_source_step_ids=root_sources,
        environment_coverage=environment_coverage,
        final_uncertainty=final_uncertainty,
        abstention_recommended=abstention_recommended,
        abstention_reason=abstention_reason,
        summary=", ".join(summary_parts),
    )
    return enriched
