from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from .config import get_settings
from .models import AsyncJobKind, AsyncJobRecord
from .state_store import state_store
from .utils import generate_uuid


logger = logging.getLogger("agentrewind.jobs")

JobRunner = Callable[[], Awaitable[Any]]


@dataclass
class _QueuedJob:
    job: AsyncJobRecord
    request_payload: dict[str, Any]
    runner: JobRunner


class AsyncJobManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[_QueuedJob] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._started = False
        self._worker_loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        current_loop = asyncio.get_running_loop()
        if (
            self._started
            and self._worker_loop is current_loop
            and any(not worker.done() for worker in self._workers)
        ):
            return
        if self._worker_loop is not None and self._worker_loop is not current_loop:
            self._workers.clear()
            self._started = False
            self._worker_loop = None
        settings = get_settings()
        state_store.mark_incomplete_jobs_failed(
            "Job interrupted because the server restarted before completion."
        )
        state_store.cleanup_expired_jobs(settings.job_retention_seconds)
        self._workers = [
            asyncio.create_task(self._worker(index + 1))
            for index in range(settings.job_worker_concurrency)
        ]
        self._started = True
        self._worker_loop = current_loop

    async def shutdown(self) -> None:
        if not self._started:
            return
        current_loop = asyncio.get_running_loop()
        if self._worker_loop is not current_loop:
            self._workers.clear()
            self._started = False
            self._worker_loop = None
            return
        workers = list(self._workers)
        self._workers.clear()
        self._started = False
        self._worker_loop = None
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    async def submit(
        self,
        *,
        kind: AsyncJobKind,
        trace_id: str | None,
        request_id: str | None,
        request_payload: dict[str, Any],
        runner: JobRunner,
    ) -> AsyncJobRecord:
        if not self._started:
            await self.start()
        now = time.time()
        job = AsyncJobRecord(
            job_id=generate_uuid(),
            kind=kind,
            status="queued",
            trace_id=trace_id,
            created_at=now,
            updated_at=now,
            request_id=request_id,
            result=None,
            error=None,
        )
        state_store.create_job(job, request_payload=request_payload)
        await self._queue.put(
            _QueuedJob(
                job=job,
                request_payload=request_payload,
                runner=runner,
            )
        )
        return job

    def get_job(self, job_id: str) -> AsyncJobRecord | None:
        return state_store.get_job(job_id)

    async def _worker(self, worker_index: int) -> None:
        while True:
            queued_job = await self._queue.get()
            try:
                state_store.update_job(
                    job_id=queued_job.job.job_id,
                    status="running",
                )
                result = await queued_job.runner()
                serialized_result = self._serialize_result(result)
                state_store.update_job(
                    job_id=queued_job.job.job_id,
                    status="completed",
                    result=serialized_result,
                    error=None,
                )
                logger.info(
                    "Completed async job=%s kind=%s worker=%s",
                    queued_job.job.job_id,
                    queued_job.job.kind,
                    worker_index,
                )
            except asyncio.CancelledError:
                state_store.update_job(
                    job_id=queued_job.job.job_id,
                    status="failed",
                    error="Job cancelled while shutting down the server.",
                )
                raise
            except Exception as error:  # noqa: BLE001
                logger.exception(
                    "Async job failed job=%s kind=%s worker=%s",
                    queued_job.job.job_id,
                    queued_job.job.kind,
                    worker_index,
                    exc_info=error,
                )
                state_store.update_job(
                    job_id=queued_job.job.job_id,
                    status="failed",
                    error=str(error) or "Job failed unexpectedly.",
                )
            finally:
                self._queue.task_done()

    def _serialize_result(self, result: Any) -> Any:
        if isinstance(result, BaseModel):
            return result.model_dump(mode="json")
        return result


job_manager = AsyncJobManager()
