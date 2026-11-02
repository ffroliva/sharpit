"""``traces`` endpoints and MCP tools (lane A-traces, Task 3; BootUI ``TracesControllerTests``).

The OTel SDK is not a test dependency: an SDK-shaped provider is planted in ``sys.modules`` and spans are delivered
through the real ``otel.PROCESSOR``, exactly as the SDK's span pipeline calls it.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.golden import assert_parity

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import otel

API = "/sharpit/api/traces"
TRACE_A = 0x2EBE213F5EE32D51495B4077F5F4DC74
TRACE_B = 0xC9BDC3CBE2A6ED25EF75355D78DB82B4


class Provider:
    def __init__(self) -> None:
        self.processors: list[Any] = []

    def add_span_processor(self, processor: Any) -> None:
        self.processors.append(processor)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> Provider:
    planted = Provider()
    trace = ModuleType("opentelemetry.trace")
    trace.get_tracer_provider = lambda: planted  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))
    monkeypatch.setattr(otel, "PROCESSOR", otel.SharpitSpanProcessor())
    return planted


def span(trace_id: int, start: int, path: str = "/owners") -> Any:
    return SimpleNamespace(
        context=SimpleNamespace(trace_id=trace_id, span_id=7),
        parent=None,
        name=f"GET {path}",
        kind=SimpleNamespace(name="SERVER"),
        resource=SimpleNamespace(attributes={"service.name": "api"}),
        instrumentation_scope=SimpleNamespace(name="tests"),
        start_time=start,
        end_time=start + 2_000,
        status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET"), description=None),
        attributes={"http.route": path},
        events=[],
    )


@pytest.fixture
def client(provider: Provider) -> Iterator[TestClient]:
    app = FastAPI()

    @app.get("/owners")
    def owners() -> list[str]:  # pyright: ignore[reportUnusedFunction]
        return []

    install(app, enabled="ON", show_banner=False, mcp_enabled="ON")
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as started:  # lifespan arms
        yield started


def _two_traces() -> None:
    otel.PROCESSOR.on_end(span(TRACE_A, 1_000))
    otel.PROCESSOR.on_end(span(TRACE_B, 5_000))


def _get(client: TestClient) -> dict[str, Any]:
    response = client.get(API)
    assert response.status_code == 200
    return response.json()


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/sharpit/api/mcp", json=body).json()


def test_golden_parity(client: TestClient):
    _two_traces()
    response = client.get(API)
    assert response.status_code == 200
    assert_parity("traces", "list", response.json())


def test_list_reports_enabled_newest_first(client: TestClient):
    # ported: TracesControllerTests.listDelegatesToService
    _two_traces()
    body = _get(client)
    assert body["enabled"] is True
    assert [t["traceId"] for t in body["traces"]] == [f"{TRACE_B:032x}", f"{TRACE_A:032x}"]


def test_detail_returns_spans(client: TestClient):
    # ported: TracesControllerTests.detailReturnsTrace
    _two_traces()
    response = client.get(f"{API}/{TRACE_A:032x}")
    assert response.status_code == 200
    assert [s["spanId"] for s in response.json()["spans"]] == [f"{7:016x}"]


@pytest.mark.parametrize(("raw", "expected"), [("0", 1), ("-5", 1), ("10000", 2), ("1", 1)])
def test_limit_clamped(client: TestClient, raw: str, expected: int):
    _two_traces()
    response = client.get(API, params={"limit": raw})
    assert response.status_code == 200
    assert len(response.json()["traces"]) == expected


def test_limit_not_a_number_is_400(client: TestClient):
    assert client.get(API, params={"limit": "abc"}).status_code == 400


def test_unknown_trace_404(client: TestClient):
    # ported: TracesControllerTests.unknownTraceIsNotFound
    response = client.get(f"{API}/abc")
    assert response.status_code == 404
    assert response.json() == {"error": "trace abc not found"}


def test_clear_204(client: TestClient):
    # ported: TracesControllerTests.clearRemovesTelemetry
    _two_traces()
    response = client.delete(API)
    assert response.status_code == 204
    assert response.content == b""
    assert _get(client)["traces"] == []


def test_clear_read_only_403(provider: Provider):
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, read_only=True)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as started:
        assert started.delete(API).status_code == 403


def test_no_sdk_reports_the_reason(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delitem(sys.modules, "opentelemetry.sdk.trace", raising=False)
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as started:
        body = _get(started)
    assert body["enabled"] is False
    assert body["unavailableReason"] == otel.NO_SDK


def test_attach_never_during_request(client: TestClient, provider: Provider):
    armed = otel.PROCESSOR.sinks
    for _ in range(3):
        client.get("/owners")
        client.get(API)
    assert provider.processors == [otel.PROCESSOR]
    assert otel.PROCESSOR.sinks == armed


def test_shutdown_disarms_and_restart_rearms(provider: Provider):
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)):
        pass
    assert otel.PROCESSOR.sinks == ()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as again:
        otel.PROCESSOR.on_end(span(TRACE_A, 1_000))
        assert len(_get(again)["traces"]) == 1
    assert provider.processors == [otel.PROCESSOR]


def test_mcp_read_tool_only(client: TestClient):
    _two_traces()
    names = [t["name"] for t in _rpc(client, "tools/list")["result"]["tools"]]
    assert "get_traces" in names
    assert "clear_traces" not in names
    result = _rpc(client, "tools/call", {"name": "get_traces", "arguments": {"limit": 1}})["result"]
    assert result["isError"] is False
    assert len(result["structuredContent"]["traces"]) == 1


# BootUI 2.2.0 records, field order as declared (boot-ui-ref bootui-engine core/dto/*.java).
# O2 forbids this lane writing
# a provisional.json, so the detail DTO is checked against the record field lists instead.
BOOTUI_TRACE_DETAIL = {"traceId": str, "spans": list}  # TraceDetailDto
BOOTUI_SPAN = {  # SpanDto
    "traceId": str,
    "spanId": str,
    "parentSpanId": (str, type(None)),
    "name": str,
    "kind": str,
    "serviceName": (str, type(None)),
    "scope": (str, type(None)),
    "startEpochNanos": int,
    "endEpochNanos": int,
    "durationNanos": int,
    "statusCode": str,
    "statusMessage": (str, type(None)),
    "attributes": list,
    "events": list,
}
BOOTUI_SPAN_EVENT = {"name": str, "timeOffsetNanos": int, "attributes": list}  # SpanEventDto
BOOTUI_SPAN_ATTRIBUTE = {"key": str, "type": str, "value": (str, type(None))}  # SpanAttributeDto (Object value)


def _record_problems(record: dict[str, Any], fields: dict[str, Any], where: str) -> list[str]:
    problems = [f"{where}: keys {list(record)} != {list(fields)}"] if list(record) != list(fields) else []
    return problems + [
        f"{where}.{key}: {type(record[key]).__name__}"
        for key, kind in fields.items()
        if key in record and not isinstance(record[key], kind)
    ]


def test_detail_matches_the_bootui_span_records(client: TestClient):
    child = span(TRACE_A, 2_000)
    child.context.span_id, child.parent = 8, SimpleNamespace(trace_id=TRACE_A, span_id=7)
    child.status = SimpleNamespace(status_code=SimpleNamespace(name="ERROR"), description="boom")
    child.events = [SimpleNamespace(name="exception", timestamp=2_500, attributes={"exception.type": "ValueError"})]
    otel.PROCESSOR.on_end(span(TRACE_A, 1_000))
    otel.PROCESSOR.on_end(child)
    detail = client.get(f"{API}/{TRACE_A:032x}").json()
    problems = _record_problems(detail, BOOTUI_TRACE_DETAIL, "detail")
    for i, s in enumerate(detail["spans"]):
        problems += _record_problems(s, BOOTUI_SPAN, f"spans[{i}]")
        for j, e in enumerate(s["events"]):
            problems += _record_problems(e, BOOTUI_SPAN_EVENT, f"spans[{i}].events[{j}]")
            problems += [p for a in e["attributes"] for p in _record_problems(a, BOOTUI_SPAN_ATTRIBUTE, "event attr")]
        problems += [p for a in s["attributes"] for p in _record_problems(a, BOOTUI_SPAN_ATTRIBUTE, "attribute")]
    assert len(detail["spans"]) == 2
    assert problems == []


def test_server_root_path_hides_sharpit_server_spans(provider: Provider):
    # review r1: behind ``--root-path /proxy`` the server span's path carries the prefix; sharpit learns it per request
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    url = "/proxy/sharpit/api/traces"
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), root_path="/proxy") as started:
        assert started.get(url).status_code == 200
        otel.PROCESSOR.on_end(span(TRACE_A, 1_000, path=url))
        body = started.get(url).json()
    assert body["traces"] == []
