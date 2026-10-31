"""Live Activity endpoints, ``get_live_activity`` and the activity tick stream end to end (F4, spec §7.4, §13.2).

Derived cases: BootUI's oracle for the merge itself is ported in ``tests/engine/capture/test_activity.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import OpenStream, SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.activity import EVICTED, REPORT_KEYS
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import CAPTURE_TOO_LATE_REASON

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/activity"
_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _app(**options: Any) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()

    @app.get("/pets")
    def pets() -> list[str]:  # pyright: ignore[reportUnusedFunction]
        return ["rex"]

    @app.get("/boom")
    def boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("boom")

    handle = install(app, **{"enabled": "ON", "show_banner": False, "stream_max_seconds": 0.05, **options})
    _HANDLES.append(handle)
    return app, handle


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False)


def _rpc(client: TestClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return client.post("/sharpit/api/mcp", json=call).json()["result"]


def test_activity_feed_and_profile():
    app, _ = _app()
    client = _client(app)
    client.get("/pets")
    client.get("/boom")
    report = client.get(API).json()
    assert tuple(report) == REPORT_KEYS
    assert report["available"] is True
    requests = [e for e in report["entries"] if e["type"] == "REQUEST"]
    assert [(e["path"], e["status"], e["severity"]) for e in requests] == [
        ("/boom", 500, "ERROR"),
        ("/pets", 200, "OK"),
    ]
    exception = next(e for e in report["entries"] if e["type"] == "EXCEPTION")
    assert exception["parentId"] == requests[0]["id"]
    profile = client.get(f"{API}/request/{requests[0]['id']}").json()
    assert profile["available"] is True
    assert profile["request"]["path"] == "/boom"
    assert [e["exceptionClassName"] for e in profile["exceptions"]] == ["RuntimeError"]
    assert client.get(f"{API}/request/0123456789abcdef").json()["unavailableReason"] == EVICTED
    assert [e["type"] for e in client.get(API, params={"type": "REQUEST", "limit": 1}).json()["entries"]] == ["REQUEST"]


def test_activity_available_in_panels():
    app, _ = _app(panels={p: {"enabled": False} for p in ("http-exchanges", "exceptions", "sql-trace")})
    panel = next(p for p in _client(app).get("/sharpit/api/panels").json()["panels"] if p["id"] == "activity")
    assert (panel["available"], panel["unavailableReason"]) == (True, None)  # the middleware is the source (§13.1)


def test_activity_unavailable_when_installed_too_late():
    late = FastAPI()
    late.get("/host")(lambda: {})
    client = _client(late)
    assert client.get("/host").status_code == 200  # the middleware stack is built now
    _HANDLES.append(install(late, enabled="ON", show_banner=False, panels={"sql-trace": {"enabled": False}}))
    panel = next(p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "activity")
    assert (panel["available"], panel["unavailableReason"]) == (False, CAPTURE_TOO_LATE_REASON)
    assert client.get(API).json()["available"] is False


def test_disabled_sql_trace_no_sql_rows():
    app, handle = _app(panels={"sql-trace": {"enabled": False}}, mcp_enabled="ON")
    assert handle.context.capture.sql_trace is None
    client = _client(app)
    client.get("/pets")
    for report in (client.get(API).json(), _rpc(client, "get_live_activity", {})["structuredContent"]):
        assert "sql" not in report["sources"]
        assert "SQL" not in report["typeCounts"]


def test_disabled_exceptions_no_exception_rows():
    app, _ = _app(panels={"exceptions": {"enabled": False}}, mcp_enabled="ON")
    client = _client(app)
    client.get("/boom")
    for report in (client.get(API).json(), _rpc(client, "get_live_activity", {})["structuredContent"]):
        assert "exceptions" not in report["sources"]
        assert "EXCEPTION" not in report["typeCounts"]
        assert [e["status"] for e in report["entries"]] == [500]


def test_disabled_http_exchanges_no_headers():
    app, _ = _app(panels={"http-exchanges": {"enabled": False}}, mcp_enabled="ON")
    client = _client(app)
    client.get("/pets", headers={"x-demo": "1"})
    assert client.get("/sharpit/api/http-exchanges").status_code == 403  # the panel's own route stays closed
    report = _rpc(client, "get_live_activity", {"limit": 5})["structuredContent"]
    rid = report["entries"][0]["id"]
    request = client.get(f"{API}/request/{rid}").json()["request"]
    assert (request["path"], request["requestHeaders"], request["responseHeaders"]) == ("/pets", [], [])


@pytest.mark.needs_sqlalchemy
def test_activity_alone_attaches_no_sql_listeners():
    pytest.importorskip("sqlalchemy")
    from sharpit.engine import sqla

    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    disabled = ("http-exchanges", "exceptions", "sql-trace")
    _app(panels={p: {"enabled": False} for p in disabled})
    attached = sqla.attached()
    assert not any(attached[e] for e in sqla.STATEMENT_EVENTS)


def test_new_request_ticks_activity_stream():
    app, _ = _app(stream_max_seconds=30)

    async def main() -> str:
        stream = OpenStream(app, f"{API}/stream")
        await asyncio.wait_for(stream.started.wait(), 5)
        await asyncio.sleep(0.05)  # subscribed
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": "/pets", "raw_path": b"/pets", "root_path": "", "query_string": b"",
            "headers": [(b"host", b"localhost")], "client": LOCAL, "server": ("localhost", 80),
        }  # fmt: skip
        await app(scope, receive, send)
        for _ in range(50):
            if "event: update" in stream.body:
                break
            await asyncio.sleep(0.02)
        stream.task.cancel()
        await asyncio.gather(stream.task, return_exceptions=True)
        return stream.body

    assert "event: update" in asyncio.run(main())


def test_get_live_activity_mcp_no_side_effects(no_side_effects: SideEffectGuard):
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        client.get("/owners")
        no_side_effects.block_network()
        result = _rpc(client, "get_live_activity", {"limit": 10})
    assert result["isError"] is False
    assert [e["path"] for e in result["structuredContent"]["entries"] if e["type"] == "REQUEST"] == ["/owners"]
    assert no_side_effects.violations == []
