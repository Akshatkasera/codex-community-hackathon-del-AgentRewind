from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import get_settings
from .models import AgentTrace, ImportFramework, ImportedTraceResult, TraceStep
from .utils import count_tokens, generate_uuid


SUPPORTED_IMPORT_FRAMEWORKS: tuple[ImportFramework, ...] = (
    "agentrewind",
    "langgraph",
    "crewai",
    "autogen",
    "openai_agents",
    "generic",
)


@dataclass
class AdapterOutcome:
    framework: ImportFramework
    trace: AgentTrace
    notes: list[str]


def import_trace_payload(
    *,
    payload: Any,
    framework_hint: ImportFramework = "auto",
    source_name: str | None = None,
    title_override: str | None = None,
    task_description_override: str | None = None,
) -> ImportedTraceResult:
    parsed_payload = _coerce_payload(payload)
    framework = detect_framework(parsed_payload, framework_hint)

    adapter = {
        "agentrewind": _adapt_agentrewind,
        "langgraph": _adapt_langgraph,
        "crewai": _adapt_crewai,
        "autogen": _adapt_autogen,
        "openai_agents": _adapt_openai_agents,
        "generic": _adapt_generic,
    }[framework]

    try:
        outcome = adapter(parsed_payload)
    except ValueError:
        if framework_hint != "auto" or framework == "generic":
            raise
        outcome = _adapt_generic(parsed_payload)
        framework = "generic"

    trace = _finalize_trace(
        outcome.trace,
        framework=framework,
        source_name=source_name,
        title_override=title_override,
        task_description_override=task_description_override,
    )
    trace, sanitization_notes = _sanitize_trace(trace)
    notes = list(
        dict.fromkeys(
            outcome.notes
            + sanitization_notes
            + [f"Imported via {framework} adapter."]
        )
    )
    return ImportedTraceResult(
        framework_detected=framework,
        adapter_notes=notes,
        trace=trace,
    )


def detect_framework(payload: Any, framework_hint: ImportFramework = "auto") -> ImportFramework:
    if framework_hint != "auto":
        return framework_hint

    if isinstance(payload, dict):
        declared = _normalize_framework_name(
            _first_non_empty(
                payload.get("framework"),
                payload.get("source_framework"),
                payload.get("framework_name"),
            )
        )
        if declared is not None:
            return declared

        if "trace_id" in payload and isinstance(payload.get("steps"), list):
            return "agentrewind"
        if _looks_like_crewai(payload):
            return "crewai"
        if _looks_like_langgraph(payload):
            return "langgraph"
        if _looks_like_openai_agents(payload):
            return "openai_agents"
        if _looks_like_autogen(payload):
            return "autogen"
        return "generic"

    if isinstance(payload, list):
        if any(isinstance(item, dict) and ("node" in item or "graph_id" in item) for item in payload):
            return "langgraph"
        if any(isinstance(item, dict) and ("source" in item or "speaker" in item) for item in payload):
            return "autogen"
        if any(isinstance(item, dict) and ("span_type" in item or "agent_name" in item) for item in payload):
            return "openai_agents"
        return "generic"

    return "generic"


def _normalize_framework_name(value: Any) -> ImportFramework | None:
    if not value:
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "agentrewind": "agentrewind",
        "langgraph": "langgraph",
        "crewai": "crewai",
        "crew_ai": "crewai",
        "autogen": "autogen",
        "microsoft_autogen": "autogen",
        "openai_agents": "openai_agents",
        "openai_agents_sdk": "openai_agents",
        "openai_agents_runner": "openai_agents",
        "generic": "generic",
    }
    framework = aliases.get(normalized)
    if framework is None:
        return None
    return framework  # type: ignore[return-value]


def _looks_like_langgraph(payload: dict[str, Any]) -> bool:
    events = _ensure_list(payload.get("events") or payload.get("trace") or payload.get("steps"))
    if any(
        isinstance(event, dict)
        and (
            "node" in event
            or "graph_id" in event
            or "state" in event
            or "superstep" in event
        )
        for event in events
    ):
        return True
    return any(key in payload for key in ("graph", "graph_name", "graph_id", "nodes"))


def _looks_like_crewai(payload: dict[str, Any]) -> bool:
    if "crew_name" in payload or "crew" in payload:
        return True
    tasks = _ensure_list(payload.get("tasks") or payload.get("task_runs"))
    return any(
        isinstance(task, dict)
        and (
            "agent" in task
            or "expected_output" in task
            or "tools_used" in task
        )
        for task in tasks
    )


def _looks_like_autogen(payload: dict[str, Any]) -> bool:
    if any(key in payload for key in ("autogen_version", "chat_history", "conversation")):
        return True
    messages = _ensure_list(payload.get("messages"))
    return any(
        isinstance(message, dict)
        and (
            "source" in message
            or "speaker" in message
            or "tool_calls" in message
        )
        for message in messages
    )


