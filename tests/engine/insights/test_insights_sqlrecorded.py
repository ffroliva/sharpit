"""Whether this context records SQL at all (BootUI ``SqlCapture.of`` + ``SqlTraceRecorder.hasWrappedDataSource``,
v2.3.0): one per-context fact, read by the insights, the SQL Trace panel reasons and ``sqlastats``.

BootUI's fact is known at WRAP time (a DataSource is registered), not when a statement first runs: the SQLAlchemy
analogue is an engine attached to the context, and raw sqlite3 (no wrap-time object) is a statement delivered to it."""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from typing import Any

import pytest

import sqlalchemy as sa
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.collectors import sqlastats
from sharpit.engine.collectors.insights import sqlcapture
from sharpit.engine.collectors.insights.service import insights_service
from sharpit.fastapi.capture import HOOK_SQLA_LISTENERS, HOOK_SQLITE_LISTENERS

pytestmark = pytest.mark.needs_sqlalchemy
NOT_RECORDED = sqlcapture.NOT_RECORDED
_HTTP = {"source": "http", "requestId": "r1", "status": 200, "route": "GET /a", "routeTemplate": "/a"}
UNSUPPORTED = "SQLAlchemy 1.4.0 is imported, but sharpit needs 2.0 or later"


@pytest.fixture
def handles() -> Iterator[list[Any]]:
    opened: list[Any] = []
    yield opened
    for handle in opened:
        handle.uninstall_capture()


@pytest.fixture
def no_sqlalchemy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sqlalchemy", None)  # the application never imports SQLAlchemy


def _install(handles: list[Any], **options: Any) -> Any:
    sqla.detach_all()
    handle = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False, **options)
    handles.append(handle)
    return handle.context


def _engine() -> sa.Engine:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(sa.text("create table t (n int)"))
    return engine


def _raw_sqlite() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("select 1").fetchall()
    conn.close()


def _dml_check(ctx: Any) -> dict[str, Any]:
    journal = ctx.capture.journal
    for i in range(3):
        assert journal.offer({**_HTTP, "requestId": f"r{i}"})
    return next(c for c in insights_service(ctx).report()["checks"] if c["kind"] == "safe-method-dml")


# ported: RuntimeInsightsServiceTests.sqlCaptureNamesWhyStatementsAreNotRecorded (SqlCapture.of(recorder, true, false))
# finding 1: no SQLAlchemy and no sqlite3 use is NOT_RECORDED; release answered EVALUATED over nothing
def test_an_app_with_no_database_at_all_reads_not_recorded(handles: list[Any], no_sqlalchemy: None) -> None:
    ctx = _install(handles)
    check = _dml_check(ctx)
    assert check["status"] == "UNAVAILABLE"
    assert check["reason"] == NOT_RECORDED


# finding 2: SQLAlchemy imported, no engine attached, no DB
def test_sqlalchemy_imported_with_no_engine_reads_not_recorded(handles: list[Any]) -> None:
    ctx = _install(handles, sql_trace_sqlite3_enabled=False)
    check = _dml_check(ctx)
    assert check["status"] == "UNAVAILABLE"
    assert check["reason"] == NOT_RECORDED


# the wrap-time fact: an engine attached to THIS context is a recorded database before its first statement
def test_an_attached_engine_is_recorded_before_any_statement(handles: list[Any]) -> None:
    ctx = _install(handles, engines=[_engine()], sql_trace_sqlite3_enabled=False)
    capture = sqlcapture.for_context(ctx)
    assert capture.recorded
    assert capture.reason is None


# finding 6: SQLAlchemy imported late, its engine never attached here: the fact follows the recorded events
def test_an_engine_created_after_install_is_recorded_only_when_its_statements_are(handles: list[Any]) -> None:
    ctx = _install(handles, sql_trace_sqlite3_enabled=False)
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(sa.text("update t set n = 1"))
    recorded_events = ctx.capture.sql_trace.rows()
    assert sqlcapture.for_context(ctx).recorded == bool(recorded_events)


# finding 7: an idle raw-sqlite3 app is not recorded until its first statement reaches this context
def test_an_idle_raw_sqlite_app_reads_not_recorded_until_the_first_statement(
    handles: list[Any], no_sqlalchemy: None
) -> None:
    ctx = _install(handles)
    assert sqlcapture.for_context(ctx).reason == NOT_RECORDED
    _raw_sqlite()
    assert sqlcapture.for_context(ctx).recorded


# finding 5: raw sqlite3 outside any request reaches no context when two are installed; neither is recorded
def test_a_raw_sqlite_statement_no_context_received_leaves_both_not_recorded(
    handles: list[Any], no_sqlalchemy: None
) -> None:
    first, second = _install(handles), _install(handles)
    _raw_sqlite()
    assert sqlcapture.for_context(first).reason == NOT_RECORDED
    assert sqlcapture.for_context(second).reason == NOT_RECORDED


