from __future__ import annotations

from pathlib import Path

from .models import AgentTrace, Fork, GeneratedEval, TraceSummary


class TraceRepository:
    def __init__(self, trace_dir: Path) -> None:
        self.trace_dir = trace_dir
        self._traces: dict[str, AgentTrace] = {}
        self._forks: dict[str, Fork] = {}
        self._evals: dict[str, GeneratedEval] = {}
        self.reload()

    def reload(self) -> None:
        self._traces.clear()
        for path in sorted(self.trace_dir.glob("*.json")):
            trace = AgentTrace.model_validate_json(path.read_text(encoding="utf-8"))
            self._traces[trace.trace_id] = trace

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

    def save_fork(self, fork: Fork) -> None:
        self._forks[fork.fork_id] = fork

    def get_fork(self, fork_id: str) -> Fork | None:
        return self._forks.get(fork_id)

    def save_eval(self, generated_eval: GeneratedEval) -> None:
        self._evals[generated_eval.eval_id] = generated_eval


repository = TraceRepository(Path(__file__).resolve().parents[1] / "demo_traces")