def _looks_like_openai_agents(payload: dict[str, Any]) -> bool:
    if any(key in payload for key in ("workflow_name", "run_id", "session_id")):
        items = _ensure_list(payload.get("items") or payload.get("trace") or payload.get("events"))
        if items:
            return True
    items = _ensure_list(payload.get("items") or payload.get("trace"))
    return any(
        isinstance(item, dict)
        and (
            "span_type" in item
            or item.get("type") in {"message", "reasoning", "tool_call", "tool_result"}
            or "agent_name" in item
        )
        for item in items
    )


def _coerce_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise ValueError("Import payload is empty.")
        max_payload_bytes = get_settings().import_max_payload_bytes
        if len(text.encode("utf-8")) > max_payload_bytes:
            raise ValueError(
                f"Import payload exceeds the {max_payload_bytes:,}-byte limit."
            )
        return json.loads(text)
    return payload


def _adapt_agentrewind(payload: Any) -> AdapterOutcome:
    if not isinstance(payload, dict):
        raise ValueError("AgentRewind imports require an object payload.")
    trace = AgentTrace.model_validate(payload)
    return AdapterOutcome(
        framework="agentrewind",
        trace=trace,
        notes=["Payload already matched the native AgentRewind trace schema."],
    )


def _adapt_langgraph(payload: Any) -> AdapterOutcome:
    if not isinstance(payload, dict):
        raise ValueError("LangGraph imports require an object payload.")

    raw_events = _ensure_list(
        payload.get("events")
        or payload.get("steps")
        or payload.get("trace")
        or payload.get("runs")
    )
    if not raw_events:
        raise ValueError("No LangGraph events were found.")

    steps: list[TraceStep] = []
    for index, raw_event in enumerate(raw_events, start=1):
        if not isinstance(raw_event, dict):
            continue
        state = raw_event.get("state") if isinstance(raw_event.get("state"), dict) else {}
        tool_name = _extract_tool_name(raw_event)
        input_prompt = _textify(
            _first_non_empty(
                raw_event.get("input"),
                raw_event.get("prompt"),
                raw_event.get("messages_in"),
                raw_event.get("request"),
                state.get("input") if isinstance(state, dict) else None,
            )
        )
        output_response = _textify(
            _first_non_empty(
                raw_event.get("output"),
                raw_event.get("result"),
                raw_event.get("messages_out"),
                raw_event.get("response"),
                raw_event.get("value"),
                state.get("output") if isinstance(state, dict) else None,
            )
        )
        if not (input_prompt or output_response or tool_name):
            continue

        memory_reads = _normalize_memory_entries(
            _first_non_empty(
                raw_event.get("memory_reads"),
                raw_event.get("state_reads"),
                raw_event.get("read_keys"),
                raw_event.get("state_before"),
            )
        )
        memory_writes = _normalize_memory_entries(
            _first_non_empty(
                raw_event.get("memory_writes"),
                raw_event.get("state_writes"),
                raw_event.get("write_keys"),
                raw_event.get("state_after"),
            )
        )
        metadata = _extract_common_metadata(raw_event, framework="langgraph")
        if isinstance(state, dict):
            metadata["state_keys"] = sorted(state.keys())
        steps.append(
            _build_step(
                raw=raw_event,
                index=index,
                framework="langgraph",
                agent_name=_first_non_empty(
                    raw_event.get("node"),
                    raw_event.get("name"),
                    raw_event.get("agent"),
                    raw_event.get("actor"),
                    f"LangGraphNode{index}",
                ),
                input_prompt=input_prompt,
                output_response=output_response,
                tool_name=tool_name,
                tool_args=_extract_tool_args(raw_event),
                tool_result=_extract_tool_result(raw_event),
                memory_reads=memory_reads,
                memory_writes=memory_writes,
                metadata=metadata,
            )
        )

    if not steps:
        raise ValueError("LangGraph payload did not contain importable node events.")

    trace = AgentTrace(
        trace_id=_infer_trace_id(payload, prefix="langgraph"),
        title=str(
            _first_non_empty(
                payload.get("title"),
                payload.get("graph_name"),
                payload.get("name"),
                "Imported LangGraph Trace",
            )
        ),
        task_description=_textify(
            _first_non_empty(
                payload.get("task_description"),
                payload.get("task"),
                payload.get("input"),
                payload.get("graph_description"),
                "Imported LangGraph run",
            )
        ),
        expected_output=_optional_text(payload.get("expected_output") or payload.get("goal")),
        final_output=_infer_final_output(payload, steps),
        steps=steps,
        failure_summary=_optional_text(payload.get("failure_summary") or payload.get("error")),
        tags=["imported", "langgraph"],
        metadata=_trace_metadata(payload, framework="langgraph"),
    )
    return AdapterOutcome(
        framework="langgraph",
        trace=trace,
        notes=[
            "Mapped LangGraph node events into AgentRewind steps.",
            "State reads and writes were normalized into memory signals when present.",
        ],
    )


