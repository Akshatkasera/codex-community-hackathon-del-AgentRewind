from __future__ import annotations

from collections import defaultdict

from .models import AgentTrace, FailureCluster
from .utils import generate_uuid


CLUSTER_LABELS = {
    "evidence_integrity": "Evidence Integrity Failures",
    "interface_hallucination": "Interface Hallucinations",
    "memory_contamination": "Memory Contamination",
    "overconfidence": "Unsafe Overconfidence",
    "misc": "Mixed Failure Modes",
}


def _trace_signals(trace: AgentTrace) -> list[str]:
    signals: set[str] = set()
    category = str(trace.metadata.get("failure_category", "")).lower()
    analysis = trace.analysis

    if category in {"stale_data", "consensus_hallucination"}:
        signals.add("evidence_integrity")
    if analysis and analysis.contradiction_findings:
        signals.add("evidence_integrity")
    if any(
        (step.metadata.get("source_age_days") or 0) >= 180
        or step.metadata.get("canonical_source_missed")
        for step in trace.steps
    ):
        signals.add("evidence_integrity")

    if category == "hallucination" or any(step.metadata.get("invented_api") for step in trace.steps):
        signals.add("interface_hallucination")

    if analysis and analysis.memory_corruption_issues:
        signals.add("memory_contamination")

    if analysis and analysis.abstention_recommended:
        signals.add("overconfidence")

    if not signals:
        signals.add("misc")
    return sorted(signals)


def _primary_cluster_key(signals: list[str]) -> str:
    priority = [
        "evidence_integrity",
        "interface_hallucination",
        "memory_contamination",
        "overconfidence",
        "misc",
    ]
    for key in priority:
        if key in signals:
            return key
    return "misc"


def build_failure_clusters(traces: list[AgentTrace]) -> tuple[list[FailureCluster], dict[str, list[FailureCluster]]]:
    traces_by_cluster: dict[str, list[AgentTrace]] = defaultdict(list)
    signals_by_trace: dict[str, list[str]] = {}
    for trace in traces:
        signals = _trace_signals(trace)
        signals_by_trace[trace.trace_id] = signals
        traces_by_cluster[_primary_cluster_key(signals)].append(trace)

    clusters: list[FailureCluster] = []
    trace_membership: dict[str, list[FailureCluster]] = defaultdict(list)
    for cluster_key, cluster_traces in traces_by_cluster.items():
        if not cluster_traces:
            continue
        failure_categories = sorted(
            {str(trace.metadata.get("failure_category", "unknown")) for trace in cluster_traces}
        )
        shared_signals = sorted({signal for trace in cluster_traces for signal in signals_by_trace[trace.trace_id]})
        recommended_scopes = sorted(
            {
                suggestion.target_scope
                for trace in cluster_traces
                if trace.analysis
                for suggestion in trace.analysis.repair_suggestions
            }
        )
        recurring_memory_keys = sorted(
            {
                issue.memory_key
                for trace in cluster_traces
                if trace.analysis
                for issue in trace.analysis.memory_corruption_issues
                if issue.persistent
            }
        )
        cluster = FailureCluster(
            cluster_id=generate_uuid(),
            label=CLUSTER_LABELS.get(cluster_key, CLUSTER_LABELS["misc"]),
            summary=(
                f"{len(cluster_traces)} traces share the {cluster_key.replace('_', ' ')} pattern. "
                "Use this cluster to fix repeated failures once instead of chasing them one by one."
            ),
            trace_ids=[trace.trace_id for trace in cluster_traces],
            shared_signals=shared_signals,
            failure_categories=failure_categories,
            recommended_scopes=recommended_scopes,
            recurring_memory_keys=recurring_memory_keys,
        )
        clusters.append(cluster)
        for trace in cluster_traces:
            trace_membership[trace.trace_id].append(cluster)

    clusters.sort(key=lambda cluster: (-len(cluster.trace_ids), cluster.label))
    return clusters, trace_membership