def test_the_raw_sqlite_fact_does_not_move_the_application_family_evidence(
    handles: list[Any], no_sqlalchemy: None
) -> None:
    ctx = _install(handles)
    _raw_sqlite()
    assert ctx.capture.raw_sqlite_seen  # application_family still reads it; the recorded fact is its own field
    assert ctx.capture.sqlite3_delivered


def _both_used(handles: list[Any]) -> Any:
    ctx = _install(handles, engines=[_engine()])
    _raw_sqlite()
    assert sqlcapture.for_context(ctx).reason is None
    return ctx


# finding 3: one hook detached, the other still recording: recorded, naming what is missed
def test_the_sqlalchemy_hook_suspended_is_recorded_except_sqlalchemy(handles: list[Any]) -> None:
    ctx = _both_used(handles)
    ctx.capture.wiring.suspend_hook(HOOK_SQLA_LISTENERS)
    capture = sqlcapture.for_context(ctx)
    assert capture.recorded
    assert "SQLAlchemy" in str(capture.reason)


# finding 4: only the sqlite3 hook suspended
def test_the_sqlite_hook_suspended_is_recorded_except_sqlite3(handles: list[Any]) -> None:
    ctx = _both_used(handles)
    ctx.capture.wiring.suspend_hook(HOOK_SQLITE_LISTENERS)
    capture = sqlcapture.for_context(ctx)
    assert capture.recorded
    assert "sqlite3" in str(capture.reason)


# finding 8: report-time state, not window-time: events were recorded, then both hooks are detached
def test_both_hooks_suspended_after_events_is_not_recorded_with_a_check_unavailable(handles: list[Any]) -> None:
    ctx = _both_used(handles)
    ctx.capture.wiring.suspend_hook(HOOK_SQLA_LISTENERS)
    ctx.capture.wiring.suspend_hook(HOOK_SQLITE_LISTENERS)
    assert not sqlcapture.for_context(ctx).recorded
    assert _dml_check(ctx)["status"] == "UNAVAILABLE"


def test_a_partly_suspended_capture_keeps_the_caveat_on_a_check_that_reads_sql(handles: list[Any]) -> None:
    ctx = _both_used(handles)
    ctx.capture.wiring.suspend_hook(HOOK_SQLA_LISTENERS)
    check = _dml_check(ctx)
    assert check["status"] != "UNAVAILABLE"
    assert "SQLAlchemy" in str(check["reason"])


# finding 9: SQLAlchemy older than 2.0 beside raw sqlite3: what is missed is said, and it is not "neither is in use"
def test_an_unsupported_sqlalchemy_beside_sqlite3_names_the_version_it_cannot_record(
    handles: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sa, "__version__", "1.4.0")
    ctx = _install(handles)
    _raw_sqlite()
    capture = sqlcapture.for_context(ctx)
    assert capture.recorded
    assert UNSUPPORTED in str(capture.reason)


def test_an_unsupported_sqlalchemy_and_no_sqlite3_is_not_recorded_and_names_the_version(
    handles: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sa, "__version__", "1.4.0")
    ctx = _install(handles)
    capture = sqlcapture.for_context(ctx)
    assert not capture.recorded
    assert UNSUPPORTED in str(capture.reason)


# finding 10: the sql-trace panel off with the flag on does not blame the flag, and composes with the panel's own text
def test_the_panel_off_with_the_flag_on_does_not_name_the_flag(handles: list[Any]) -> None:
    ctx = _install(handles, panels={"sql-trace": {"enabled": False}})
    capture = sqlcapture.for_context(ctx)
    assert not capture.recorded
    assert "SHARPIT_SQL_TRACE_ENABLED" not in str(capture.reason)
    assert "sql-trace panel" in str(capture.reason)


def test_the_flag_off_still_names_the_flag(handles: list[Any]) -> None:
    ctx = _install(handles, sql_trace_enabled=False)
    assert "SHARPIT_SQL_TRACE_ENABLED=false" in str(sqlcapture.for_context(ctx).reason)


# one fact, read by every surface that answers "is SQL recorded"
def test_the_panel_reason_and_sqlastats_agree_with_the_insights_fact(handles: list[Any], no_sqlalchemy: None) -> None:
    ctx = _install(handles)
    assert sqlcapture.for_context(ctx).reason == NOT_RECORDED
    assert sqla.sql_trace_unavailable_reason(ctx) == NOT_RECORDED
    assert sqlastats.statistics_report(ctx)["unavailableReason"] == NOT_RECORDED
    _raw_sqlite()
    assert sqla.sql_trace_unavailable_reason(ctx) is None