def _adapt_crewai(payload: Any) -> AdapterOutcome:
    if not isinstance(payload, dict):
        raise ValueError("CrewAI imports require an object payload.")

    raw_tasks = _ensure_list(payload.get("tasks") or payload.get("task_runs") or payload.get("steps"))
    if not raw_tasks:
        raise ValueError("No CrewAI tasks were found.")

    steps: list[TraceStep] = []
    for index, raw_task in enumerate(raw_tasks, start=1):
        if not isinstance(raw_task, dict):
            continue
        tools_used = _ensure_list(
            raw_task.get("tools_used")
            or raw_task.get("tool_calls")
            or raw_task.get("tools")
        )
        primary_tool = None
        if tools_used:
            first_tool = tools_used[0]
            if isinstance(first_tool, dict):
                primary_tool = _first_non_empty(
                    first_tool.get("name"),
                    first_tool.get("tool_name"),
                    first_tool.get("tool"),
                )
            else:
                primary_tool = str(first_tool)

        input_prompt = _textify(
            _first_non_empty(
                raw_task.get("description"),
                raw_task.get("prompt"),
                raw_task.get("task"),
                raw_task.get("expected_output"),
            )
        )
        output_response = _textify(
            _first_non_empty(
                raw_task.get("output"),
                raw_task.get("result"),
                raw_task.get("summary"),
                raw_task.get("final_answer"),
            )
        )
        if not (input_prompt or output_response or primary_tool):
            continue

        metadata = _extract_common_metadata(raw_task, framework="crewai")
        if len(tools_used) > 1:
            metadata["tool_calls"] = tools_used

        steps.append(
            _build_step(
                raw=raw_task,
                index=index,
                framework="crewai",
                agent_name=_first_non_empty(
                    raw_task.get("agent"),
                    raw_task.get("agent_name"),
                    raw_task.get("owner"),
                    f"CrewTask{index}",
                ),
                input_prompt=input_prompt,
                output_response=output_response,
                tool_name=primary_tool,
                tool_args=_extract_tool_args(raw_task),
                tool_result=_extract_tool_result(raw_task),
                memory_reads=_normalize_memory_entries(raw_task.get("context")),
                memory_writes=_normalize_memory_entries(raw_task.get("memory_writes")),
                metadata=metadata,
            )
        )

    if not steps:
        raise ValueError("CrewAI payload did not contain importable tasks.")

    trace = AgentTrace(
        trace_id=_infer_trace_id(payload, prefix="crewai"),
        title=str(
            _first_non_empty(
                payload.get("title"),
                payload.get("crew_name"),
                payload.get("name"),
                "Imported CrewAI Trace",
            )
        ),
        task_description=_textify(
            _first_non_empty(
                payload.get("task_description"),
                payload.get("goal"),
                payload.get("input"),
                "Imported CrewAI run",
            )
        ),
        expected_output=_optional_text(
            _first_non_empty(
                payload.get("expected_output"),
                raw_tasks[-1].get("expected_output") if isinstance(raw_tasks[-1], dict) else None,
            )
        ),
        final_output=_infer_final_output(payload, steps),
        steps=steps,
        failure_summary=_optional_text(payload.get("failure_summary")),
        tags=["imported", "crewai"],
        metadata=_trace_metadata(payload, framework="crewai"),
    )
    return AdapterOutcome(
        framework="crewai",
        trace=trace,
        notes=[
            "Mapped CrewAI task executions into sequential debugger steps.",
            "Tool usage was preserved when task-level tool metadata was available.",
        ],
    )


