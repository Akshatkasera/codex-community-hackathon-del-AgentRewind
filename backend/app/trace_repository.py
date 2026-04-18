from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from uuid import uuid4

from .analysis_engine import enrich_trace
from .cluster_engine import build_failure_clusters
from .config import get_settings
from .models import AgentTrace, FailureCluster, Fork, GeneratedEval, TraceSummary
from .state_store import SQLiteStateStore, state_store


logger = logging.getLogger("agentrewind.repository")


class TraceRepository:
    def __init__(
        self,
        trace_dir: Path,
        imported_trace_dir: Path | None = None,
        persistent_store: SQLiteStateStore | None = None,
    ) -> None:
        self.trace_dir = trace_dir
        self.imported_trace_dir = imported_trace_dir or trace_dir.parent / "imported_traces"
        self.imported_trace_dir.mkdir(parents=True, exist_ok=True)
        self._persistent_store = persistent_store
        self._lock = threading.RLock()
        self._traces: dict[str, AgentTrace] = {}
        self._forks: dict[str, Fork] = {}
        self._evals: dict[str, GeneratedEval] = {}
        self._clusters: list[FailureCluster] = []
        self._trace_watermark = 0.0
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self._traces.clear()
            self._load_trace_directory(self.trace_dir)
            self._load_persisted_imports()
            self._refresh_clusters()

    def _load_trace_directory(self, directory: Path) -> None:
        for path in sorted(directory.glob("*.json")):
            try:
                trace = AgentTrace.model_validate_json(path.read_text(encoding="utf-8"))
                self._traces[trace.trace_id] = enrich_trace(trace)
            except Exception as error:  # noqa: BLE001
                logger.warning("Skipping invalid trace file %s: %s", path.name, error)

    def _load_persisted_imports(self) -> None:
        loaded_trace_ids: set[str] = set()
        if self._persistent_store is not None:
            for trace in self._persistent_store.list_imported_traces():
                loaded_trace_ids.add(trace.trace_id)
                self._traces[trace.trace_id] = enrich_trace(trace)
            self._trace_watermark = self._persistent_store.get_trace_watermark()

        for path in sorted(self.imported_trace_dir.glob("*.json")):
            try:
                trace = AgentTrace.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception as error:  # noqa: BLE001
                logger.warning("Skipping invalid imported trace file %s: %s", path.name, error)
                continue
            if trace.trace_id in loaded_trace_ids:
                continue
            if self._persistent_store is not None:
                self._persistent_store.save_imported_trace(trace)
                self._trace_watermark = self._persistent_store.get_trace_watermark()
            self._traces[trace.trace_id] = enrich_trace(trace)

    def _sync_persisted_imports_if_needed(self) -> None:
        if self._persistent_store is None:
            return
        current_watermark = self._persistent_store.get_trace_watermark()
        if current_watermark <= self._trace_watermark:
            return
        self.reload()

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

    def _write_trace_file(self, path: Path, contents: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
        tmp_path.write_text(contents, encoding="utf-8")
        tmp_path.replace(path)

    def list_traces(self) -> list[TraceSummary]:
        self._sync_persisted_imports_if_needed()
        with self._lock:
            summaries = [
                TraceSummary(
                    trace_id=trace.trace_id,
                    title=trace.title,
                    task_description=trace.task_description,
                    failure_summary=trace.failure_summary,
                    tags=list(trace.tags),
                )
                for trace in self._traces.values()
            ]
            return sorted(
                summaries,
                key=lambda summary: (summary.title.lower(), summary.trace_id.lower()),
            )

    def get_trace(self, trace_id: str) -> AgentTrace | None:
        self._sync_persisted_imports_if_needed()
        with self._lock:
            return self._traces.get(trace_id)

    def list_clusters(self) -> list[FailureCluster]:
        self._sync_persisted_imports_if_needed()
        with self._lock:
            return list(self._clusters)

    def save_imported_trace(self, trace: AgentTrace) -> AgentTrace:
        with self._lock:
            trace_id = self._next_trace_id(trace.trace_id)
            stored_trace = trace.model_copy(
                update={
                    "trace_id": trace_id,
                    "analysis": None,
                }
            )
            target_path = self._storage_path_for_trace(trace_id)
            self._write_trace_file(
                target_path,
                stored_trace.model_dump_json(indent=2),
            )
            if self._persistent_store is not None:
                self._persistent_store.save_imported_trace(stored_trace)
                self._trace_watermark = self._persistent_store.get_trace_watermark()
            enriched = enrich_trace(stored_trace)
            self._traces[enriched.trace_id] = enriched
            self._refresh_clusters()
            return enriched

    def save_fork(self, fork: Fork) -> None:
        with self._lock:
            self._forks[fork.fork_id] = fork
            if self._persistent_store is not None:
                self._persistent_store.save_fork(fork)

    def get_fork(self, fork_id: str) -> Fork | None:
        with self._lock:
            fork = self._forks.get(fork_id)
            if fork is not None:
                return fork
        if self._persistent_store is None:
            return None
        fork = self._persistent_store.get_fork(fork_id)
        if fork is None:
            return None
        with self._lock:
            self._forks[fork_id] = fork
        return fork

    def save_eval(self, generated_eval: GeneratedEval) -> None:
        with self._lock:
            self._evals[generated_eval.eval_id] = generated_eval
            if self._persistent_store is not None:
                self._persistent_store.save_eval(generated_eval)

repository = TraceRepository(
    Path(__file__).resolve().parents[1] / "demo_traces",
    get_settings().imported_trace_dir,
    state_store,
)
