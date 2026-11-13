"""``SqlCapture`` follows what this context actually records: BootUI ``SqlCapture.of(recorder, tracedRequired, r2dbc)``
with ``recorder.hasWrappedDataSource()`` (v2.3.0). A process-wide patch nothing uses is no recorded database."""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.insights.service import insights_service
from sharpit.engine.collectors.insights.sqlcapture import NOT_RECORDED, SqlCapture
from sharpit.fastapi.capture import HOOK_SQLA_LISTENERS, HOOK_SQLITE_LISTENERS

pytestmark = pytest.mark.needs_sqlalchemy

_SQL = {"source": "sql", "sql": "select ?", "requestId": "r1"}
_HTTP = {"source": "http", "requestId": "r1", "status": 200, "route": "GET /a", "routeTemplate": "/a", "method": "GET"}


@pytest.fixture
def handles() -> Iterator[list[Any]]:
    opened: list[Any] = []
    yield opened
    for handle in opened:
        handle.uninstall_capture()


def _install(handles: list[Any], app: FastAPI | None = None, **options: Any) -> Any:
    handle = install(
        app or FastAPI(), enabled="ON", show_banner=False, config_scan=False,
        runtime_journal_sources=("http", "sql"), **options,
    )  # fmt: skip
    handles.append(handle)
    return handle


def _app_with_engine() -> tuple[FastAPI, sa.Engine]:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(sa.text("create table t (n int)"))
    app = FastAPI()

    @app.get("/w")
    def write() -> dict[str, int]:
        with engine.begin() as conn:
            conn.execute(sa.text("update t set n = n + 1"))
        return {"ok": 1}

    return app, engine


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def _check(ctx: Any, kind: str) -> dict[str, Any]:
    journal = ctx.capture.journal
    assert journal.offer(_HTTP)
    assert journal.offer(_SQL)
    return next(c for c in insights_service(ctx).report()["checks"] if c["kind"] == kind)


# ported: RuntimeInsightsServiceTests.sqlCaptureNamesWhyStatementsAreNotRecorded (SqlCapture.of(null, true, false))
# ported: RuntimeInsightsServiceTests.checksThatReadSqlAreUnavailableWhereThisApplicationsSqlIsNotRecorded
# ported: RuntimeInsightsControllerTests.sqlChecksAreUnavailableOnSpringMvcAndWebFluxWhenNoDataSourceIsTraced (servlet)
def test_the_process_wide_sqlite3_patch_alone_is_not_a_recorded_database(
    handles: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "sqlalchemy", None)  # the app never imports SQLAlchemy and opens no sqlite3
    ctx = _install(handles).context
    assert insights_service(ctx).sql_capture() == SqlCapture.not_recorded()
    check = _check(ctx, "safe-method-dml")
    assert check["status"] == "UNAVAILABLE"
    assert check["reason"] == NOT_RECORDED


# ported: RuntimeInsightsServiceTests.sqlCaptureNamesWhyStatementsAreNotRecorded (SqlCapture.of(wrapped, true, false))
# ported: RuntimeInsightsControllerTests.sqlChecksAreUnavailableOnSpringMvcAndWebFluxWhenNoDataSourceIsTraced (traced)
def test_an_attached_engine_is_capturing_and_a_sql_check_is_evaluated_over_no_work_not_unavailable(
    handles: list[Any],
) -> None:
    app, engine = _app_with_engine()
    ctx = _install(handles, app, engines=[engine]).context
    assert _client(app).get("/w").status_code == 200  # the first request attaches the listeners
    assert insights_service(ctx).sql_capture() == SqlCapture.capturing()
    check = next(c for c in insights_service(ctx).report()["checks"] if c["kind"] == "safe-method-dml")
    assert check["status"] != "UNAVAILABLE"
    assert "not recorded" not in str(check["reason"])
    assert "SQL capture" not in str(check["reason"])


def test_suspended_sql_hooks_are_not_recorded_and_the_reason_says_so(handles: list[Any]) -> None:
    app, engine = _app_with_engine()
    ctx = _install(handles, app, engines=[engine]).context
    client = _client(app)
    assert client.get("/w").status_code == 200
    wiring = ctx.capture.wiring
    wiring.suspend_hook(HOOK_SQLA_LISTENERS)
    wiring.suspend_hook(HOOK_SQLITE_LISTENERS)
    capture = insights_service(ctx).sql_capture()
    assert not capture.recorded
    assert "suspended" in str(capture.reason)
    check = _check(ctx, "safe-method-dml")
    assert check["status"] == "UNAVAILABLE"
    assert "suspended" in str(check["reason"])


def test_resuming_the_hooks_records_again(handles: list[Any]) -> None:
    app, engine = _app_with_engine()
    ctx = _install(handles, app, engines=[engine]).context
    assert _client(app).get("/w").status_code == 200
    wiring = ctx.capture.wiring
    wiring.suspend_hook(HOOK_SQLA_LISTENERS)
    wiring.resume_hook(HOOK_SQLA_LISTENERS)
    assert insights_service(ctx).sql_capture() == SqlCapture.capturing()


def test_sqlalchemy_imported_after_the_listeners_were_due_is_not_capturing(
    handles: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = sys.modules["sqlalchemy"]
    monkeypatch.setitem(sys.modules, "sqlalchemy", None)  # not imported while install and startup attach
    ctx = _install(handles, sql_trace_sqlite3_enabled=False).context
    monkeypatch.setitem(sys.modules, "sqlalchemy", real)  # imported later: nothing attaches its listeners
    assert insights_service(ctx).sql_capture() == SqlCapture.not_recorded()


def test_an_unsupported_sqlalchemy_keeps_its_specific_reason(
    handles: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sa, "__version__", "1.4.50")
    ctx = _install(handles, sql_trace_sqlite3_enabled=False).context
    capture = insights_service(ctx).sql_capture()
    assert not capture.recorded
    assert capture.reason == "SQLAlchemy 1.4.50 is imported, but sharpit needs 2.0 or later"


# ported: RuntimeInsightsServiceTests.sqlCaptureNamesWhyStatementsAreNotRecorded (SqlCapture.of(wrapped, true, true))
def test_raw_sqlite3_in_use_beside_an_unsupported_sqlalchemy_is_recorded_except_that_library(
    handles: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sa, "__version__", "1.4.50")
    ctx = _install(handles).context
    sqlite3.connect(":memory:").execute("select 1").fetchall()  # raw sqlite3, outside any request
    assert ctx.capture.raw_sqlite_seen
    capture = insights_service(ctx).sql_capture()
    assert capture.recorded
    assert "SQLAlchemy 1.4.50" in str(capture.reason)
    assert "only raw sqlite3 statements are counted" in str(capture.reason)
