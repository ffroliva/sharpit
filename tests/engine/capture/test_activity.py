"""Live Activity and the request profile (F4, spec §7.4): a read-time merge of F1-F3.

Ported from BootUI ``LiveActivityAssembler`` (severities, summaries, percentiles, typeCounts before filtering),
``LiveActivityService`` (``since``/``type``/``severity`` filters, ``effectiveLimit``, ``perMinute``) and
``RequestProfileAssembler`` / ``SqlTraceGrouping`` (profile timing and per-request groups). Correlation is by
sharpit's request id (spec §9) instead of BootUI's trace id.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from sharpit.engine import sqla
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture.activity import (
    ENTRY_KEYS,
    EVICTED,
    KPI_KEYS,
    PROFILE_KEYS,
    REPORT_KEYS,
    activity_report,
    request_profile,
)
from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.capture.exchanges import DTO_KEYS, HttpExchangeBuffer, exchange_row
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.settings import load_settings


@pytest.fixture(autouse=True)
def _sqlalchemy_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorder is fed directly here; SQL Trace is a source only while SQLAlchemy is imported (§7.4)."""
    monkeypatch.setattr(sqla, "unavailable_reason", lambda: None)


ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
HEADER = [(b"x-demo", b"1")]


class _Introspector:
    def app_info(self) -> AppInfo:
        return AppInfo("demo", "FastAPI", "0.115.0", None)

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return []


def _ctx(*, sql: bool = True, exceptions: bool = True, **options: Any) -> SharpitContext:
    settings = load_settings({"config_scan": False, **options}, {})
    ctx = SharpitContext(settings, ACTIVATION, _Introspector())
    capture = ctx.capture
    capture.exchanges = HttpExchangeBuffer(200)
    if exceptions:
        capture.exceptions = ExceptionStore(100, 25, 50, ctx.masker)
    if sql:
        capture.sql_trace = SqlTraceRecorder(ctx.masker, slow_query_threshold_millis=100)
    return ctx


def _request(
    ctx: SharpitContext, rid: str, *, status: int = 200, duration_ms: int = 5, ago_ms: int = 1000, path: str = "/x"
) -> None:
    started = time.time_ns() - ago_ms * 1_000_000
    assert ctx.capture.exchanges is not None
    ctx.capture.exchanges.add(
        exchange_row(
            ctx.masker,
            request_id=rid,
            started_epoch_ns=started,
            method="GET",
            path=path,
            query_string=b"",
            status=status,
            duration_ms=duration_ms,
            size=0,
            client=None,
            user=None,
            request_headers=HEADER,
            response_headers=HEADER,
            finished_epoch_ns=started + duration_ms * 1_000_000,
        )
    )


def _sql(ctx: SharpitContext, rid: str | None, sql: str = "select * from pets where id = 1", **kw: Any) -> None:
    assert ctx.capture.sql_trace is not None
    fields: dict[str, Any] = {"duration_ns": 2_000_000, "thread": "t", "connection_id": None, **kw}
    ctx.capture.sql_trace.record(sql, request_id=rid, **fields)


def _raise(ctx: SharpitContext, rid: str | None) -> None:
    from sharpit.engine.capture.correlation import RequestInfo

    assert ctx.capture.exceptions is not None
    info = RequestInfo(rid, "c", "GET", "/x", "app:x", 0, None) if rid else None
    try:
        raise ValueError("boom")
    except ValueError as exc:
        ctx.capture.exceptions.record(exc, "request", info, "t")