def _adapt_autogen(payload: Any) -> AdapterOutcome:
    raw_messages = _ensure_list(
        payload.get("messages") if isinstance(payload, dict) else payload
    )
    if isinstance(payload, dict) and not raw_messages:
        raw_messages = _ensure_list(payload.get("chat_history") or payload.get("conversation"))
    if not raw_messages:
        raise ValueError("No AutoGen-style messages were found.")

    steps: list[TraceStep] = []
    previous_output = ""
    for index, raw_message in enumerate(raw_messages, start=1):
        message = raw_message if isinstance(raw_message, dict) else {"content": raw_message}
        tool_name = _extract_tool_name(message)
        role = str(_first_non_empty(message.get("role"), message.get("type"), "")).lower()
        content = _textify(
            _first_non_empty(
                message.get("content"),
                message.get("output"),
                message.get("message"),
                message.get("text"),
            )
        )
        input_prompt = _textify(
            _first_non_empty(
                message.get("prompt"),
                message.get("context"),
                previous_output if role not in {"user", "system"} else None,
            )
        )
        if not (content or input_prompt or tool_name):
            continue
        metadata = _extract_common_metadata(message, framework="autogen")
        steps.append(
            _build_step(
                raw=message,
                index=index,
                framework="autogen",
                agent_name=_first_non_empty(
                    message.get("name"),
                    message.get("source"),
                    message.get("speaker"),
                    message.get("agent"),
                    role.title() if role else f"AutoGenStep{index}",
                ),
                input_prompt=input_prompt,
                output_response=content,
                tool_name=tool_name,
                tool_args=_extract_tool_args(message),
                tool_result=_extract_tool_result(message),
                memory_reads=_normalize_memory_entries(
                    _first_non_empty(message.get("memory_reads"), message.get("context"))
                ),
                memory_writes=_normalize_memory_entries(message.get("memory_writes")),
                metadata=metadata,
            )
        )
        if content:
            previous_output = content

    if not steps:
        raise ValueError("AutoGen payload did not contain importable messages.")

    trace = AgentTrace(
        trace_id=_infer_trace_id(payload if isinstance(payload, dict) else {}, prefix="autogen"),
        title=str(
            _first_non_empty(
                payload.get("title") if isinstance(payload, dict) else None,
                payload.get("name") if isinstance(payload, dict) else None,
                "Imported AutoGen Trace",
            )
        ),
        task_description=_textify(
            _first_non_empty(
                payload.get("task_description") if isinstance(payload, dict) else None,
                payload.get("task") if isinstance(payload, dict) else None,
                payload.get("input") if isinstance(payload, dict) else None,
                "Imported AutoGen conversation",
            )
        ),
        expected_output=_optional_text(
            payload.get("expected_output") if isinstance(payload, dict) else None
        ),
        final_output=_infer_final_output(payload if isinstance(payload, dict) else {}, steps),
        steps=steps,
        failure_summary=_optional_text(
            payload.get("failure_summary") if isinstance(payload, dict) else None
        ),
        tags=["imported", "autogen"],
        metadata=_trace_metadata(payload if isinstance(payload, dict) else {}, framework="autogen"),
    )
    return AdapterOutcome(
        framework="autogen",
        trace=trace,
        notes=[
            "Mapped AutoGen conversation turns into debugger steps.",
            "Previous agent output was threaded into later step inputs when no explicit prompt was present.",
        ],
    )


def _adapt_openai_agents(payload: Any) -> AdapterOutcome:
    if not isinstance(payload, dict):
        raise ValueError("OpenAI Agents imports require an object payload.")

    raw_items = _ensure_list(payload.get("items") or payload.get("trace") or payload.get("events"))
    if not raw_items:
        raise ValueError("No OpenAI Agents items were found.")

    steps: list[TraceStep] = []
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            continue
        tool_name = _extract_tool_name(raw_item)
        input_prompt = _textify(
            _first_non_empty(
                raw_item.get("input"),
                raw_item.get("prompt"),
                raw_item.get("arguments"),
                raw_item.get("request"),
            )
        )
        output_response = _textify(
            _first_non_empty(
                raw_item.get("output"),
                raw_item.get("content"),
                raw_item.get("response"),
                raw_item.get("result"),
                raw_item.get("summary"),
            )
        )
        if not (input_prompt or output_response or tool_name):
            continue

        metadata = _extract_common_metadata(raw_item, framework="openai_agents")
        if isinstance(raw_item.get("attributes"), dict):
            metadata["attributes"] = raw_item.get("attributes")

        steps.append(
            _build_step(
                raw=raw_item,
                index=index,
                framework="openai_agents",
                agent_name=_first_non_empty(
                    raw_item.get("agent_name"),
                    raw_item.get("agent"),
                    raw_item.get("name"),
                    raw_item.get("span_name"),
                    f"OpenAIAgentStep{index}",
                ),
                input_prompt=input_prompt,
                output_response=output_response,
                tool_name=tool_name,
                tool_args=_extract_tool_args(raw_item),
                tool_result=_extract_tool_result(raw_item),
                memory_reads=_normalize_memory_entries(raw_item.get("memory_reads")),
                memory_writes=_normalize_memory_entries(raw_item.get("memory_writes")),
                metadata=metadata,
            )
        )

    if not steps:
        raise ValueError("OpenAI Agents payload did not contain importable items.")

    trace = AgentTrace(
        trace_id=_infer_trace_id(payload, prefix="openai_agents"),
        title=str(
            _first_non_empty(
                payload.get("title"),
                payload.get("workflow_name"),
                payload.get("name"),
                "Imported OpenAI Agents Trace",
            )
        ),
        task_description=_textify(
            _first_non_empty(
                payload.get("task_description"),
                payload.get("input"),
                payload.get("instructions"),
                "Imported OpenAI Agents run",
            )
        ),
        expected_output=_optional_text(payload.get("expected_output")),
        final_output=_infer_final_output(payload, steps),
        steps=steps,
        failure_summary=_optional_text(payload.get("failure_summary")),
        tags=["imported", "openai_agents"],
        metadata=_trace_metadata(payload, framework="openai_agents"),
    )
    return AdapterOutcome(
        framework="openai_agents",
        trace=trace,
        notes=[
            "Mapped OpenAI Agents items or spans into debugger steps.",
            "Tool calls and reasoning items were preserved when present.",
        ],
    )


