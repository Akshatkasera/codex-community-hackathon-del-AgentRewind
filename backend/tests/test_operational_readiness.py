from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

import main
from app.config import get_settings
from app.jobs import AsyncJobManager
from app.rate_limiter import rate_limiter
from app.state_store import SQLiteStateStore
from main import app


@contextmanager
def override_settings_env(**updates: str):
    original_values = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            os.environ[key] = value
        get_settings.cache_clear()
        main.settings = get_settings()
        rate_limiter.reset()
        yield
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        main.settings = get_settings()
        rate_limiter.reset()


class OperationalReadinessTests(unittest.TestCase):
    def test_sqlite_state_store_round_trips_trace_and_job(self) -> None:
        from app.import_adapters import import_trace_payload

        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStateStore(Path(temp_dir) / "state.sqlite3")
            trace = import_trace_payload(
                payload={
                    "trace_id": "persisted_trace",
                    "title": "Persisted Trace",
                    "task_description": "Persist this trace.",
                    "final_output": "wrong output",
                    "steps": [
                        {
                            "id": "s1",
                            "agent_name": "Planner",
                            "step_type": "llm",
                            "status": "ok",
                            "input_prompt": "Do the thing",
                            "output_response": "wrong output",
                            "timestamp": 1.0,
                        }
                    ],
                },
                framework_hint="agentrewind",
            ).trace
            store.save_imported_trace(trace)

            saved_traces = store.list_imported_traces()
            self.assertEqual(len(saved_traces), 1)
            self.assertEqual(saved_traces[0].trace_id, "persisted_trace")

            from app.models import AsyncJobRecord

            job = AsyncJobRecord(
                job_id="job-1",
                kind="diagnosis",
                status="queued",
                trace_id="persisted_trace",
                created_at=time.time(),
                updated_at=time.time(),
                request_id="req-1",
                result=None,
                error=None,
            )
            store.create_job(job, request_payload={"trace_id": "persisted_trace"})
            store.update_job(job_id="job-1", status="completed", result={"ok": True})
            saved_job = store.get_job("job-1")

            self.assertIsNotNone(saved_job)
            self.assertEqual(saved_job.status, "completed")
            self.assertEqual(saved_job.result, {"ok": True})
            store.close()

    def test_api_requires_auth_token_when_enabled(self) -> None:
        with override_settings_env(AGENTREWIND_AUTH_TOKENS="prod-token"):
            with TestClient(app) as client:
                unauthorized = client.get("/api/traces")
                authorized = client.get(
                    "/api/traces",
                    headers={"Authorization": "Bearer prod-token"},
                )

            self.assertEqual(unauthorized.status_code, 401)
            self.assertEqual(unauthorized.json()["detail"], "Missing or invalid API token.")
            self.assertEqual(authorized.status_code, 200)

    def test_rate_limiter_blocks_excess_requests(self) -> None:
        with override_settings_env(
            AGENTREWIND_RATE_LIMIT_REQUESTS_PER_MINUTE="1",
            AGENTREWIND_RATE_LIMIT_HEAVY_REQUESTS_PER_MINUTE="1",
        ):
            with TestClient(app) as client:
                first = client.get("/api/traces")
                second = client.get("/api/traces")

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 429)
            self.assertEqual(second.headers.get("X-RateLimit-Remaining"), "0")

    def test_async_diagnosis_job_submits_and_is_queryable(self) -> None:
        with override_settings_env(AGENTREWIND_USE_MOCK_LLM="true"):
            with TestClient(app) as client:
                submitted = client.post(
                    "/api/diagnose/jobs",
                    json={"trace_id": "refund_policy_bug"},
                )
                self.assertEqual(submitted.status_code, 202)
                job_id = submitted.json()["job_id"]
                poll = client.get(f"/api/jobs/{job_id}")

            self.assertEqual(poll.status_code, 200)
            self.assertIn(poll.json()["status"], {"queued", "running", "completed"})
            self.assertEqual(poll.json()["kind"], "diagnosis")

    def test_async_job_manager_executes_runner(self) -> None:
        async def scenario():
            manager = AsyncJobManager()
            await manager.start()

            async def runner():
                await asyncio.sleep(0.02)
                return {"ok": True}

            job = await manager.submit(
                kind="diagnosis",
                trace_id="trace-1",
                request_id="request-1",
                request_payload={"trace_id": "trace-1"},
                runner=runner,
            )
            completed_job = manager.get_job(job.job_id)
            for _ in range(40):
                if completed_job is not None and completed_job.status == "completed":
                    break
                await asyncio.sleep(0.02)
                completed_job = manager.get_job(job.job_id)
            await manager.shutdown()
            return completed_job

        completed = asyncio.run(scenario())
        self.assertIsNotNone(completed)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.result, {"ok": True})


if __name__ == "__main__":
    unittest.main()
