"""``sqlalchemy-statistics`` collector (lane A-sqlalchemy-statistics, Task 3).

Ported from BootUI ``HibernateStatisticsServiceTests``; the Hibernate counters SQLAlchemy cannot measure are ``None``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine import panels, sqla
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture.exchanges import HttpExchangeBuffer, exchange_row
from sharpit.engine.capture.sqltrace import SqlTraceRecorder, normalize
from sharpit.engine.collectors import sqlastats
from sharpit.engine.collectors.sqlastats import (
    CACHE_COUNT_KEYS,
    NULL_KEYS,
    NULL_REASON,
    RECORDING_PAUSED,
    REPORT_KEYS,
    STATISTICS_KEYS,
    n_plus_one,
    statistics_report,
)
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.settings import load_settings

ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
SELECT = "select * from pets where owner_id = {}"
STRIPE_KEY = "sk_live_4eC39HqLyjWDarjtT1zdp7dc"


@pytest.fixture(autouse=True)
def _sqlalchemy_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sqla, "unavailable_reason", lambda: None)


class _Introspector:
    def app_info(self) -> AppInfo:
        return AppInfo("demo", "FastAPI", "0.115.0", None)

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return []


def _ctx(*, sql: bool = True, exchanges: bool = True, **options: Any) -> SharpitContext:
    settings = load_settings({"config_scan": False, **options}, {})
    ctx = SharpitContext(settings, ACTIVATION, _Introspector())
    if exchanges:
        ctx.capture.exchanges = HttpExchangeBuffer(200)
    if sql:
        ctx.capture.sql_trace = SqlTraceRecorder(
            ctx.masker, max_entries=settings.sql_trace_max_entries, n_plus_one_threshold=5
        )
    return ctx


def _request(ctx: SharpitContext, rid: str, *, method: str = "GET", endpoint: str | None = "app:list_pets") -> None:
    assert ctx.capture.exchanges is not None
    ctx.capture.exchanges.add(
        exchange_row(
            ctx.masker,
            request_id=rid,
            started_epoch_ns=time.time_ns(),
            method=method,
            path="/pets",
            query_string=b"",
            status=200,
            duration_ms=5,
            size=0,
            client=None,
            user=None,
            request_headers=[],
            response_headers=[],
            endpoint=endpoint,
        )
    )


def _sql(ctx: SharpitContext, sql: str, rid: str | None = None, millis: int = 2) -> None:
    assert ctx.capture.sql_trace is not None
    ctx.capture.sql_trace.record(sql, duration_ns=millis * 1_000_000, thread="t", connection_id=None, request_id=rid)


def _stats(ctx: SharpitContext) -> dict[str, Any]:
    return statistics_report(ctx)["statistics"]


def _only(ctx: SharpitContext) -> dict[str, Any]:
    entries = _stats(ctx)["nPlusOne"]
    assert len(entries) == 1
    return entries[0]


def _burst(ctx: SharpitContext, rid: str | None, count: int) -> None:
    for i in range(count):
        _sql(ctx, SELECT.format(i), rid)


def test_maps_totals_onto_dto():
    # ported: HibernateStatisticsServiceTests.mapsSnapshotOntoDtoWhenAvailableAndEnabled
    ctx = _ctx()
    _sql(ctx, "select 1", millis=4)
    _sql(ctx, "select 2", millis=9)
    _sql(ctx, "delete from t")
    report = statistics_report(ctx)
    stats = report["statistics"]
    assert tuple(report) == REPORT_KEYS
    assert report["available"] is True
    assert report["enableAvailable"] is False
    assert report["unavailableReason"] is None
    assert set(stats) == set(STATISTICS_KEYS)
    assert stats["queryExecutionCount"] == 2
    assert stats["statementCount"] == 3
    assert stats["queryExecutionMaxTime"] == 9
    assert stats["queryExecutionMaxTimeQueryString"] == "select ?"


def test_unmeasurable_counters_are_null():
    stats = _stats(_ctx())
    assert [key for key in NULL_KEYS if stats[key] is not None] == []
    assert NULL_REASON.startswith("SQLAlchemy reports SQL statements")


def test_cache_is_off_and_counts_zero():
    stats = _stats(_ctx())
    assert stats["queryCacheEnabled"] is False
    assert stats["secondLevelCacheEnabled"] is False
    assert stats["secondLevelCacheRegions"] == []
    assert [key for key in CACHE_COUNT_KEYS if stats[key] != 0] == []


def test_unavailable_without_recorder():
    # ported: HibernateStatisticsServiceTests.reportsUnavailableWhenNoProvider
    report = statistics_report(_ctx(sql=False))
    assert report["available"] is False
    assert report["unavailableReason"] == sqla.TRACING_DISABLED
    assert set(report["statistics"]) == set(STATISTICS_KEYS)


def test_unavailable_when_tracing_off():
    # ported: HibernateStatisticsServiceTests.reportsUnavailableWhenStatisticsDisabled
    report = statistics_report(_ctx(sql_trace_enabled=False))
    assert report["available"] is False
    assert report["unavailableReason"] == sqla.TRACING_DISABLED


def test_unavailable_mirrors_sqlalchemy_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sqla, "unavailable_reason", lambda: "SQLAlchemy not imported")
    assert statistics_report(_ctx())["unavailableReason"] == "SQLAlchemy not imported"


def test_n_plus_one_per_route():
    ctx = _ctx()
    _request(ctx, "r1")
    _burst(ctx, "r1", 6)
    entry = _only(ctx)
    assert entry["method"] == "GET"
    assert entry["route"] == "app:list_pets"
    assert entry["sql"] == "select * from pets where owner_id = ?"
    assert entry["requests"] == 1
    assert entry["executionsPerRequest"] == 6
    assert entry["threshold"] == 5


def test_n_plus_one_merges_requests_of_a_route():
    ctx = _ctx()
    _request(ctx, "r1")
    _request(ctx, "r2")
    _burst(ctx, "r1", 6)
    _burst(ctx, "r2", 8)
    entry = _only(ctx)
    assert entry["requests"] == 2
    assert entry["executionsPerRequest"] == 8


def test_below_threshold_is_not_n_plus_one():
    ctx = _ctx()
    _request(ctx, "r1")
    _burst(ctx, "r1", 4)
    assert _stats(ctx)["nPlusOne"] == []


def test_only_selects_count_towards_n_plus_one():
    ctx = _ctx()
    _request(ctx, "r1")
    for i in range(7):
        _sql(ctx, f"update pets set name = 'a' where id = {i}", "r1")
    assert _stats(ctx)["nPlusOne"] == []


def test_n_plus_one_is_capped():
    rows = [
        {"traceId": f"r{i}", "category": "SELECT", "sql": f"select {'c' * i} from t where x = {n}"}
        for i in range(1, 26)
        for n in range(5)
    ]
    entries = n_plus_one(rows, lambda _rid: ("GET", "/x"), 5)
    assert len(entries) == 20


def test_max_time_query_is_normalised():
    ctx = _ctx(sql_trace_capture_parameters=True)
    _sql(ctx, f"select * from pay where key = '{STRIPE_KEY}'", millis=50)
    assert STRIPE_KEY not in str(statistics_report(ctx))


def test_n_plus_one_never_holds_a_literal_with_parameter_capture():
    ctx = _ctx(sql_trace_capture_parameters=True)
    _request(ctx, "r1")
    for i in range(6):
        _sql(ctx, f"select * from pay where key = '{STRIPE_KEY}{i}'", "r1")
    entry = _only(ctx)
    assert STRIPE_KEY not in entry["sql"]
    assert entry["executionsPerRequest"] == 6


def test_counts_are_lifetime_n_plus_one_is_window():
    ctx = _ctx()
    _request(ctx, "r1")
    _burst(ctx, "r1", 500)
    stats = _stats(ctx)
    assert stats["queryExecutionCount"] == 500
    assert stats["statementCount"] == 500
    assert stats["nPlusOneWindow"] == "retained SQL Trace window (200 statements)"
    assert stats["nPlusOne"][0]["executionsPerRequest"] == 200


def test_uncorrelated_statements_not_in_n_plus_one():
    ctx = _ctx()
    _burst(ctx, None, 9)
    stats = _stats(ctx)
    assert stats["nPlusOne"] == []
    assert stats["queryExecutionCount"] == 9


def test_route_unknown_when_exchange_gone():
    ctx = _ctx()
    _burst(ctx, "gone", 6)
    entry = _only(ctx)
    assert entry["method"] is None
    assert entry["route"] is None
    assert entry["routeReason"]
    assert entry["executionsPerRequest"] == 6


def test_route_unknown_when_exchanges_disabled():
    ctx = _ctx(exchanges=False)
    _burst(ctx, "r1", 6)
    entry = _only(ctx)
    assert entry["route"] is None
    assert "HTTP Exchanges" in entry["routeReason"]


NULLABLE = Path(__file__).parents[1] / "fixtures/bootui/2.2.0/sqlalchemy-statistics/nullable.json"


def test_n_plus_one_carries_the_request_path():
    # review A-sqlalchemy-statistics #2: HTTP Exchanges filters on the path, never on the endpoint name
    ctx = _ctx()
    _request(ctx, "r1")
    _burst(ctx, "r1", 6)
    assert _only(ctx).get("routePath") == "/pets"


def test_long_statements_with_varying_literals_are_one_shape():
    # review #3: group by the recorder's fingerprint, never re-normalise truncated raw rows
    ctx = _ctx(exchanges=False, sql_trace_capture_parameters=True)
    ctx.capture.sql_trace = SqlTraceRecorder(ctx.masker, max_sql_length=60)
    for i in range(6):
        _sql(ctx, f"select * from pets where name = '{'x' * i}' and owner_id = 1 and species = 'cat'", "r1")
    assert len(_stats(ctx)["nPlusOne"]) == 1


def test_get_does_not_normalize(monkeypatch: pytest.MonkeyPatch):
    ctx = _ctx()
    _request(ctx, "r1")
    _burst(ctx, "r1", 6)
    calls: list[str] = []

    def spy(sql: str) -> Any:
        calls.append(sql)
        return normalize(sql)

    monkeypatch.setattr(sqlastats, "normalize", spy, raising=False)
    statistics_report(ctx)
    assert calls == []


def test_route_lookup_does_not_scan_per_group(monkeypatch: pytest.MonkeyPatch):
    # review #4: one {id: row} index per report, no HttpExchangeBuffer.get scan per N+1 group
    ctx = _ctx()
    _request(ctx, "r1")
    _burst(ctx, "r1", 6)
    calls: list[str] = []
    real_get = HttpExchangeBuffer.get

    def spy(self: HttpExchangeBuffer, rid: str) -> Any:
        calls.append(rid)
        return real_get(self, rid)

    monkeypatch.setattr(HttpExchangeBuffer, "get", spy)
    statistics_report(ctx)
    assert calls == []


def test_unavailable_when_sql_trace_panel_disabled():
    # review #5: the panel switch, not SHARPIT_SQL_TRACE_ENABLED, is why there is no recorder
    settings = load_settings({"config_scan": False}, {"SHARPIT_PANELS_SQL_TRACE_ENABLED": "false"})
    ctx = SharpitContext(settings, ACTIVATION, _Introspector())
    assert statistics_report(ctx)["unavailableReason"] == panels.disabled_reason("sql-trace")


def test_paused_recording_is_a_warning():
    # review #6: counters freeze while SQL Trace recording is paused
    ctx = _ctx()
    assert ctx.capture.sql_trace is not None
    ctx.capture.sql_trace.set_recording(False)
    assert _stats(ctx).get("warnings") == [RECORDING_PAUSED]


def test_paused_recording_stays_available():
    ctx = _ctx()
    assert ctx.capture.sql_trace is not None
    ctx.capture.sql_trace.set_recording(False)
    assert statistics_report(ctx)["available"] is True


def test_null_reason_matches_nullable_json():
    # review #8: one reason text for the DTO, nullable.json and the view
    reasons = set(json.loads(NULLABLE.read_text(encoding="utf-8")).values())
    assert reasons == {NULL_REASON}


def test_n_plus_one_is_capped_from_the_recorder():
    # supersedes test_n_plus_one_is_capped (fed hand-built rows the recorder never stores)
    ctx = _ctx()
    ctx.capture.sql_trace = SqlTraceRecorder(ctx.masker, max_entries=500)
    _request(ctx, "r1")
    for i in range(1, 26):
        for n in range(5):
            _sql(ctx, f"select {'c' * i} from t where x = {n}", "r1")
    assert len(_stats(ctx)["nPlusOne"]) == 20