def _adapt_generic(payload: Any) -> AdapterOutcome:
    if isinstance(payload, dict) and isinstance(payload.get("steps"), list):
        steps = [
            _build_step_from_generic(raw_step, index=index, framework="generic")
            for index, raw_step in enumerate(payload["steps"], start=1)
            if isinstance(raw_step, dict)
        ]
    elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
        steps = [
            _build_step_from_generic(raw_step, index=index, framework="generic")
            for index, raw_step in enumerate(payload["events"], start=1)
            if isinstance(raw_step, dict)
        ]
    else:
        sequence = payload if isinstance(payload, list) else _ensure_list(
            payload.get("messages") if isinstance(payload, dict) else None
        )
        if sequence:
            steps = [
                _build_step_from_generic(raw_step, index=index, framework="generic")
                for index, raw_step in enumerate(sequence, start=1)
                if isinstance(raw_step, dict) or isinstance(raw_step, str)
            ]
        else:
            steps = []

    steps = [step for step in steps if step.output_response or step.input_prompt or step.tool_name]
    if not steps and isinstance(payload, dict):
        steps = [
            _build_step(
                raw=payload,
                index=1,
                framework="generic",
                agent_name=_first_non_empty(payload.get("agent"), payload.get("name"), "ImportedRun"),
                input_prompt=_textify(_first_non_empty(payload.get("input"), payload.get("prompt"))),
                output_response=_textify(
                    _first_non_empty(payload.get("output"), payload.get("final_output"), payload.get("result"))
                ),
                tool_name=_extract_tool_name(payload),
                tool_args=_extract_tool_args(payload),
                tool_result=_extract_tool_result(payload),
                metadata=_extract_common_metadata(payload, framework="generic"),
            )
        ]

    if not steps:
        raise ValueError("The payload did not contain any importable steps, events, or messages.")

    payload_dict = payload if isinstance(payload, dict) else {}
    trace = AgentTrace(
        trace_id=_infer_trace_id(payload_dict, prefix="imported"),
        title=str(
            _first_non_empty(
                payload_dict.get("title"),
                payload_dict.get("name"),
                "Imported Custom Trace",
            )
        ),
        task_description=_textify(
            _first_non_empty(
                payload_dict.get("task_description"),
                payload_dict.get("task"),
                payload_dict.get("input"),
                "Imported custom multi-agent run",
            )
        ),
        expected_output=_optional_text(payload_dict.get("expected_output")),
        final_output=_infer_final_output(payload_dict, steps),
        steps=steps,
        failure_summary=_optional_text(payload_dict.get("failure_summary")),
        tags=["imported", "generic"],
        metadata=_trace_metadata(payload_dict, framework="generic"),
    )
    return AdapterOutcome(
        framework="generic",
        trace=trace,
        notes=[
            "Used the generic adapter because the payload did not match a more specific framework shape.",
        ],
    )


def _build_step_from_generic(raw_value: Any, *, index: int, framework: ImportFramework) -> TraceStep:
    raw = raw_value if isinstance(raw_value, dict) else {"content": raw_value}
    output_response = _textify(
        _first_non_empty(
            raw.get("output"),
            raw.get("content"),
            raw.get("message"),
            raw.get("result"),
        )
    )
    return _build_step(
        raw=raw,
        index=index,
        framework=framework,
        agent_name=_first_non_empty(
            raw.get("agent_name"),
            raw.get("agent"),
            raw.get("name"),
            raw.get("node"),
            f"ImportedStep{index}",
        ),
        input_prompt=_textify(_first_non_empty(raw.get("input"), raw.get("prompt"), raw.get("context"))),
        output_response=output_response,
        tool_name=_extract_tool_name(raw),
        tool_args=_extract_tool_args(raw),
        tool_result=_extract_tool_result(raw),
        memory_reads=_normalize_memory_entries(raw.get("memory_reads")),
        memory_writes=_normalize_memory_entries(raw.get("memory_writes")),
        metadata=_extract_common_metadata(raw, framework=framework),
    )


def _finalize_trace(
    trace: AgentTrace,
    *,
    framework: ImportFramework,
    source_name: str | None,
    title_override: str | None,
    task_description_override: str | None,
) -> AgentTrace:
    sanitized_trace_id = _safe_slug(trace.trace_id) or f"{framework}_{generate_uuid()[:8]}"
    metadata = dict(trace.metadata)
    metadata["imported_framework"] = framework
    if source_name:
        metadata["import_source_name"] = source_name
    tags = list(dict.fromkeys([*trace.tags, "imported", framework]))
    normalized_steps = [
        step.model_copy(
            update={
                "id": step.id or f"s{index}",
                "timestamp": step.timestamp or (time.time() + index),
            }
        )
        for index, step in enumerate(trace.steps, start=1)
    ]
    steps = _ensure_unique_step_ids(normalized_steps)
    return trace.model_copy(
        update={
            "trace_id": sanitized_trace_id,
            "title": title_override or trace.title or f"Imported {framework.title()} Trace",
            "task_description": task_description_override or trace.task_description or "Imported multi-agent run",
            "final_output": trace.final_output or (steps[-1].output_response if steps else ""),
            "failure_summary": trace.failure_summary or f"Imported from {framework} adapter.",
            "tags": tags,
            "metadata": metadata,
            "steps": steps,
            "analysis": None,
        }
    )


