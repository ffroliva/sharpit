from __future__ import annotations

import copy
import sys
from collections import Counter
from collections.abc import Mapping
from typing import Any, cast

from sharpit.engine.capture.traces import SpanBuffer
from sharpit.engine.masking import MASK, Exposure, Masker

from . import AiSettings, recognizer

_MAX_CHATS = 500
_MAX_MODEL_BREAKDOWN = 50
_MAX_TOKEN_MINUTES = 240
_NANOS_PER_MINUTE = 60_000_000_000
# D-A1, fail closed: under MASKED a chat span's string attribute is shown only for this metadata (lower-case keys);
# every other string, whatever its name, is null. Numbers and booleans keep the traces rendering.
_METADATA_KEYS = frozenset(
    {
        "gen_ai.operation.name",
        "gen_ai.system",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.request.model_name",
        "gen_ai.response.model",
        "gen_ai.response.model_name",
        "gen_ai.request.temperature",
        "gen_ai.request.max_tokens",
        "gen_ai.request.top_p",
        "gen_ai.request.top_k",
        "gen_ai.request.frequency_penalty",
        "gen_ai.request.presence_penalty",
        "gen_ai.request.seed",
        "gen_ai.request.choice.count",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.total_tokens",
        "gen_ai.usage.prompt_tokens",
        "gen_ai.usage.completion_tokens",
        "gen_ai.response.finish_reasons",
        "gen_ai.response.finish_reason",
        "gen_ai.response.id",
        "gen_ai.output.type",
        "gen_ai.tool.name",
        "gen_ai.tool.type",
        "gen_ai.tool.call.id",
        "spring.ai.tool.definition.name",
        "spring.ai.tool.name",
        "spring.ai.kind",
        "server.address",
        "server.port",
        "error.type",
        "finish_reason",
        "index",
    }
)
_NUMERIC_TYPES = frozenset({"BOOLEAN", "LONG", "DOUBLE", "BOOLEAN_ARRAY", "LONG_ARRAY", "DOUBLE_ARRAY"})
_GENAI_INSTRUMENTATIONS = (
    "opentelemetry.instrumentation.openai_v2",
    "opentelemetry.instrumentation.genai.agno",
    "opentelemetry.instrumentation.genai.anthropic",
    "opentelemetry.instrumentation.genai.bedrock",
    "opentelemetry.instrumentation.genai.dspy",
    "opentelemetry.instrumentation.genai.langchain",
    "opentelemetry.instrumentation.genai.llama_index",
    "opentelemetry.instrumentation.genai.openai",
    "opentelemetry.instrumentation.genai.openai_agents",
    "opentelemetry.instrumentation.genai.portkey",
    "opentelemetry.instrumentation.genai.qwen_agent",
    "opentelemetry.instrumentation.genai.qwenpaw",
    "opentelemetry.instrumentation.genai.smolagents",
    "opentelemetry.instrumentation.genai.google_genai",
    "opentelemetry.instrumentation.genai.claude_agent_sdk",
    "opentelemetry.instrumentation.genai.crewai",
    "opentelemetry.instrumentation.genai.weaviate_client",
)


def _attributes(span: Any) -> Mapping[str, Any]:
    attributes = getattr(span, "attributes", None)
    return cast(Mapping[str, Any], attributes) if isinstance(attributes, Mapping) else {}


def _spans(buffer: SpanBuffer) -> tuple[dict[str, list[Any]], list[Any]]:
    traces = buffer.trace_spans()
    return traces, [span for spans in traces.values() for span in spans]


def _id(span: Any, key: str, width: int) -> str:
    context = getattr(span, "context", None)
    value = getattr(context, key, 0)
    return f"{value:0{width}x}"


def _end(span: Any) -> int:
    return getattr(span, "end_time", None) or getattr(span, "start_time", 0)


def _duration(span: Any) -> int:
    return max(0, _end(span) - getattr(span, "start_time", 0))


def _status(span: Any) -> str:
    status = getattr(span, "status", None)
    code = getattr(status, "status_code", None)
    return getattr(code, "name", "UNSET")


def _chats(spans: list[Any]) -> list[Any]:
    return sorted(
        (span for span in spans if recognizer.operation(_attributes(span), getattr(span, "name", "")) == "chat"),
        key=lambda span: getattr(span, "start_time", 0),
        reverse=True,
    )


def _name(masker: Masker, name: str | None) -> str | None:
    """A provider, model, tool or collection name: metadata, so METADATA_ONLY shows it unless it is secret-shaped."""
    if name is None or getattr(masker, "_exposure", None) is not Exposure.METADATA_ONLY:
        return masker.mask_text(name)
    shape = copy.copy(masker)  # the live never-shown secrets and policy; only the exposure is switched
    setattr(shape, "_exposure", Exposure.MASKED)  # noqa: B010 - a private field, set on the copy only
    return MASK if shape.mask_text(name) != name else name