def _report(ctx: SharpitContext, **kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {"type": None, "severity": None, "since": None, "limit": None, "q": None, **kw}
    return activity_report(ctx, **args)


def test_merge_ordered_by_time():
    ctx = _ctx()
    _request(ctx, "r1", ago_ms=50)
    time.sleep(0.002)
    _sql(ctx, "r1")
    time.sleep(0.002)
    _raise(ctx, "r1")
    report = _report(ctx)
    assert tuple(report) == REPORT_KEYS
    assert [e["type"] for e in report["entries"]] == ["EXCEPTION", "SQL", "REQUEST"]
    stamps = [e["timestamp"] for e in report["entries"]]
    assert stamps == sorted(stamps, reverse=True)
    assert report["typeCounts"] == {"EXCEPTION": 1, "SQL": 1, "REQUEST": 1}
    assert (report["pageInfo"], report["persistenceOption"]) == (None, None)
    assert report["sources"] == ["requests", "exceptions", "sql"]


def test_parent_id_on_sql_and_exception_rows():
    ctx = _ctx()
    _request(ctx, "r1")
    _sql(ctx, "r1")
    _sql(ctx, "gone")  # its request is not in the buffer: no parent to nest under
    _raise(ctx, "r1")
    by_type: dict[str, list[dict[str, Any]]] = {}
    for entry in _report(ctx)["entries"]:
        by_type.setdefault(entry["type"], []).append(entry)
    request = by_type["REQUEST"][0]
    assert (request["id"], request["correlationId"], request["parentId"], request["profileable"]) == (
        "r1",
        "r1",
        None,
        True,
    )
    assert sorted((e["correlationId"], e["parentId"]) for e in by_type["SQL"]) == [("gone", None), ("r1", "r1")]
    exception = by_type["EXCEPTION"][0]
    assert (exception["parentId"], exception["correlationId"], exception["profileable"]) == ("r1", "r1", False)
    assert exception["id"].startswith("exc-") and all(e["id"].startswith("sql-") for e in by_type["SQL"])


def test_n_plus_one_flags_request_and_group():
    ctx = _ctx(activity_n_plus_one_threshold=3)
    _request(ctx, "r1")
    _request(ctx, "r2")
    for n in range(3):
        _sql(ctx, "r1", f"select * from owners where id = {n}", call_site="app:list_pets:12")
    for n in range(2):
        _sql(ctx, "r2", f"select * from owners where id = {n}")
    for n in range(3):
        _sql(ctx, "r2", f"update owners set seen = {n}")  # not a SELECT: never N+1
    flags = {e["id"]: e["sqlNPlusOneSuspected"] for e in _report(ctx)["entries"] if e["type"] == "REQUEST"}
    assert flags == {"r1": True, "r2": False}
    groups = request_profile(ctx, "r1")["sqlGroups"]
    assert [(g["sql"], g["executions"], g["potentialNPlusOne"], g["callSites"]) for g in groups] == [
        ("select * from owners where id = ?", 3, True, ["app:list_pets:12"])
    ]
    other = request_profile(ctx, "r2")["sqlGroups"]
    assert [(g["category"], g["executions"], g["potentialNPlusOne"]) for g in other] == [
        ("UPDATE", 3, False),
        ("SELECT", 2, False),
    ]


@pytest.mark.parametrize(
    ("status", "duration_ms", "expected"),
    [(503, 5, "ERROR"), (500, 5000, "ERROR"), (404, 5000, "WARN"), (200, 1000, "SLOW"), (200, 999, "OK")],
)
def test_severity_rules_requests(status: int, duration_ms: int, expected: str):
    ctx = _ctx()
    _request(ctx, "r1", status=status, duration_ms=duration_ms)
    assert _report(ctx)["entries"][0]["severity"] == expected


def test_severity_rules():
    # ported: LiveActivityAssembler.toSqlEntry / toExceptionEntry / requestSeverity
    ctx = _ctx()
    _sql(ctx, None, "select 1", duration_ns=150_000_000)  # slow (threshold 100 ms)
    _sql(ctx, None, "select 2")
    _sql(ctx, None, "select 3", error=RuntimeError("no such table"), success=False)
    _raise(ctx, None)
    entries = _report(ctx)["entries"]
    assert sorted((e["type"], e["severity"]) for e in entries) == [
        ("EXCEPTION", "ERROR"),
        ("SQL", "ERROR"),
        ("SQL", "OK"),
        ("SQL", "SLOW"),
    ]
    failed = next(e for e in entries if e["type"] == "SQL" and e["severity"] == "ERROR")
    assert (failed["summary"], failed["detail"]) == ("select ?", "no such table")
    exception = next(e for e in entries if e["type"] == "EXCEPTION")
    assert exception["summary"] == "ValueError: boom"


def test_limit_zero_means_cap():
    ctx = _ctx(activity_max_entries=3)
    for n in range(5):
        _request(ctx, f"r{n}", ago_ms=100 - n)
    assert len(_report(ctx, limit=0)["entries"]) == 3
    assert len(_report(ctx, limit=None)["entries"]) == 3
    assert len(_report(ctx, limit=2)["entries"]) == 2
    assert len(_report(ctx, limit=50)["entries"]) == 3
    assert _report(ctx, limit=2)["typeCounts"] == {"REQUEST": 5}  # counted before the cap, as BootUI


def test_since_type_severity_and_q_filters():
    ctx = _ctx()
    _request(ctx, "old", ago_ms=5000, path="/pets")
    _request(ctx, "new", ago_ms=10, status=500, path="/owners")
    _sql(ctx, "new", "select * from owners")
    entries = _report(ctx)["entries"]
    old_ts = next(e["timestamp"] for e in entries if e["id"] == "old")
    assert [e["id"] for e in _report(ctx, since=old_ts)["entries"] if e["type"] == "REQUEST"] == ["new"]
    assert {e["type"] for e in _report(ctx, type="sql")["entries"]} == {"SQL"}
    assert [e["id"] for e in _report(ctx, severity="error")["entries"]] == ["new"]
    assert [e["id"] for e in _report(ctx, q="PETS")["entries"]] == ["old"]


def test_until_cursor_ignored():
    # BootUI's until/cursor/pageSize belong to persistence; sharpit's signature has no such parameters
    import inspect

    assert set(inspect.signature(activity_report).parameters) == {"ctx", "type", "severity", "since", "limit", "q"}


def test_kpis_p50_p95_and_nulls():
    ctx = _ctx()
    for n, duration in enumerate([10, 20, 30, 40, 1000]):
        _request(ctx, f"r{n}", duration_ms=duration, status=500 if n == 0 else 200, path=f"/p{n}")
    _sql(ctx, "r1", duration_ns=7_000_000)
    _raise(ctx, "r1")
    kpis = _report(ctx)["kpis"]
    assert tuple(kpis) == KPI_KEYS
    assert (kpis["p50LatencyMs"], kpis["p95LatencyMs"]) == (30, 1000)
    assert (kpis["slowestEndpoint"], kpis["slowestEndpointMs"]) == ("/p4", 1000)
    assert (kpis["errorRatePercent"], kpis["activeExceptionCount"], kpis["slowestQueryMs"]) == (20.0, 1, 7)
    assert kpis["healthStatus"] is None
    nulls = (
        "heapUsedBytes",
        "heapMaxBytes",
        "cacheHitRatioPercent",
        "restCallErrorRatePercent",
        "restCallP95LatencyMs",
    )
    assert all(kpis[k] is None for k in nulls) and kpis["scheduledTaskFailureCount"] == 0
    empty = _report(_ctx())["kpis"]
    assert (empty["requestsPerMinute"], empty["p50LatencyMs"], empty["slowestQueryMs"]) == (0.0, None, None)


def test_active_exception_count_counts_open_groups_only():
    ctx = _ctx()
    _raise(ctx, None)
    store = ctx.capture.exceptions
    assert store is not None
    store.set_status(store.report()["groups"][0]["id"], "RESOLVED")
    assert _report(ctx)["kpis"]["activeExceptionCount"] == 0


def test_background_task_sql_approximate():
    ctx = _ctx()
    _request(ctx, "r1", ago_ms=1000, duration_ms=5)  # finished a second ago
    _sql(ctx, "r1")  # recorded now, after the response went out: a BackgroundTasks statement
    profile = request_profile(ctx, "r1")
    assert profile["sqlCorrelationApproximate"] is True
    assert any("after the response" in n for n in profile["notes"])
    ctx2 = _ctx()
    _request(ctx2, "r1", ago_ms=0, duration_ms=60_000)  # still running when the statement finished
    _sql(ctx2, "r1")
    assert request_profile(ctx2, "r1")["sqlCorrelationApproximate"] is False


def test_request_profile_timing_and_exceptions():
    ctx = _ctx()
    _request(ctx, "r1", duration_ms=10, ago_ms=0)
    _sql(ctx, "r1", duration_ns=4_000_000)
    _sql(ctx, "other")
    _raise(ctx, "r1")
    profile = request_profile(ctx, "r1")
    assert tuple(profile) == PROFILE_KEYS
    assert (profile["available"], profile["unavailableReason"], profile["trace"], profile["security"]) == (
        True,
        None,
        None,
        [],
    )
    assert tuple(profile["request"]) == DTO_KEYS and profile["request"]["requestHeaders"]
    assert len(profile["sql"]) == 1 and profile["sql"][0]["traceId"] == "r1"
    assert profile["timing"] == {"totalMs": 10, "sqlMs": 4, "sqlCount": 1, "sqlPercent": 40.0}
    assert [(e["exceptionClassName"], e["source"]) for e in profile["exceptions"]] == [("ValueError", "request")]
    assert tuple(profile["exceptions"][0]) == (
        "exceptionClassName", "message", "location", "timestamp", "thread", "handler", "source",
    )  # fmt: skip


def test_evicted_request_profile():
    ctx = _ctx()
    profile = request_profile(ctx, "nope")
    assert tuple(profile) == PROFILE_KEYS
    assert (profile["available"], profile["unavailableReason"]) == (False, EVICTED)
    assert EVICTED == "Request is no longer in the buffer"
    assert (profile["request"], profile["sql"], profile["timing"], profile["notes"]) == (None, [], None, [])


def test_sql_source_off_without_sqlalchemy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sqla, "unavailable_reason", lambda: sqla.UNAVAILABLE)
    ctx = _ctx()
    report = _report(ctx)
    assert "sql" not in report["sources"] and report["warnings"] == [f"SQL: {sqla.UNAVAILABLE}"]