def _ensure_unique_step_ids(steps: list[TraceStep]) -> list[TraceStep]:
    seen: dict[str, int] = {}
    unique_steps: list[TraceStep] = []
    for index, step in enumerate(steps, start=1):
        base_id = _safe_slug(step.id) or f"s{index}"
        count = seen.get(base_id, 0)
        seen[base_id] = count + 1
        unique_id = base_id if count == 0 else f"{base_id}_{count + 1}"
        unique_steps.append(step.model_copy(update={"id": unique_id}))
    return unique_steps


def _sanitize_trace(trace: AgentTrace) -> tuple[AgentTrace, list[str]]:
    settings = get_settings()
    notes: list[str] = []
    steps = list(trace.steps)
    if len(steps) > settings.import_max_steps:
        kept_steps = steps[: max(1, settings.import_max_steps - 1)]
        if steps[-1] not in kept_steps:
            kept_steps.append(steps[-1])
        notes.append(
            f"Trimmed imported trace from {len(steps)} to {len(kept_steps)} steps for stability."
        )
        steps = kept_steps

    sanitized_steps = [
        _sanitize_step(
            step,
            text_limit=settings.import_max_text_chars,
            list_limit=settings.import_max_list_entries,
        )
        for step in steps
    ]
    sanitized_trace = trace.model_copy(
        update={
            "title": _trim_text(trace.title, settings.import_max_text_chars),
            "task_description": _trim_text(
                trace.task_description, settings.import_max_text_chars
            ),
            "expected_output": (
                _trim_text(trace.expected_output, settings.import_max_text_chars)
                if trace.expected_output
                else None
            ),
            "final_output": _trim_text(trace.final_output, settings.import_max_text_chars),
            "failure_summary": (
                _trim_text(trace.failure_summary, settings.import_max_text_chars)
                if trace.failure_summary
                else None
            ),
            "tags": [
                _trim_text(tag, 80)
                for tag in list(dict.fromkeys(trace.tags))[: settings.import_max_list_entries]
            ],
            "metadata": _sanitize_value(
                trace.metadata,
                max_chars=settings.import_max_text_chars,
                max_entries=settings.import_max_list_entries,
            ),
            "steps": sanitized_steps,
        }
    )
    return sanitized_trace, notes


def _sanitize_step(step: TraceStep, *, text_limit: int, list_limit: int) -> TraceStep:
    tool_snapshot = None
    if step.tool_snapshot is not None:
        tool_snapshot = step.tool_snapshot.model_copy(
            update={
                "tool_name": _trim_text(step.tool_snapshot.tool_name, 200),
                "normalized_args": _sanitize_value(
                    step.tool_snapshot.normalized_args,
                    max_chars=text_limit,
                    max_entries=list_limit,
                ),
                "result": _sanitize_value(
                    step.tool_snapshot.result,
                    max_chars=text_limit,
                    max_entries=list_limit,
                ),
                "result_digest": _trim_text(step.tool_snapshot.result_digest, 120),
                "invalidation_reason": (
                    _trim_text(step.tool_snapshot.invalidation_reason, 200)
                    if step.tool_snapshot.invalidation_reason
                    else None
                ),
            }
        )

    environment_snapshot = None
    if step.environment_snapshot is not None:
        environment_snapshot = step.environment_snapshot.model_copy(
            update={
                "model_name": (
                    _trim_text(step.environment_snapshot.model_name, 120)
                    if step.environment_snapshot.model_name
                    else None
                ),
                "prompt_version": (
                    _trim_text(step.environment_snapshot.prompt_version, 120)
                    if step.environment_snapshot.prompt_version
                    else None
                ),
                "tool_versions": step.environment_snapshot.tool_versions[:list_limit],
                "memory_digest": (
                    _trim_text(step.environment_snapshot.memory_digest, 120)
                    if step.environment_snapshot.memory_digest
                    else None
                ),
                "config_flags": _sanitize_value(
                    step.environment_snapshot.config_flags,
                    max_chars=text_limit // 2,
                    max_entries=list_limit,
                ),
                "auth_scope": (
                    _trim_text(step.environment_snapshot.auth_scope, 120)
                    if step.environment_snapshot.auth_scope
                    else None
                ),
                "clock_version": (
                    _trim_text(step.environment_snapshot.clock_version, 120)
                    if step.environment_snapshot.clock_version
                    else None
                ),
            }
        )

    return step.model_copy(
        update={
            "agent_name": _trim_text(step.agent_name, 200),
            "tool_name": _trim_text(step.tool_name, 200) if step.tool_name else None,
            "tool_args": _sanitize_value(
                step.tool_args,
                max_chars=text_limit,
                max_entries=list_limit,
            ),
            "tool_result": _sanitize_value(
                step.tool_result,
                max_chars=text_limit,
                max_entries=list_limit,
            ),
            "input_prompt": _trim_text(step.input_prompt, text_limit),
            "output_response": _trim_text(step.output_response, text_limit),
            "claims": _sanitize_string_list(step.claims, item_limit=list_limit),
            "memory_reads": _sanitize_string_list(
                step.memory_reads,
                item_limit=list_limit,
            ),
            "memory_writes": _sanitize_string_list(
                step.memory_writes,
                item_limit=list_limit,
            ),
            "tool_snapshot": tool_snapshot,
            "environment_snapshot": environment_snapshot,
            "metadata": _sanitize_value(
                step.metadata,
                max_chars=text_limit // 2,
                max_entries=list_limit,
            ),
        }
    )