def _preferred_model(attributes: Mapping[str, Any]) -> str:
    return recognizer.response_model(attributes) or recognizer.request_model(attributes) or "unknown"


def _summary(span: Any, siblings: list[Any], masker: Masker) -> dict[str, Any]:
    attributes = _attributes(span)
    tool_count = sum(
        recognizer.operation(_attributes(sibling), getattr(sibling, "name", "")) == "tool" for sibling in siblings
    )
    vector_count = sum(
        recognizer.operation(_attributes(sibling), getattr(sibling, "name", "")) == "retrieval" for sibling in siblings
    )
    return {
        "traceId": _id(span, "trace_id", 32),
        "spanId": _id(span, "span_id", 16),
        "startEpochNanos": getattr(span, "start_time", 0),
        "durationNanos": _duration(span),
        "provider": _name(masker, recognizer.provider(attributes)),
        "requestModel": _name(masker, recognizer.request_model(attributes)),
        "responseModel": _name(masker, recognizer.response_model(attributes)),
        "inputTokens": recognizer.input_tokens(attributes),
        "outputTokens": recognizer.output_tokens(attributes),
        "totalTokens": recognizer.total_tokens(attributes),
        "finishReason": _name(masker, recognizer.finish_reason(attributes)),
        "statusCode": _status(span),
        "operation": "chat",
        "toolCallCount": tool_count,
        "vectorOperationCount": vector_count,
    }


def ai_overview(buffer: SpanBuffer, settings: AiSettings, now_ns: int) -> dict[str, Any]:
    traces, spans = _spans(buffer)
    chats = _chats(spans)
    tokens_by_model: dict[str, int] = {}
    calls_by_model: dict[str, int] = {}
    total_input = total_output = duration = errors = 0
    for chat in chats:
        attributes = _attributes(chat)
        input_count = recognizer.input_tokens(attributes) or 0
        output_count = recognizer.output_tokens(attributes) or 0
        model = _name(buffer.masker, _preferred_model(attributes)) or "unknown"
        total_input += input_count
        total_output += output_count
        duration += _duration(chat)
        errors += _status(chat) == "ERROR"
        tokens_by_model[model] = tokens_by_model.get(model, 0) + input_count + output_count
        calls_by_model[model] = calls_by_model.get(model, 0) + 1
    operations = Counter(recognizer.operation(_attributes(span), getattr(span, "name", "")) for span in spans)
    recent_limit = max(0, min(settings.max_recent_chats, _MAX_CHATS))
    recent = [_summary(chat, traces.get(_id(chat, "trace_id", 32), []), buffer.masker) for chat in chats[:recent_limit]]
    spring_ai = langchain4j = False
    framework_detected = any(name in sys.modules for name in _GENAI_INSTRUMENTATIONS)
    banner = (
        "Set OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true to capture prompt and completion content."
        if framework_detected and settings.show_content_capture_banner
        else None
    )
    return {
        "enabled": settings.traces_enabled,
        "springAiDetected": spring_ai,
        "langChain4jDetected": langchain4j,
        "aiFrameworkDetected": framework_detected,
        "totalChats": len(chats),
        "totalInputTokens": total_input,
        "totalOutputTokens": total_output,
        "tokensByModel": dict(
            sorted(tokens_by_model.items(), key=lambda item: item[1], reverse=True)[:_MAX_MODEL_BREAKDOWN]
        ),
        "callsByModel": dict(
            sorted(calls_by_model.items(), key=lambda item: item[1], reverse=True)[:_MAX_MODEL_BREAKDOWN]
        ),
        "errorCount": errors,
        "averageDurationNanos": duration // len(chats) if chats else 0,
        "toolCallCount": operations["tool"],
        "vectorOperationCount": operations["retrieval"],
        "embeddingCount": operations["embeddings"],
        "recent": recent,
        "contentBanner": banner,
    }


def ai_chats(buffer: SpanBuffer, limit: int | None) -> list[dict[str, Any]]:
    traces, spans = _spans(buffer)
    return [
        _summary(chat, traces.get(_id(chat, "trace_id", 32), []), buffer.masker)
        for chat in _chats(spans)[: max(1, min(limit if limit is not None else 100, _MAX_CHATS))]
    ]


def _numbers_only(value: object) -> bool:
    """Read on the raw value, every element: the rendered type names only an array's first element."""
    if isinstance(value, list | tuple):
        return all(type(item) in (bool, int, float) for item in cast("list[object]", value))
    return type(value) in (bool, int, float)


