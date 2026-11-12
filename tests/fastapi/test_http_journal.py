"""W5a P-http: the capture middleware offers one ``http`` journal event per finished request (BootUI
``RequestCorrelationFilter.publish`` offers ``RuntimeEvent.of(JournalSource.HTTP, ..., HttpPayload)``)."""

from __future__ import annotations

import secrets
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI, Request
from sharpit import install
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.capture.traces import span_buffer
from sharpit.engine.collectors.insights.service import insights_service

ENVELOPE = {"source", "epochMillis", "durationNanos", "traceId", "thread", "requestId"}
PAYLOAD = {"method", "path", "routeTemplate", "operation", "status"}


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
    assert record["traceId"] == row["traceId"]


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
