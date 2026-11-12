"""W5a P-http: the capture middleware offers one ``http`` journal event per finished request (BootUI
``RequestCorrelationFilter.publish`` offers ``RuntimeEvent.of(JournalSource.HTTP, ..., HttpPayload)``)."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from fastapi import FastAPI, Request
from sharpit import install
from sharpit.engine.capture.exchanges import MAX_PATH
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.capture.traces import span_buffer
from sharpit.engine.collectors.insights.service import insights_service

ENVELOPE = {"source", "epochMillis", "durationNanos", "traceId", "thread", "requestId"}
PAYLOAD = {
    "method",
    "path",
    "routeTemplate",
    "operation",
    "status",
    "startNanos",
}  # startNanos: timing.startNanos, flat


def _world(**options: Any) -> tuple[TestClient, RuntimeJournal, Any]:
    app = FastAPI()

    @app.get("/api/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"id": item_id}

    @app.post("/api/echo")
    async def echo(request: Request) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"n": len(await request.body())}

    handle = install(app, enabled="ON", show_banner=False, config_scan=False, **options)
    journal = handle.context.capture.journal
    assert journal is not None
    return TestClient(app), journal, handle


def _one(journal: RuntimeJournal) -> dict[str, object]:
    records = journal.records("http")
    assert len(records) == 1
    return records[0]


# ported: RequestCorrelationFilterTests (the HttpPayload fields: method, path, routeTemplate, operation, status)
def test_http_journal_event_offered_once_per_request_with_bootui_fields() -> None:
    client, journal, _ = _world()
    assert client.get("/api/items/42").status_code == 200
    record = _one(journal)
    assert set(record) == ENVELOPE | PAYLOAD | {"route"}
    assert record["method"] == "GET"
    assert record["status"] == 200
    assert record["operation"] is None
    assert isinstance(record["requestId"], str)
    assert isinstance(record["epochMillis"], int)
    assert isinstance(record["durationNanos"], int)
    assert record["durationNanos"] >= 0  # type: ignore[operator]


def test_http_journal_event_request_id_is_the_exchange_id() -> None:
    client, journal, handle = _world()
    client.get("/api/items/42")
    exchanges = handle.context.capture.exchanges
    assert exchanges is not None
    (row,) = exchanges.rows()
    record = _one(journal)
    assert record["requestId"] == row["id"]
    assert row["traceId"] == row["id"]  # the exchanges row keeps its own fallback
    assert record["traceId"] is None  # BootUI's MDC trace id is null without tracing


def test_http_journal_event_trace_id_is_null_without_a_traceparent() -> None:
    client, journal, _ = _world()
    client.get("/api/items/1")
    assert _one(journal)["traceId"] is None


def test_http_journal_event_trace_id_is_the_traceparent_trace() -> None:
    client, journal, _ = _world()
    trace = "0af7651916cd43dd8448eb211c80319c"
    client.get("/api/items/1", headers={"traceparent": f"00-{trace}-b7ad6b7169203331-01"})
    assert _one(journal)["traceId"] == trace


def test_without_tracing_and_ai_outside_any_request_the_kind_is_not_applicable() -> None:
    client, journal, handle = _world()
    client.get("/api/items/1")
    journal.offer({"source": "ai", "operation": "chat", "traceId": None, "requestId": None})
    checks = insights_service(handle.context).report()["checks"]  # type: ignore[attr-defined]
    check = next(c for c in checks if c["kind"] == "ai-usage-by-route")
    assert check["status"] == "NOT_APPLICABLE"
    assert "Without tracing" in str(check["reason"])


# BootUI parity: HttpPayload.timing.startNanos, on the clock the sql event's completedNanos is read from
def test_http_journal_event_carries_the_monotonic_start_on_the_sql_clock() -> None:
    client, journal, _ = _world()
    before = time.perf_counter_ns()
    client.get("/api/items/1")
    after = time.perf_counter_ns()
    start = _one(journal).get("startNanos")
    assert start is not None
    assert isinstance(start, int)
    assert before <= start <= after


def test_http_journal_event_path_is_cut_like_the_exchange_row() -> None:
    client, journal, _ = _world()
    client.get("/x" * 3000)
    assert len(str(_one(journal)["path"])) <= MAX_PATH


def test_an_exchange_row_failure_does_not_lose_the_http_event(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("row")

    monkeypatch.setattr("sharpit.fastapi.capture.exchange_row", boom)
    client, journal, _ = _world()
    assert client.get("/api/items/1").status_code == 200
    assert _one(journal)["status"] == 200


# BootUI parity: HttpPayload.path carries path-parameter values; the journal masks a secret-shaped segment at read
def test_http_journal_event_path_canary_secret_segment_masked_plain_id_kept() -> None:
    canary = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0." + secrets.token_urlsafe(24)  # a JWT-shaped segment
    client, journal, _ = _world()
    client.get(f"/api/items/{canary}")
    client.get("/api/items/42")
    first, second = journal.records("http")
    assert canary not in repr(first)
    assert second["path"] == "/api/items/42"


def _boom_world() -> tuple[TestClient, RuntimeJournal]:
    app = FastAPI()

    @app.get("/boom")
    async def boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("boom")

    @app.get("/stream")
    async def stream() -> StreamingResponse:  # pyright: ignore[reportUnusedFunction]
        async def chunks() -> AsyncIterator[bytes]:
            yield b"a"
            yield b"b"

        return StreamingResponse(chunks(), background=BackgroundTask(lambda: None))

    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    journal = handle.context.capture.journal
    assert journal is not None
    return TestClient(app, raise_server_exceptions=False), journal


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [("GET", "/boom", 500), ("GET", "/stream", 200), ("HEAD", "/boom", 405)],
)
def test_one_http_event_per_request_whatever_the_outcome(method: str, path: str, status: int) -> None:
    client, journal = _boom_world()
    assert client.request(method, path).status_code == status
    assert _one(journal)["status"] == status


def test_a_client_disconnect_is_one_499_event() -> None:
    app = FastAPI()

    @app.get("/slow")
    async def slow() -> None:  # pyright: ignore[reportUnusedFunction]
        raise asyncio.CancelledError

    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    journal = handle.context.capture.journal
    assert journal is not None

    async def call() -> None:
        scope = {"type": "http", "method": "GET", "path": "/slow", "raw_path": b"/slow", "query_string": b"",
                 "headers": [], "scheme": "http", "server": ("t", 80), "client": ("c", 1), "root_path": ""}  # fmt: skip

        async def receive() -> dict[str, str]:
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            return None

        with contextlib.suppress(asyncio.CancelledError):
            await app(scope, receive, send)  # pyright: ignore[reportArgumentType]

    asyncio.run(call())
    assert _one(journal)["status"] == 499


def test_http_journal_event_route_is_the_template_label() -> None:
    client, journal, _ = _world()
    client.get("/api/items/9f3a")
    record = _one(journal)
    assert record["routeTemplate"] == "/api/items/{item_id}"
    assert record["route"] == "GET /api/items/{item_id}"
    assert "9f3a" not in str(record["route"])


def test_http_journal_event_without_a_template_carries_the_masked_path_label() -> None:
    client, journal, _ = _world()
    client.get("/nowhere/0123456789abcdef0123")
    record = _one(journal)
    assert record["routeTemplate"] is None
    assert "0123456789abcdef0123" not in str(record["route"])
    assert str(record["route"]).startswith("GET /nowhere/")


def test_http_journal_event_not_offered_for_sharpit_routes() -> None:
    client, journal, _ = _world()
    client.get("/sharpit/api/overview")
    client.get("/api/items/1")  # the control: the producer runs, and only this request is offered
    assert [r["method"] for r in journal.records("http")] == ["GET"]
    assert _one(journal)["routeTemplate"] == "/api/items/{item_id}"
    assert journal.status()["dropped"].get("http", 0) == 0


def test_http_journal_event_not_offered_when_source_disabled() -> None:
    client, journal, _ = _world(runtime_journal_sources=("ai",))
    assert client.get("/api/items/1").status_code == 200
    assert journal.records("http") == ()
    assert journal.status()["dropped"].get("http") == 1  # counted, never raised


def test_http_journal_event_not_offered_when_journal_disabled() -> None:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    handle = install(app, enabled="ON", show_banner=False, config_scan=False, runtime_journal_enabled=False)
    assert TestClient(app).get("/ping").status_code == 200  # no journal: the request is untouched, nothing raised
    assert handle.context.capture.journal is None


@pytest.mark.parametrize("exposure", ["MASKED", "FULL"])
def test_http_journal_event_canary_never_reaches_the_journal(exposure: str) -> None:
    canary = secrets.token_hex(16)
    client, journal, _ = _world(expose_values=exposure)
    client.post(
        "/api/echo?token=" + canary + "&q=" + canary,
        content=canary.encode(),
        headers={"Authorization": f"Bearer {canary}", "X-Canary": canary, "Cookie": f"sid={canary}"},
    )
    assert journal.records("http")
    assert canary not in repr(journal.records("http"))
    assert "remoteAddress" not in journal.records("http")[0]


def test_http_is_a_recorded_source_only_when_enabled() -> None:
    from sharpit.engine.collectors.insights import snapshot as snapshot_module
    from sharpit.engine.collectors.insights.snapshot import project

    assert "http" in snapshot_module.PRODUCED_SOURCES
    on = RuntimeJournal(sources=("http", "ai"))
    off = RuntimeJournal(sources=("ai",))
    assert project(on).recorded("http")
    assert not project(off).recorded("http")


def test_ai_operation_in_a_real_request_is_joined_by_request_id() -> None:
    app = FastAPI()
    holder: dict[str, Any] = {}

    @app.get("/api/assistant")
    async def assistant() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        span = SimpleNamespace(
            context=SimpleNamespace(trace_id=7, span_id=9),
            kind=SimpleNamespace(name="INTERNAL"),
            name="chat",
            start_time=0,
            end_time=40_000_000,
            status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET")),
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "openai",
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 10,
                "gen_ai.usage.output_tokens": 5,
            },
        )
        span_buffer(holder["ctx"]).add(span)  # a span ended inside the request, as the SDK processor delivers it
        return {"ok": True}

    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    holder["ctx"] = handle.context
    journal = handle.context.capture.journal
    assert journal is not None
    assert TestClient(app).get("/api/assistant").status_code == 200
    http = _one(journal)
    (ai,) = journal.records("ai")
    assert ai["requestId"] == http["requestId"]
    coverage = {c["source"]: c for c in insights_service(handle.context).report()["coverage"]}  # type: ignore[attr-defined]
    assert coverage["ai"]["byRequestId"] == 1
