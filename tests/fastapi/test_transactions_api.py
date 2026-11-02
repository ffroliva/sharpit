from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

LOCAL = ("127.0.0.1", 50000)


def test_transaction_route_reports_committed_sqlite_with_loopback_client() -> None:
    sa = pytest.importorskip("sqlalchemy")
    app = FastAPI()
    engine = sa.create_engine("sqlite://")
    handle = install(app, enabled="ON", show_banner=False, engines=[engine])
    try:
        with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
            with engine.begin():
                pass
            response = client.get("/sharpit/api/transactions")
        assert response.status_code == 200, "the implemented transactions panel must expose its GET report route"
        report = response.json()
        assert report["available"] is True, "an installed recorder must make the transactions report available"
        assert report["entries"][0]["status"] == "COMMITTED", "a SQLAlchemy commit must appear in the report"
    finally:
        handle.uninstall_capture()
        engine.dispose()


def _app(**options):
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, **options)
    return app, handle


def _client(app):
    return TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False)


def test_transactions_recording_controls_and_clear() -> None:
    app, handle = _app()
    try:
        with _client(app) as client:
            initial = client.get("/sharpit/api/transactions").json()
            paused = client.post("/sharpit/api/transactions/recording", json={"enabled": None}).json()
            resumed = client.post("/sharpit/api/transactions/recording", json={"enabled": True}).json()
            cleared = client.post("/sharpit/api/transactions/clear").json()
        assert initial["capturing"] is True, "recording must start enabled by default"
        assert paused["capturing"] is False, "missing or null enabled must toggle recording"
        assert resumed["capturing"] is True, "an explicit enabled value must set recording"
        assert cleared["bufferSize"] == 0, "clear must remove retained entries"
    finally:
        handle.uninstall_capture()


def test_transactions_unavailable_when_disabled() -> None:
    app, handle = _app(transactions_enabled=False)
    try:
        response = _client(app).get("/sharpit/api/transactions")
        assert response.status_code == 200, "a disabled transaction recorder must still return its report"
        assert response.json()["available"] is False, "transactions_enabled false must make the report unavailable"
    finally:
        handle.uninstall_capture()


def test_transactions_posts_are_blocked_by_global_read_only() -> None:
    app, handle = _app(read_only=True)
    try:
        response = _client(app).post("/sharpit/api/transactions/clear")
        assert response.status_code == 403, "read-only mode must reject transaction mutations"
    finally:
        handle.uninstall_capture()


def test_transactions_mcp_exposes_only_the_read_tool() -> None:
    app, handle = _app(mcp_enabled="ON")
    try:
        with _client(app) as client:
            listing = client.post("/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()[
                "result"
            ]["tools"]
            names = {tool["name"] for tool in listing}
            result = client.post(
                "/sharpit/api/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "get_transactions", "arguments": {}},
                },
            ).json()["result"]
        assert "get_transactions" in names, "MCP must expose the transactions read tool"
        assert "clear_transactions" not in names, "MCP must not expose the clear action"
        assert result["structuredContent"]["available"] is True, "the MCP read tool must return the cached report"
    finally:
        handle.uninstall_capture()
