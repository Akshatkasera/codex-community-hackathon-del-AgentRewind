from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.config import get_settings
from app.import_adapters import import_trace_payload
from app.trace_repository import TraceRepository
from app.utils import format_trace_for_llm
from main import app


def _native_trace_payload(*, text: str = "output", step_id: str = "s1") -> dict[str, object]:
    return {
        "trace_id": "native_trace",
        "title": "Native Trace",
        "task_description": "Test a native import payload.",
        "final_output": text,
        "steps": [
            {
                "id": step_id,
                "agent_name": "Planner",
                "step_type": "llm",
                "status": "ok",
                "input_prompt": "Do the thing",
                "output_response": text,
                "timestamp": 1.0,
            }
        ],
    }


class ProductionHardeningTests(unittest.TestCase):
    def test_import_normalizes_duplicate_step_ids_and_trims_large_text(self) -> None:
        settings = get_settings()
        oversized_text = "x" * (settings.import_max_text_chars + 500)
        payload = _native_trace_payload(text=oversized_text, step_id="dup")
        payload["steps"] = [payload["steps"][0], dict(payload["steps"][0])]

        imported = import_trace_payload(payload=payload, framework_hint="agentrewind")

        self.assertEqual(
            [step.id for step in imported.trace.steps],
            ["dup", "dup_2"],
        )
        self.assertLessEqual(
            len(imported.trace.steps[0].output_response),
            settings.import_max_text_chars,
        )

    def test_repository_reload_skips_invalid_trace_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            demo_dir = root / "demo_traces"
            imported_dir = root / "imported_traces"
            demo_dir.mkdir()
            imported_dir.mkdir()

            (demo_dir / "good.json").write_text(
                import_trace_payload(
                    payload=_native_trace_payload(),
                    framework_hint="agentrewind",
                ).trace.model_dump_json(indent=2),
                encoding="utf-8",
            )
            (imported_dir / "bad.json").write_text("{not valid json", encoding="utf-8")

            repository = TraceRepository(demo_dir, imported_dir)

            traces = repository.list_traces()
            self.assertEqual(len(traces), 1)
            self.assertEqual(traces[0].trace_id, "native_trace")

    def test_import_endpoint_rejects_payloads_over_body_limit(self) -> None:
        settings = get_settings()
        client = TestClient(app)
        huge_payload = {
            "framework_hint": "generic",
            "payload": {"messages": ["x" * (settings.import_max_payload_bytes + 256)]},
        }

        response = client.post("/api/imports", json=huge_payload)

        self.assertEqual(response.status_code, 413)
        self.assertIn("maximum supported size", response.json()["detail"])
        self.assertTrue(response.headers.get("X-Request-ID"))

    def test_trace_formatter_obeys_context_budget(self) -> None:
        settings = get_settings()
        long_trace = import_trace_payload(
            payload={
                "trace_id": "long_trace",
                "title": "Long Trace",
                "task_description": "A" * (settings.import_max_text_chars + 100),
                "final_output": "B" * (settings.import_max_text_chars + 100),
                "steps": [
                    {
                        "id": f"s{index}",
                        "agent_name": f"Agent{index}",
                        "step_type": "llm",
                        "status": "ok",
                        "input_prompt": "P" * 4_000,
                        "output_response": "O" * 4_000,
                        "timestamp": float(index),
                        "metadata": {"blob": "M" * 4_000},
                    }
                    for index in range(1, 32)
                ],
            },
            framework_hint="agentrewind",
        ).trace

        formatted = format_trace_for_llm(long_trace)

        self.assertLessEqual(len(formatted), settings.llm_max_trace_chars + 64)
        self.assertIn("[trace truncated", formatted)


if __name__ == "__main__":
    unittest.main()