def test_disabled_sql_trace_no_sql_rows():
    ctx = _ctx(sql=False)
    _request(ctx, "r1")
    report = _report(ctx)
    assert "SQL" not in report["typeCounts"] and "sql" not in report["sources"]
    profile = request_profile(ctx, "r1")
    assert (profile["sql"], profile["sqlGroups"]) == ([], [])


def test_disabled_exceptions_no_exception_rows():
    ctx = _ctx(exceptions=False)
    _request(ctx, "r1")
    report = _report(ctx)
    assert "EXCEPTION" not in report["typeCounts"] and "exceptions" not in report["sources"]
    assert report["kpis"]["activeExceptionCount"] == 0
    assert request_profile(ctx, "r1")["exceptions"] == []


def test_disabled_http_exchanges_no_headers():
    ctx = _ctx(panels={"http-exchanges": {"enabled": False}})
    _request(ctx, "r1")
    assert [e["type"] for e in _report(ctx)["entries"]] == ["REQUEST"]
    request = request_profile(ctx, "r1")["request"]
    assert (request["requestHeaders"], request["responseHeaders"]) == ([], [])


def test_shape_keys_match_bootui():
    # ActivityEntryDto, ActivityKpiDto, LiveActivityReport and RequestProfileDto record components, in order
    assert ENTRY_KEYS == (
        "id", "type", "timestamp", "severity", "summary", "detail", "durationMs", "correlationId", "method", "path",
        "status", "thread", "profileable", "parentId", "securedPrincipal", "sqlNPlusOneSuspected",
    )  # fmt: skip
    assert KPI_KEYS == (
        "requestsPerMinute", "errorRatePercent", "p50LatencyMs", "p95LatencyMs", "slowestEndpoint",
        "slowestEndpointMs", "activeExceptionCount", "sqlPerMinute", "slowestQueryMs", "healthStatus",
        "heapUsedBytes", "heapMaxBytes", "cacheHitRatioPercent", "scheduledTaskFailureCount",
        "restCallErrorRatePercent", "restCallP95LatencyMs",
    )  # fmt: skip
    assert REPORT_KEYS == (
        "available", "entries", "typeCounts", "kpis", "sources", "warnings", "pageInfo", "persistenceOption",
    )  # fmt: skip
    assert PROFILE_KEYS == (
        "available", "unavailableReason", "request", "sql", "sqlGroups", "sqlCorrelationApproximate", "exceptions",
        "security", "trace", "timing", "notes",
    )  # fmt: skip
    ctx = _ctx()
    _request(ctx, "r1")
    _sql(ctx, "r1")
    _raise(ctx, "r1")
    assert all(tuple(e) == ENTRY_KEYS for e in _report(ctx)["entries"])


def test_fan_in_forwards_source_ticks():
    target = ChangeStream()
    source = ChangeStream()
    source.forward_to(target)
    seen: list[int] = []
    target.signal = lambda: seen.append(1)  # type: ignore[method-assign]
    source.signal()  # nobody subscribes to the source: the tick still reaches the fan-in
    assert seen == [1]
