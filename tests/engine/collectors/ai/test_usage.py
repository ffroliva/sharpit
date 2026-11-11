from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from sharpit.engine.capture.traces import SpanBuffer as TraceBuffer
from sharpit.engine.masking import Exposure, Masker


def _usage():
    try:
        from sharpit.engine.collectors.ai import usage
    except ImportError:
        usage = None
    assert usage is not None, "AI span usage collector is missing"
    return usage


class SpanBuffer:
    def __init__(self, spans: list[Any], masker: Masker | None = None) -> None:
        self.spans = spans
        self.masker = masker or Masker(Exposure.MASKED, True)

    def trace_spans(self) -> dict[str, list[Any]]:
        grouped: dict[str, list[Any]] = {}
        for span in self.spans:
            grouped.setdefault(f"{span.context.trace_id:032x}", []).append(span)
        return grouped

    def render_attributes(self, span: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        def render(attributes: dict[str, Any]) -> list[dict[str, Any]]:
            output = []
            for key, value in attributes.items():
                shown, hidden = self.masker.mask(key, value)
                output.append({"key": key, "type": "STRING", "value": None if hidden or shown is None else str(shown)})
            return output

        return (
            render(span.attributes),
            [
                {
                    "name": event.name,
                    "timeOffsetNanos": event.timestamp - span.start_time,
                    "attributes": render(event.attributes),
                }
                for event in span.events
            ],
        )


def _span(
    span_id: int,
    operation: str,
    attributes: dict[str, Any],
    *,
    trace_id: int = 1,
    start: int = 60_000_000_000,
    end: int = 61_000_000_000,
    status: str = "UNSET",
    name: str | None = None,
    events: list[Any] | None = None,
) -> Any:
    return SimpleNamespace(
        context=SimpleNamespace(trace_id=trace_id, span_id=span_id),
        name=name or operation,
        kind=SimpleNamespace(name="INTERNAL"),
        attributes={"gen_ai.operation.name": operation, **attributes},
        start_time=start,
        end_time=end,
        status=SimpleNamespace(status_code=SimpleNamespace(name=status)),
        events=events or [],
    )


def _settings(**values: Any) -> Any:
    settings = {
        "token_series_minutes": 60,
        "max_recent_chats": 100,
        "show_content_capture_banner": True,
        "traces_enabled": True,
    }
    settings.update(values)
    return SimpleNamespace(**settings)


def test_ai_overview_aggregates_chat_tool_and_vector_spans():
    # ported: AiControllerTests.overviewAggregatesChatToolAndVectorSpans
    # ported: AiControllerTests.overviewAggregatesChatToolAndVectorSpans
    usage = _usage()
    spans = [
        _span(
            1,
            "chat",
            {
                "gen_ai.provider.name": "openai",
                "gen_ai.response.model": "gpt-4o-mini",
                "gen_ai.usage.input_tokens": 3,
                "gen_ai.usage.output_tokens": 2,
            },
            status="ERROR",
        ),
        _span(2, "execute_tool", {"gen_ai.tool.name": "search"}),
        _span(3, "retrieval", {"db.collection.name": "docs"}),
        _span(4, "embeddings", {}),
    ]
    report = usage.ai_overview(SpanBuffer(spans), _settings(), 120_000_000_000)
    assert report["totalChats"] == 1
    assert report["totalInputTokens"] == 3
    assert report["toolCallCount"] == 1
    assert report["vectorOperationCount"] == 1
    assert report["embeddingCount"] == 1
    assert report["errorCount"] == 1
    assert report["tokensByModel"] == {"gpt-4o-mini": 5}
    assert report["callsByModel"] == {"gpt-4o-mini": 1}


def test_ai_overview_emits_empty_contract_shape_and_disabled_telemetry():
    # ported: AiControllerTests.overviewReportsDisabledTelemetry
    usage = _usage()
    report = usage.ai_overview(SpanBuffer([]), _settings(traces_enabled=False), 60_000_000_000)
    assert list(report) == [
        "enabled",
        "springAiDetected",
        "langChain4jDetected",
        "aiFrameworkDetected",
        "totalChats",
        "totalInputTokens",
        "totalOutputTokens",
        "tokensByModel",
        "callsByModel",
        "errorCount",
        "averageDurationNanos",
        "toolCallCount",
        "vectorOperationCount",
        "embeddingCount",
        "recent",
        "contentBanner",
    ]
    assert report["enabled"] is False
    assert report["springAiDetected"] is False
    assert report["langChain4jDetected"] is False
    assert report["totalChats"] == 0


def test_ai_overview_reports_python_genai_instrumentation(monkeypatch: pytest.MonkeyPatch):
    usage = _usage()
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.openai_v2", object())
    report = usage.ai_overview(SpanBuffer([]), _settings(), 60_000_000_000)
    assert report["springAiDetected"] is False
    assert report["langChain4jDetected"] is False
    assert report["aiFrameworkDetected"] is True
    assert "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true" in report["contentBanner"]


def test_ai_chats_respect_limit_and_are_ordered_most_recent_first():
    # ported: AiControllerTests.chatsRespectLimitAndAreOrderedMostRecentFirst
    # Also ported: AiControllerTests.chatsClampLimitToConfiguredMaximum.
    usage = _usage()
    spans = [_span(i, "chat", {}, start=i * 1_000_000_000) for i in (1, 2, 3)]
    chats = usage.ai_chats(SpanBuffer(spans), 2)
    assert [row["spanId"] for row in chats] == [f"{3:016x}", f"{2:016x}"]
    assert len(usage.ai_chats(SpanBuffer(spans), 0)) == 1
    assert len(usage.ai_chats(SpanBuffer([_span(i, "chat", {}) for i in range(501)]), 9999)) == 500


def test_ai_chat_detail_returns_linked_tools_and_vector_operations():
    # ported: AiControllerTests.chatDetailReturnsLinkedToolsAndVectorOperations
    usage = _usage()
    chat = _span(1, "chat", {"gen_ai.input.messages": "hello"})
    tool = _span(2, "execute_tool", {"gen_ai.tool.name": "search"}, start=62_000_000_000)
    vector = _span(3, "retrieval", {"db.collection.name": "docs"}, start=63_000_000_000)
    detail = usage.ai_chat_detail(SpanBuffer([chat, tool, vector]), f"{1:016x}", Masker(Exposure.FULL, True))
    assert detail is not None
    assert len(detail["toolCalls"]) == 1
    assert len(detail["vectorOperations"]) == 1
    assert detail["contentCaptured"] is True
    assert next(item["value"] for item in detail["attributes"] if item["key"] == "gen_ai.input.messages") == "hello"


def test_ai_content_keys_null_unless_full():
    # adapted: AiUsageServiceTests.maskedExposureScrubsContentAndMasksSensitiveAttributes (deviation D-A1, owner OQ12)
    # Also covers AiUsageServiceTests.fullExposureReturnsChatSpanValuesVerbatim,
    # .metadataOnlyExposureOmitsContentButKeepsItsShape, .contentCaptureIsReportedWhateverTheExposureMode,
    # .everyReadAppliesTheLivePolicy and AiControllerTests.chatDetailFollowsTheLiveValueExposurePolicy.
    usage = _usage()
    chat = _span(
        1,
        "chat",
        {
            "gen_ai.prompt": "sensitive prompt",
            "gen_ai.completion": "sensitive completion",
            "gen_ai.input.messages": "sensitive messages",
            "gen_ai.output.messages": "sensitive output",
            "gen_ai.system_instructions": "sensitive instructions",
            "gen_ai.tool.call.arguments": "sensitive arguments",
            "gen_ai.tool.call.result": "sensitive result",
            "db.vector.query.content": "sensitive vector query",
            "db.vector.query.response.documents": "sensitive documents",
            "gen_ai.prompt.0.content": "sensitive prefixed prompt",
            "gen_ai.completion.0.content": "sensitive prefixed completion",
            "app.note": "password=hunter2",
        },
        events=[
            SimpleNamespace(
                name="event", timestamp=60_000_000_001, attributes={"gen_ai.completion.0.content": "completion"}
            )
        ],
    )
    masked_masker = Masker(Exposure.MASKED, True)
    full_masker = Masker(Exposure.FULL, True)
    masked = usage.ai_chat_detail(SpanBuffer([chat], masked_masker), f"{1:016x}", masked_masker)
    metadata_masker = Masker(Exposure.METADATA_ONLY, True)
    metadata = usage.ai_chat_detail(SpanBuffer([chat], metadata_masker), f"{1:016x}", metadata_masker)
    full = usage.ai_chat_detail(SpanBuffer([chat], full_masker), f"{1:016x}", full_masker)
    assert masked is not None
    assert metadata is not None
    assert full is not None
    values = {item["key"]: item["value"] for item in masked["attributes"]}
    assert values["gen_ai.prompt"] is None
    assert values["gen_ai.completion"] is None
    assert values["gen_ai.input.messages"] is None
    assert values["gen_ai.output.messages"] is None
    assert values["gen_ai.system_instructions"] is None
    assert values["gen_ai.tool.call.arguments"] is None
    assert values["gen_ai.tool.call.result"] is None
    assert values["db.vector.query.content"] is None
    assert values["db.vector.query.response.documents"] is None
    assert values["gen_ai.prompt.0.content"] is None
    assert values["gen_ai.completion.0.content"] is None
    assert values["app.note"] != "password=hunter2"
    assert masked["events"][0]["attributes"][0]["value"] is None
    assert metadata["attributes"][0]["value"] is None
    assert masked["contentCaptured"] is True
    full_values = {item["key"]: item["value"] for item in full["attributes"]}
    assert full_values["gen_ai.prompt"] == "sensitive prompt"
    assert full["contentCaptured"] is True


def test_ai_chat_detail_returns_none_for_unknown_span():
    # ported: AiControllerTests.chatDetailReturnsNotFoundForUnknownSpan
    usage = _usage()
    assert usage.ai_chat_detail(SpanBuffer([]), "0" * 16, Masker(Exposure.MASKED, True)) is None


def test_ai_chat_content_banner_follows_setting():
    usage = _usage()
    chat = _span(1, "chat", {})
    buffer = SpanBuffer([chat])
    shown = usage.ai_chat_detail(buffer, f"{1:016x}", buffer.masker, _settings())
    hidden = usage.ai_chat_detail(buffer, f"{1:016x}", buffer.masker, _settings(show_content_capture_banner=False))
    assert shown is not None
    assert hidden is not None
    assert shown["contentBanner"] is not None
    assert hidden["contentBanner"] is None


def test_ai_tokens_returns_requested_window_and_buckets_chat():
    # ported: AiControllerTests.tokensReturnsRequestedWindowAndBucketsTheChat
    usage = _usage()
    chat = _span(1, "chat", {"gen_ai.usage.input_tokens": 4, "gen_ai.usage.output_tokens": 2}, start=120_000_000_000)
    result = usage.ai_tokens(SpanBuffer([chat]), 2, _settings(), 120_000_000_000)
    assert result["minutes"] == 2
    assert len(result["buckets"]) == 2
    assert result["buckets"][-1]["inputTokens"] == 4
    assert result["buckets"][-1]["outputTokens"] == 2
    assert result["buckets"][-1]["callCount"] == 1


def test_ai_tokens_clamp_and_default_window():
    # ported: AiControllerTests.tokensClampsWindowAndFallsBackToConfiguredDefault
    usage = _usage()
    short = usage.ai_tokens(SpanBuffer([]), 0, _settings(token_series_minutes=17), 60_000_000_000)
    default = usage.ai_tokens(SpanBuffer([]), None, _settings(token_series_minutes=17), 60_000_000_000)
    long = usage.ai_tokens(SpanBuffer([]), 999, _settings(), 60_000_000_000)
    assert short["minutes"] == 1
    assert default["minutes"] == 17
    assert long["minutes"] == 240


def test_ai_chats_share_the_trace_ring():
    buffer = TraceBuffer(Masker(Exposure.MASKED, True), application=lambda: None)
    buffer.add(_span(1, "chat", {}))
    trace_spans = getattr(buffer, "trace_spans", None)
    assert callable(trace_spans), "AI and traces need the same recorded span ring"
    assert len(trace_spans()[f"{1:032x}"]) == 1
