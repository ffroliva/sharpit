"""SQL capture state in the runtime insights: RuntimeInsightsService.java:975-1008 (v2.3.0) with SqlCapture.DISABLED.
The flag off, or the sql-trace panel off, is not a panel being unavailable: a check that needs SQL is UNAVAILABLE and an
optional SQL read is a caveat. Whether a database is in use at all is tested in test_insights_sqlrecorded.py."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from tests.engine.insights.test_insights_k1 import Run

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.finding import Evaluation
from sharpit.engine.collectors.insights.service import InsightsService, insights_service
from sharpit.engine.collectors.insights.sqlcapture import PANEL_OFF, SqlCapture

SQL_OFF = "SQL capture is disabled (SHARPIT_SQL_TRACE_ENABLED=false), so no statement is recorded."
CAVEAT = f"{SQL_OFF} Its SQL and connection evidence is not counted."
_HTTP = {"source": "http", "requestId": "r1", "status": 200, "route": "GET /a", "routeTemplate": "/a"}
_SQL = {"source": "sql", "sql": "select ?", "requestId": "r1"}


@pytest.fixture
def handles() -> Iterator[list[Any]]:
    opened: list[Any] = []
    yield opened
    for handle in opened:
        handle.uninstall_capture()


def _report(handles: list[Any], events: list[dict[str, Any]], **options: Any) -> dict[str, Any]:
    handle = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False, **options)
    handles.append(handle)
    for event in events:
        assert handle.context.capture.journal.offer(event)
    return insights_service(handle.context).report()


def _check(report: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(c for c in report["checks"] if c["kind"] == kind)


# ported: RuntimeInsightsServiceTests.checksThatReadSqlAreUnavailableWhereThisApplicationsSqlIsNotRecorded
# ported: RuntimeInsightsControllerTests.sqlChecksAreUnavailableOnSpringMvcAndWebFluxWhenNoDataSourceIsTraced (disabled)
def test_a_required_sql_check_with_sql_capture_off_is_unavailable_with_the_capture_reason(handles: list[Any]) -> None:
    check = _check(_report(handles, [_SQL], sql_trace_enabled=False), "safe-method-dml")
    assert check["status"] == "UNAVAILABLE"
    assert check["reason"] == SQL_OFF


# ported: RuntimeInsightsServiceTests.sqlCaptureNamesWhyStatementsAreNotRecorded (SqlCapture.of(disabled, true, false))
def test_an_optional_sql_read_with_sql_capture_off_is_a_caveat_with_the_not_counted_suffix(handles: list[Any]) -> None:
    check = _check(_report(handles, [_HTTP, _SQL], sql_trace_enabled=False), "route-time-breakdown")
    assert check["status"] != "UNAVAILABLE"
    assert CAVEAT in str(check["reason"])


# ported: RuntimeInsightsService.java:975-980 (a disabled panel is reported before the capture state)
def test_the_disabled_panel_wins_over_the_capture_reason(handles: list[Any]) -> None:
    report = _report(handles, [_SQL], sql_trace_enabled=False, panels={"sql-trace": {"enabled": False}})
    check = _check(report, "safe-method-dml")
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == "The sql-trace panel, whose evidence this reads, is disabled."


# ported: BootUiAutoConfiguration.bootUiSqlTraceRecorder (v2.3.0:803): enabled = sqlTrace.isEnabled() && panel enabled
def test_the_sql_trace_panel_off_with_the_flag_on_is_sql_capture_disabled(handles: list[Any]) -> None:
    report = _report(handles, [_HTTP, _SQL], panels={"sql-trace": {"enabled": False}})
    assert f"{PANEL_OFF} Its SQL and connection evidence is not counted." in str(
        _check(report, "route-time-breakdown")["reason"]
    )


# ported: RuntimeInsightsServiceTests.checksThatReadSqlAreUnavailableWhereThisApplicationsSqlIsNotRecorded
# (report.observations[].limitations contain the reason, RuntimeInsightsServiceTests.java:1030-1037)
def test_an_observation_row_carries_the_capture_caveat_in_its_limitations() -> None:
    run = Run(sql_trace_enabled=False)
    try:
        for _ in range(6):
            run.request("GET /api/orders", 30)
        rows = [o for o in insights_service(run.ctx).report()["observations"] if o["kind"] == "route-time-breakdown"]
    finally:
        run.close()
    assert rows
    assert all(CAVEAT in row["limitations"] for row in rows)


def test_no_caveat_when_the_journal_does_not_record_sql_at_all() -> None:
    run = Run(sources=("http",), sql_trace_enabled=False)  # BootUI gates the caveat on snapshot.records(SQL)
    try:
        check = next(c for c in insights_service(run.ctx).report()["checks"] if c["kind"] == "route-time-breakdown")
    finally:
        run.close()
    assert "SQL capture" not in str(check["reason"])


def test_a_supplier_that_returns_nothing_is_capturing(handles: list[Any]) -> None:
    handle = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False)
    handles.append(handle)
    assert handle.context.capture.journal.offer(_SQL)
    service = InsightsService(handle.context.capture.journal, None, 5, None, cast(Any, lambda: None))
    check = next(c for c in service.report()["checks"] if c["kind"] == "safe-method-dml")
    assert check["status"] != "UNAVAILABLE"
    assert check["reason"] is None or "SQL" not in str(check["reason"])


def test_a_check_that_reads_only_connection_evidence_is_unavailable_with_sql_capture_off(
    handles: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        snapshot_module, "PRODUCED_SOURCES", frozenset(snapshot_module.PRODUCED_SOURCES | {"connection"})
    )
    handle = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False, sql_trace_enabled=False)
    handles.append(handle)
    kind = SimpleNamespace(
        kind="conn-only", title="t", minimum_tier="TIME_WINDOW", reads=frozenset({"connection"}),
        optional_reads=frozenset(), uses_requests=False, evaluate=lambda _snapshot: Evaluation(0),
    )  # fmt: skip
    report = InsightsService(
        handle.context.capture.journal, [kind], 5, None, lambda: SqlCapture.not_recorded(SQL_OFF)
    ).report()
    assert report["checks"][0]["status"] == "UNAVAILABLE"
