from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .config import get_settings
from .models import AgentTrace, AsyncJobRecord, Fork, GeneratedEval


class SQLiteStateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA busy_timeout=5000")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS imported_traces (
                    trace_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS forks (
                    fork_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evals (
                    eval_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trace_id TEXT,
                    request_id TEXT,
                    request_payload TEXT,
                    result_payload TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_imported_traces_updated_at
                ON imported_traces(updated_at);

                CREATE INDEX IF NOT EXISTS idx_forks_trace_id
                ON forks(trace_id);

                CREATE INDEX IF NOT EXISTS idx_evals_trace_id
                ON evals(trace_id);

                CREATE INDEX IF NOT EXISTS idx_jobs_status_updated_at
                ON jobs(status, updated_at);
                """
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def get_trace_watermark(self) -> float:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(updated_at), 0) AS watermark FROM imported_traces"
            ).fetchone()
        return float(row["watermark"] or 0.0)

    def save_imported_trace(self, trace: AgentTrace) -> None:
        now = time.time()
        payload = trace.model_dump_json()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO imported_traces(trace_id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (trace.trace_id, payload, now, now),
            )
            self._connection.commit()

    def list_imported_traces(self) -> list[AgentTrace]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM imported_traces ORDER BY updated_at ASC, trace_id ASC"
            ).fetchall()
        return [AgentTrace.model_validate_json(row["payload"]) for row in rows]

    def save_fork(self, fork: Fork) -> None:
        now = time.time()
        payload = fork.model_dump_json()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO forks(fork_id, trace_id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(fork_id) DO UPDATE SET
                    trace_id = excluded.trace_id,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (fork.fork_id, fork.original_trace_id, payload, now, now),
            )
            self._connection.commit()

    def get_fork(self, fork_id: str) -> Fork | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM forks WHERE fork_id = ?",
                (fork_id,),
            ).fetchone()
        if row is None:
            return None
        return Fork.model_validate_json(row["payload"])

    def save_eval(self, generated_eval: GeneratedEval) -> None:
        now = time.time()
        payload = generated_eval.model_dump_json()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO evals(eval_id, trace_id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(eval_id) DO UPDATE SET
                    trace_id = excluded.trace_id,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    generated_eval.eval_id,
                    generated_eval.created_from_trace_id,
                    payload,
                    now,
                    now,
                ),
            )
            self._connection.commit()

    def create_job(
        self,
        job: AsyncJobRecord,
        *,
        request_payload: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO jobs(
                    job_id, kind, status, trace_id, request_id,
                    request_payload, result_payload, error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.kind,
                    job.status,
                    job.trace_id,
                    job.request_id,
                    json.dumps(request_payload, ensure_ascii=True) if request_payload else None,
                    json.dumps(job.result, ensure_ascii=True) if job.result is not None else None,
                    job.error,
                    job.created_at,
                    job.updated_at,
                ),
            )
            self._connection.commit()

    def get_job(self, job_id: str) -> AsyncJobRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT job_id, kind, status, trace_id, request_id, result_payload, error, created_at, updated_at
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        result = json.loads(row["result_payload"]) if row["result_payload"] else None
        return AsyncJobRecord(
            job_id=row["job_id"],
            kind=row["kind"],
            status=row["status"],
            trace_id=row["trace_id"],
            request_id=row["request_id"],
            result=result,
            error=row["error"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def update_job(
        self,
        *,
        job_id: str,
        status: str,
        result: Any | None = None,
        error: str | None = None,
    ) -> AsyncJobRecord | None:
        now = time.time()
        serialized_result = (
            json.dumps(result, ensure_ascii=True, default=str)
            if result is not None
            else None
        )
        with self._lock:
            self._connection.execute(
                """
                UPDATE jobs
                SET status = ?, result_payload = ?, error = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, serialized_result, error, now, job_id),
            )
            self._connection.commit()
        return self.get_job(job_id)

    def mark_incomplete_jobs_failed(self, error: str) -> None:
        now = time.time()
        with self._lock:
            self._connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', error = ?, updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (error, now),
            )
            self._connection.commit()

    def cleanup_expired_jobs(self, retention_seconds: int) -> None:
        cutoff = time.time() - retention_seconds
        with self._lock:
            self._connection.execute(
                """
                DELETE FROM jobs
                WHERE status IN ('completed', 'failed')
                  AND updated_at < ?
                """,
                (cutoff,),
            )
            self._connection.commit()


state_store = SQLiteStateStore(get_settings().state_db_path)