def _metadata_only(rows: list[dict[str, Any]], raw: Mapping[str, Any], masker: Masker) -> None:
    for row in rows:
        key = row.get("key")
        value = raw.get(key) if isinstance(key, str) else None
        if not isinstance(key, str) or key.lower() not in _METADATA_KEYS:
            if not _numbers_only(value):
                row["value"] = None
        elif row.get("value") is not None:
            # BootUI leaves numbers as they are (a token count is not a secret token); text is a masked name
            row["value"] = str(value) if type(value) in (int, float) else _name(masker, row["value"])


def _captured(attributes: Mapping[str, Any]) -> bool:
    return any(
        key in attributes
        for key in ("gen_ai.prompt", "gen_ai.completion", "gen_ai.input.messages", "gen_ai.output.messages")
    )


def _tool(span: Any, masker: Masker) -> dict[str, Any]:
    attributes = _attributes(span)
    return {
        "spanId": _id(span, "span_id", 16),
        "name": _name(masker, recognizer.tool_name(attributes, getattr(span, "name", ""))),
        "startEpochNanos": getattr(span, "start_time", 0),
        "durationNanos": _duration(span),
        "statusCode": _status(span),
    }


def _vector(span: Any, masker: Masker) -> dict[str, Any]:
    attributes = _attributes(span)
    return {
        "spanId": _id(span, "span_id", 16),
        "operation": recognizer.vector_operation(attributes),
        "collectionName": _name(masker, recognizer.vector_collection(attributes)),
        "startEpochNanos": getattr(span, "start_time", 0),
        "durationNanos": _duration(span),
        "statusCode": _status(span),
    }


def ai_chat_detail(
    buffer: SpanBuffer, span_id: str, masker: Masker, settings: AiSettings | None = None
) -> dict[str, Any] | None:
    traces, spans = _spans(buffer)
    chat = next((span for span in spans if _id(span, "span_id", 16) == span_id), None)
    if chat is None or recognizer.operation(_attributes(chat), getattr(chat, "name", "")) != "chat":
        return None
    siblings = traces.get(_id(chat, "trace_id", 32), [])
    attributes, events = buffer.render_attributes(chat)
    # OQ12 requires FULL even when secret masking is disabled.
    reveals_content = getattr(masker, "_exposure", None) is Exposure.FULL
    if not reveals_content:
        _metadata_only(attributes, _attributes(chat), masker)
        for event, raw_event in zip(events, getattr(chat, "events", None) or (), strict=False):
            _metadata_only(event.get("attributes", []), _attributes(raw_event), masker)
    content_captured = _captured(_attributes(chat))
    show_banner = True if settings is None else settings.show_content_capture_banner
    return {
        "summary": _summary(chat, siblings, masker),
        "toolCalls": sorted(
            (
                _tool(span, masker)
                for span in siblings
                if recognizer.operation(_attributes(span), getattr(span, "name", "")) == "tool"
            ),
            key=lambda item: item["startEpochNanos"],
        ),
        "vectorOperations": sorted(
            (
                _vector(span, masker)
                for span in siblings
                if recognizer.operation(_attributes(span), getattr(span, "name", "")) == "retrieval"
            ),
            key=lambda item: item["startEpochNanos"],
        ),
        "attributes": attributes,
        "events": events,
        "contentCaptured": content_captured,
        "contentBanner": (
            "Message content is not on this span. Set OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true "
            "to capture prompt and completion text."
            if not content_captured and show_banner
            else None
        ),
    }


def ai_tokens(buffer: SpanBuffer, minutes: int | None, settings: AiSettings, now_ns: int) -> dict[str, Any]:
    window = max(1, min(minutes if minutes is not None else settings.token_series_minutes, _MAX_TOKEN_MINUTES))
    end_minute = now_ns // _NANOS_PER_MINUTE
    start_minute = end_minute - window + 1
    buckets = {minute: [0, 0, 0] for minute in range(start_minute, end_minute + 1)}
    _, spans = _spans(buffer)
    for chat in _chats(spans):
        minute = getattr(chat, "start_time", 0) // _NANOS_PER_MINUTE
        bucket = buckets.get(minute)
        if bucket is None:
            continue
        attributes = _attributes(chat)
        bucket[0] += recognizer.input_tokens(attributes) or 0
        bucket[1] += recognizer.output_tokens(attributes) or 0
        bucket[2] += 1
    return {
        "minutes": window,
        "buckets": [
            {"epochMinute": minute, "inputTokens": values[0], "outputTokens": values[1], "callCount": values[2]}
            for minute, values in buckets.items()
        ],
    }
