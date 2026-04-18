from __future__ import annotations

import re
from pathlib import Path

from .analysis_engine import enrich_trace
from .cluster_engine import build_failure_clusters
from .models import AgentTrace, FailureCluster, Fork, GeneratedEval, TraceSummary


class TraceRepository:
    def __init__(self, trace_dir: Path, imported_trace_dir: Path | None = None) -> None:
        self.trace_dir = trace_dir
        self.imported_trace_dir = imported_trace_dir or trace_dir.parent / "imported_traces"
        self.imported_trace_dir.mkdir(parents=True, exist_ok=True)
        self._traces: dict[str, AgentTrace] = {}
        self._forks: dict[str, Fork] = {}
        self._evals: dict[str, GeneratedEval] = {}
        self._clusters: list[FailureCluster] = []
        self.reload()

    def reload(self) -> None:
        self._traces.clear()
        for path in self._iter_trace_paths():
            trace = AgentTrace.model_validate_json(path.read_text(encoding="utf-8"))
            trace = enrich_trace(trace)
            self._traces[trace.trace_id] = trace
        self._refresh_clusters()

    def _iter_trace_paths(self) -> list[Path]:
        demo_paths = sorted(self.trace_dir.glob("*.json"))
        imported_paths = sorted(self.imported_trace_dir.glob("*.json"))
        return [*demo_paths, *imported_paths]

    def _refresh_clusters(self) -> None:
        self._clusters, trace_membership = build_failure_clusters(list(self._traces.values()))
        for trace_id, clusters in trace_membership.items():
            trace = self._traces.get(trace_id)
            if trace is None or trace.analysis is None:
                continue
            trace.analysis.cluster_ids = [cluster.cluster_id for cluster in clusters]
            trace.analysis.cluster_labels = [cluster.label for cluster in clusters]

    def _next_trace_id(self, desired_trace_id: str) -> str:
        candidate = desired_trace_id
        suffix = 2
        while candidate in self._traces:
            candidate = f"{desired_trace_id}_{suffix}"
            suffix += 1
        return candidate

    def _storage_path_for_trace(self, trace_id: str) -> Path:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", trace_id).strip("_") or "imported_trace"
        return self.imported_trace_dir / f"{safe_name}.json"

    def list_traces(self) -> list[TraceSummary]:
        return [
            TraceSummary(
                trace_id=trace.trace_id,
                title=trace.title,
                task_description=trace.task_description,
                failure_summary=trace.failure_summary,
                tags=trace.tags,
            )
            for trace in self._traces.values()
        ]

    def get_trace(self, trace_id: str) -> AgentTrace | None:
        return self._traces.get(trace_id)

    def list_clusters(self) -> list[FailureCluster]:
        return self._clusters

    def save_imported_trace(self, trace: AgentTrace) -> AgentTrace:
        trace_id = self._next_trace_id(trace.trace_id)
        stored_trace = trace.model_copy(
            update={
                "trace_id": trace_id,
                "analysis": None,
            }
        )
        target_path = self._storage_path_for_trace(trace_id)
        target_path.write_text(
            stored_trace.model_dump_json(indent=2),
            encoding="utf-8",
        )
        enriched = enrich_trace(stored_trace)
        self._traces[enriched.trace_id] = enriched
        self._refresh_clusters()
        return enriched

    def save_fork(self, fork: Fork) -> None:
        self._forks[fork.fork_id] = fork

    def get_fork(self, fork_id: str) -> Fork | None:
        return self._forks.get(fork_id)

    def save_eval(self, generated_eval: GeneratedEval) -> None:
        self._evals[generated_eval.eval_id] = generated_eval

repository = TraceRepository(
    Path(__file__).resolve().parents[1] / "demo_traces",
    Path(__file__).resolve().parents[1] / "imported_traces",
)
