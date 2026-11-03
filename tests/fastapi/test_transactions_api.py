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


# ported: TransactionsControllerSupportTests.traceReportsUnavailableWhenRecorderIsAbsent
def test_transactions_capture_when_sql_trace_is_disabled() -> None:
    sa = pytest.importorskip("sqlalchemy")
    app = FastAPI()
    engine = sa.create_engine("sqlite://")
    handle = install(app, enabled="ON", show_banner=False, engines=[engine], sql_trace_enabled=False)
    try:
        with engine.begin():
            pass
        report = handle.context.capture.transactions.report(None)
        assert report["totalCaptured"] == 1, "transactions must capture connection events while SQL Trace is off"
    finally:
        handle.uninstall_capture()
        engine.dispose()


def test_real_sqlite_savepoint_rollback_then_outer_commit() -> None:
    sa = pytest.importorskip("sqlalchemy")
    app = FastAPI()
    engine = sa.create_engine("sqlite://")
    handle = install(app, enabled="ON", show_banner=False, engines=[engine])
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            nested = connection.begin_nested()
            nested.rollback()
            outer.commit()
        report = handle.context.capture.transactions.report(None)
        rows = report["entries"]
        outer_row = next(row for row in rows if row["parentId"] is None)
        child_row = next(row for row in rows if row["parentId"] is not None)
        assert child_row["propagation"] == "PARTICIPATING", "a savepoint must be a participating transaction"
        assert report["stats"]["nestedCount"] == 1, "a rolled-back savepoint must count as one nested transaction"
        assert child_row["status"] == "ROLLED_BACK", "rolling back a savepoint must close the child as rolled back"
        assert outer_row["status"] == "COMMITTED", "the outer transaction must still commit after savepoint rollback"
    finally:
        handle.uninstall_capture()
        engine.dispose()


def _app(**options):
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, **options)
    return app, handle


def _client(app):
    return TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False)


# ported: TransactionsControllerSupportTests.recordingTogglesWhenNoExplicitValueIsGiven
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
        assert cleared["bufferSize"] == 200, "clear must preserve the configured transaction ring capacity"
    finally:
        handle.uninstall_capture()


# ported: TransactionsControllerSupportTests.traceReportsUnavailableWhenRecorderIsDisabled
def test_transactions_unavailable_when_disabled() -> None:
    app, handle = _app(transactions_enabled=False)
    try:
        response = _client(app).get("/sharpit/api/transactions")
        assert response.status_code == 200, "a disabled transaction recorder must still return its report"
        assert response.json()["available"] is False, "transactions_enabled false must make the report unavailable"
    finally:
        handle.uninstall_capture()


def test_transactions_alone_does_not_install_capture_middleware() -> None:
    from sharpit.fastapi.capture import CaptureMiddleware

    app = FastAPI()
    disabled = {panel: {"enabled": False} for panel in ("http-exchanges", "exceptions", "sql-trace", "activity")}
    handle = install(app, enabled="ON", show_banner=False, panels=disabled)
    try:
        classes = {entry.cls for entry in app.user_middleware}
        assert CaptureMiddleware not in classes, "transactions alone must not add request capture middleware"
    finally:
        handle.uninstall_capture()


def test_transactions_posts_are_blocked_by_global_read_only() -> None:
    app, handle = _app(read_only=True)
    try:
        response = _client(app).post("/sharpit/api/transactions/clear")
        assert response.status_code == 403, "read-only mode must reject transaction mutations"
    finally:
        handle.uninstall_capture()


def test_transactions_posts_are_blocked_by_panel_read_only() -> None:
    app, handle = _app(panels={"transactions": {"read_only": True}})
    try:
        response = _client(app).post("/sharpit/api/transactions/clear")
        assert response.status_code == 403, "transactions panel read-only must reject its action routes"
    finally:
        handle.uninstall_capture()


def test_recording_post_recursion_error_returns_400() -> None:
    app, handle = _app()
    deep_json = b'{"enabled":' + b"[" * 5000 + b"true" + b"]" * 5000 + b"}"
    try:
        response = _client(app).post("/sharpit/api/transactions/recording", content=deep_json)
        assert response.status_code == 400, "a recursively nested toggle body must be rejected with 400"
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


def test_uninstall_capture_removes_listeners() -> None:
    from sharpit.engine.capture.transactions import (
        tx_begin,
        tx_commit,
        tx_release_savepoint,
        tx_rollback,
        tx_rollback_savepoint,
        tx_savepoint,
    )

    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://")
    callbacks = {
        "begin": tx_begin,
        "commit": tx_commit,
        "rollback": tx_rollback,
        "savepoint": tx_savepoint,
        "rollback_savepoint": tx_rollback_savepoint,
        "release_savepoint": tx_release_savepoint,
    }
    before = {event: sa.event.contains(sa.engine.Engine, event, callback) for event, callback in callbacks.items()}
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    try:
        after_install = {
            event: sa.event.contains(sa.engine.Engine, event, callback) for event, callback in callbacks.items()
        }
        assert all(after_install.values()), "install must attach every transaction connection event"
        handle.uninstall_capture()
        after_uninstall = {
            event: sa.event.contains(sa.engine.Engine, event, callback) for event, callback in callbacks.items()
        }
        assert after_uninstall == before, "uninstall must restore the transaction listener state"
    finally:
        handle.uninstall_capture()
        engine.dispose()


@pytest.mark.asyncio
async def test_async_engine_transaction_recorded() -> None:
    pytest.importorskip("aiosqlite")
    from sqlalchemy.ext.asyncio import create_async_engine

    app = FastAPI()
    engine = create_async_engine("sqlite+aiosqlite://")
    handle = install(app, enabled="ON", show_banner=False, engines=[engine])
    try:
        async with engine.begin():
            pass
        with _client(app) as client:
            report = client.get("/sharpit/api/transactions").json()
        assert report["totalCaptured"] == 1, "AsyncEngine connection events must be captured through its sync engine"
        assert report["entries"][0]["status"] == "COMMITTED", "an async commit must close the transaction entry"
    finally:
        handle.uninstall_capture()
        await engine.dispose()


def test_transactions_capture_with_sql_trace_and_discovery_off() -> None:
    import gc

    sa = pytest.importorskip("sqlalchemy")
    from sharpit.engine import sqla
    from sharpit.engine.panels import PANELS

    implemented = {panel.id for panel in PANELS if panel.implemented}
    panels = {panel: {"enabled": False} for panel in sqla.DISCOVERY_PANELS if panel in implemented}
    gc.collect()  # drop contexts other tests left behind, so this app is the only one
    engine = sa.create_engine("sqlite://")
    handle = install(FastAPI(), enabled="ON", show_banner=False, sql_trace_enabled=False, panels=panels)
    try:
        with engine.begin():
            pass
        report = handle.context.capture.transactions.report(None)
    finally:
        handle.uninstall_capture()
        engine.dispose()
    assert report["totalCaptured"] == 1, "the only installed context must capture with SQL Trace and discovery off"


def test_report_golden_parity() -> None:
    from tests.golden import assert_parity

    sa = pytest.importorskip("sqlalchemy")
    app = FastAPI()
    engine = sa.create_engine("sqlite://")
    handle = install(app, enabled="ON", show_banner=False, engines=[engine])
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            connection.begin_nested().commit()
            outer.commit()
        with _client(app) as client:
            body = client.get("/sharpit/api/transactions").json()
    finally:
        handle.uninstall_capture()
        engine.dispose()
    assert_parity("transactions", "captured", body)