def _sanitize_string_list(values: list[str], *, item_limit: int) -> list[str]:
    trimmed = [_trim_text(value, 240) for value in values[:item_limit]]
    if len(values) > item_limit:
        trimmed.append(f"...[truncated {len(values) - item_limit} entries]")
    return trimmed


def _sanitize_value(value: Any, *, max_chars: int, max_entries: int) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return _trim_text(value, max_chars)
    if isinstance(value, list):
        sanitized_items = [
            _sanitize_value(item, max_chars=max_chars, max_entries=max_entries)
            for item in value[:max_entries]
        ]
        if len(value) > max_entries:
            sanitized_items.append(f"...[truncated {len(value) - max_entries} entries]")
        return sanitized_items
    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        items = list(value.items())[:max_entries]
        for key, nested_value in items:
            safe_key = _trim_text(str(key), 80) or "field"
            sanitized_dict[safe_key] = _sanitize_value(
                nested_value,
                max_chars=max_chars,
                max_entries=max_entries,
            )
        if len(value) > max_entries:
            sanitized_dict["__truncated__"] = (
                f"{len(value) - max_entries} additional entries omitted"
            )
        return sanitized_dict
    return _trim_text(str(value), max_chars)


def _trim_text(value: str | None, max_chars: int) -> str:
    if not value:
        return ""
    if len(value) <= max_chars:
        return value
    if max_chars <= 16:
        return value[:max_chars]
    return f"{value[: max_chars - 16].rstrip()} ...[truncated]"


