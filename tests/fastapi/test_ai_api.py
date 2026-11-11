"""AI Framework routes over the existing span ring (W7 Task A1)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import otel
from sharpit.engine.capture.traces import span_buffer

API = "/sharpit/api"
FIXTURES = Path(__file__).parents[1] / "fixtures/bootui/2.3.0/ai"


def _client(**kwargs: Any) -> TestClient:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, **kwargs)
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def test_ai_overview_golden_shape_23():
    # ported: AiControllerTests.overviewIsEmptyWhenNoSpans
    golden = json.loads((FIXTURES / "overview.captured.json").read_text(encoding="utf-8"))
    with _client() as client:
        response = client.get(f"{API}/ai/overview")
    assert response.status_code == 200
    assert response.json() == golden
    assert list(response.json()) == list(golden)


def test_ai_tokens_golden_shape_23():
    with _client() as client:
        response = client.get(f"{API}/ai/tokens?minutes=1")
    assert response.status_code == 200
    assert list(response.json()) == ["minutes", "buckets"]
    assert list(response.json()["buckets"][0]) == ["epochMinute", "inputTokens", "outputTokens", "callCount"]


def test_ai_overview_panel_disabled_refuses_read():
    with _client(panels={"ai": {"enabled": False}}) as client:
        response = client.get(f"{API}/ai/overview")
    assert response.status_code == 403


def test_ai_chats_and_detail_read_the_shared_trace_ring():
    # ported: AiControllerTests.chatsRespectLimitAndAreOrderedMostRecentFirst
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    buffer = span_buffer(handle.context)
    for span_id, start in ((1, 1_000), (2, 2_000)):
        buffer.add(
            SimpleNamespace(
                context=SimpleNamespace(trace_id=1, span_id=span_id),
                parent=None,
                name="chat",
                kind=SimpleNamespace(name="INTERNAL"),
                resource=SimpleNamespace(attributes={"service.name": "api"}),
                instrumentation_scope=SimpleNamespace(name="openai"),
                start_time=start,
                end_time=start + 1_000,
                status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET"), description=None),
                attributes={"gen_ai.operation.name": "chat", "gen_ai.system": "openai"},
                events=[],
            )
        )
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        chats = client.get(f"{API}/ai/chats?limit=1")
        detail = client.get(f"{API}/ai/chats/{2:016x}")
    assert chats.status_code == 200
    assert chats.json()[0]["spanId"] == f"{2:016x}"
    assert detail.status_code == 200
    assert detail.json()["summary"]["spanId"] == f"{2:016x}"


def test_ai_spans_recorded_with_sdk(monkeypatch: pytest.MonkeyPatch):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider()
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(otel, "PROCESSOR", otel.SharpitSpanProcessor())
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        with provider.get_tracer("test").start_as_current_span("chat") as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.system", "openai")
        response = client.get(f"{API}/ai/chats")
    provider.shutdown()
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_ai_unknown_chat_returns_contract_404():
    # ported: AiControllerTests.chatDetailReturnsNotFoundForUnknownSpan
    with _client() as client:
        response = client.get(f"{API}/ai/chats/{'0' * 16}")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"] == f"chat span {'0' * 16} not found"


def test_ai_spans_absent_with_traces_panel_disabled():
    # scenario W7 row 17
    with _client(panels={"traces": {"enabled": False}}) as client:
        response = client.get(f"{API}/ai/overview")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["totalChats"] == 0


def test_ai_spans_recorded_with_ai_panel_disabled():
    # scenario W7 row 17
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, panels={"ai": {"enabled": False}})
    span_buffer(handle.context).add(
        SimpleNamespace(
            context=SimpleNamespace(trace_id=1, span_id=1),
            parent=None,
            name="chat",
            kind=SimpleNamespace(name="INTERNAL"),
            resource=SimpleNamespace(attributes={"service.name": "api"}),
            instrumentation_scope=SimpleNamespace(name="openai"),
            start_time=1_000,
            end_time=2_000,
            status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET"), description=None),
            attributes={"gen_ai.operation.name": "chat"},
            events=[],
        )
    )
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        response = client.get(f"{API}/traces")
    assert response.status_code == 200
    assert response.json()["traces"][0]["hasAi"] is True


CONTENT_ATTRIBUTES = {
    "spring.ai.tool.call.arguments": "PROMPTLEAK1",
    "GEN_AI.PROMPT": "PROMPTLEAK2",
    "spring.ai.tool.call.result": "PROMPTLEAK3",
    "input.value": "PROMPTLEAK4",
    "output.value": "PROMPTLEAK5",
    "traceloop.entity.input": "PROMPTLEAK6",
    "traceloop.entity.output": "PROMPTLEAK7",
}
CONTENT_EVENT_ATTRIBUTES = {"content": "PROMPTLEAK8", "gen_ai.event.content": "PROMPTLEAK9"}


@pytest.mark.parametrize(
    "canary", [*CONTENT_ATTRIBUTES.values(), *CONTENT_EVENT_ATTRIBUTES.values()], ids=lambda canary: canary
)
def test_ai_chat_detail_hides_content_under_masked(canary: str):
    # finding W7-A r2 #1: BootUI's spring.ai tool keys, keys matched case-insensitively, and the OpenInference,
    # Traceloop and span-event content keys (D-A1, stricter than BootUI) are hidden unless FULL
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, expose_values="MASKED")
    span_buffer(handle.context).add(
        SimpleNamespace(
            context=SimpleNamespace(trace_id=1, span_id=1),
            parent=None,
            name="chat",
            kind=SimpleNamespace(name="CLIENT"),
            resource=SimpleNamespace(attributes={"service.name": "api"}),
            instrumentation_scope=SimpleNamespace(name="openai"),
            start_time=1_000,
            end_time=2_000,
            status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET"), description=None),
            attributes={"gen_ai.operation.name": "chat", **CONTENT_ATTRIBUTES},
            events=[SimpleNamespace(name="gen_ai.user.message", timestamp=1_500, attributes=CONTENT_EVENT_ATTRIBUTES)],
        )
    )
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        response = client.get(f"{API}/ai/chats/{1:016x}")
    assert response.status_code == 200
    assert canary not in response.text


def test_ai_journal_attached_whichever_route_is_built_first():
    # finding W7-A r2 #3: the AI route used to build the shared buffer without the journal hook
    from sharpit.fastapi.routes import ai, traces

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=("ai",))
    ctx = handle.context
    ctx._cache.pop("traces.buffer")  # pyright: ignore[reportPrivateUsage] - replay a build where the AI route goes first
    ai.build_routes(ctx)
    traces.build_routes(ctx)
    span_buffer(ctx).add(
        SimpleNamespace(
            context=SimpleNamespace(trace_id=1, span_id=1),
            kind=SimpleNamespace(name="INTERNAL"),
            name="chat",
            status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET")),
            attributes={"gen_ai.operation.name": "chat"},
        )
    )
    journal = ctx.capture.journal
    assert journal is not None
    assert len(journal.records("ai")) == 1