def _build_step(
    *,
    raw: dict[str, Any],
    index: int,
    framework: ImportFramework,
    agent_name: Any,
    input_prompt: str,
    output_response: str,
    tool_name: str | None = None,
    tool_args: Any | None = None,
    tool_result: Any | None = None,
    memory_reads: list[str] | None = None,
    memory_writes: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> TraceStep:
    merged_metadata = dict(metadata or {})
    merged_metadata.setdefault("framework", framework)
    return TraceStep(
        id=str(_first_non_empty(raw.get("id"), raw.get("step_id"), f"s{index}")),
        agent_name=str(agent_name),
        step_type=_infer_step_type(raw, tool_name=tool_name),
        status=_infer_status(raw),
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result=tool_result,
        input_prompt=input_prompt,
        output_response=output_response,
        timestamp=_normalize_timestamp(
            _first_non_empty(
                raw.get("timestamp"),
                raw.get("created_at"),
                raw.get("ended_at"),
                raw.get("ts"),
            ),
            fallback=time.time() + index,
        ),
        cost_usd=_coerce_float(
            _first_non_empty(raw.get("cost_usd"), raw.get("cost"), 0.0),
            default=0.0,
        ),
        tokens=_coerce_int(
            _first_non_empty(raw.get("tokens"), raw.get("token_count"), count_tokens(output_response)),
            default=count_tokens(output_response),
        ),
        duration_seconds=_coerce_float(
            _first_non_empty(raw.get("duration_seconds"), raw.get("latency_seconds"), raw.get("duration"), 0.0),
            default=0.0,
        ),
        claims=_normalize_claims(raw.get("claims")),
        memory_reads=memory_reads or [],
        memory_writes=memory_writes or [],
        metadata=merged_metadata,
    )


def _extract_common_metadata(raw: dict[str, Any], *, framework: ImportFramework) -> dict[str, Any]:
    metadata = dict(raw.get("metadata") or {})
    metadata["framework"] = framework
    for input_key, output_key in (
        ("model", "model_name"),
        ("model_name", "model_name"),
        ("model_version", "model_version"),
        ("prompt_version", "prompt_version"),
        ("tool_version", "tool_version"),
        ("source_quality", "source_quality"),
        ("source_age_days", "source_age_days"),
        ("error", "error"),
        ("warning", "warning"),
        ("type", "raw_type"),
        ("event", "raw_event"),
        ("kind", "raw_kind"),
    ):
        value = raw.get(input_key)
        if value is not None:
            metadata[output_key] = value
    return metadata


def _extract_tool_name(raw: dict[str, Any]) -> str | None:
    direct = _first_non_empty(raw.get("tool_name"), raw.get("tool"), raw.get("function_name"))
    if direct:
        return str(direct)

    tool_call = raw.get("tool_call") or raw.get("function_call")
    if isinstance(tool_call, dict):
        nested = _first_non_empty(tool_call.get("name"), tool_call.get("tool_name"), tool_call.get("tool"))
        if nested:
            return str(nested)

    tool_calls = _ensure_list(raw.get("tool_calls"))
    if tool_calls and isinstance(tool_calls[0], dict):
        nested = _first_non_empty(tool_calls[0].get("name"), tool_calls[0].get("tool_name"))
        if nested:
            return str(nested)
    return None


def _extract_tool_args(raw: dict[str, Any]) -> dict[str, Any] | str | None:
    value = _first_non_empty(
        raw.get("tool_args"),
        raw.get("arguments"),
        raw.get("args"),
        raw.get("kwargs"),
        raw.get("tool_input"),
    )
    if value is None:
        tool_call = raw.get("tool_call") or raw.get("function_call")
        if isinstance(tool_call, dict):
            value = _first_non_empty(tool_call.get("arguments"), tool_call.get("args"))
    if isinstance(value, (dict, str)):
        return value
    if value is None:
        return None
    return _textify(value)


def _extract_tool_result(raw: dict[str, Any]) -> Any | None:
    value = _first_non_empty(
        raw.get("tool_result"),
        raw.get("observation"),
        raw.get("tool_output"),
        raw.get("result") if _extract_tool_name(raw) else None,
    )
    if value is None:
        return None
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return _textify(value)


def _infer_status(raw: dict[str, Any]) -> str:
    status = str(_first_non_empty(raw.get("status"), raw.get("state"), raw.get("outcome"), "ok")).lower()
    if status in {"error", "failed", "failure", "exception"} or raw.get("error"):
        return "error"
    if status in {"warning", "partial", "degraded"} or raw.get("warning"):
        return "warning"
    return "ok"


def _infer_step_type(raw: dict[str, Any], *, tool_name: str | None) -> str:
    if tool_name:
        return "tool"
    hints = " ".join(
        str(value).lower()
        for value in (
            raw.get("type"),
            raw.get("event"),
            raw.get("kind"),
            raw.get("name"),
            raw.get("node"),
        )
        if value
    )
    if any(token in hints for token in ("review", "critic", "validator")):
        return "review"
    if any(token in hints for token in ("analysis", "reason", "plan", "judge", "synth")):
        return "analysis"
    return "llm"


def _normalize_memory_entries(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [f"{key}={_compact_text(raw_value)}" for key, raw_value in value.items()]
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            if isinstance(item, dict):
                normalized.extend(
                    f"{key}={_compact_text(raw_value)}" for key, raw_value in item.items()
                )
            elif item is not None:
                normalized.append(_compact_text(item))
        return normalized
    return [_compact_text(value)]


def _normalize_claims(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_compact_text(item) for item in value if item is not None]
    return [_compact_text(value)]


def _trace_metadata(payload: dict[str, Any], *, framework: ImportFramework) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") or {})
    metadata["framework"] = framework
    if payload.get("run_id") is not None:
        metadata["run_id"] = payload.get("run_id")
    if payload.get("session_id") is not None:
        metadata["session_id"] = payload.get("session_id")
    return metadata


def _infer_trace_id(payload: dict[str, Any], *, prefix: str) -> str:
    value = _first_non_empty(
        payload.get("trace_id"),
        payload.get("run_id"),
        payload.get("session_id"),
        payload.get("id"),
    )
    if value is None:
        return f"{prefix}_{generate_uuid()[:8]}"
    return _safe_slug(str(value)) or f"{prefix}_{generate_uuid()[:8]}"


def _infer_final_output(payload: dict[str, Any], steps: list[TraceStep]) -> str:
    explicit = _optional_text(
        _first_non_empty(
            payload.get("final_output"),
            payload.get("output"),
            payload.get("result"),
            payload.get("final_answer"),
        )
    )
    if explicit:
        return explicit
    return steps[-1].output_response if steps else ""


def _normalize_timestamp(value: Any, *, fallback: float) -> float:
    if value is None:
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return fallback
        try:
            return float(stripped)
        except ValueError:
            try:
                return datetime.fromisoformat(stripped.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return fallback
    return fallback


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _textify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for part in (_textify(item) for item in value) if part)
    if isinstance(value, dict):
        preferred_keys = ("content", "text", "message", "output", "result", "value")
        picked = [_textify(value.get(key)) for key in preferred_keys if value.get(key) is not None]
        if picked:
            return "\n".join(part for part in picked if part)
        return json.dumps(value, ensure_ascii=True, default=str)
    return str(value)


def _optional_text(value: Any) -> str | None:
    text = _textify(value).strip()
    return text or None


def _compact_text(value: Any) -> str:
    text = _textify(value).replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)[:160]


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80]


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
