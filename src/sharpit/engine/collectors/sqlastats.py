"""``sqlalchemy-statistics`` (BootUI ``hibernate-statistics``): SQL recorder lifetime totals plus N+1 per route."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sharpit.engine import panels, sqla
from sharpit.engine.capture.sqltrace import SqlTotals
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import Masker

NULL_REASON = (
    "SQLAlchemy reports SQL statements, not ORM session or entity operations "
    "(transactions live in the transactions panel)"
)
NULL_KEYS: tuple[str, ...] = (
    "sessionOpenCount",
    "sessionCloseCount",
    "flushCount",
    "connectCount",
    "transactionCount",
    "successfulTransactionCount",
    "entityLoadCount",
    "entityFetchCount",
    "entityInsertCount",
    "entityUpdateCount",
    "entityDeleteCount",
    "collectionLoadCount",
    "collectionFetchCount",
    "collectionRecreateCount",
    "collectionUpdateCount",
    "collectionRemoveCount",
)
CACHE_COUNT_KEYS: tuple[str, ...] = (
    "queryCacheHitCount",
    "queryCacheMissCount",
    "queryCachePutCount",
    "secondLevelCacheHitCount",
    "secondLevelCacheMissCount",
    "secondLevelCachePutCount",
)
STATISTICS_KEYS: tuple[str, ...] = (
    *NULL_KEYS,
    "queryExecutionCount",
    "queryExecutionMaxTime",
    "queryExecutionMaxTimeQueryString",
    "queryCacheEnabled",
    *CACHE_COUNT_KEYS[:3],
    "secondLevelCacheEnabled",
    *CACHE_COUNT_KEYS[3:],
    "secondLevelCacheRegions",
    "statementCount",
    "nPlusOne",
    "nPlusOneWindow",
    "warnings",
)
REPORT_KEYS = ("available", "enableAvailable", "unavailableReason", "statistics")


MAX_N_PLUS_ONE = 20
RECORDING_PAUSED = "SQL Trace recording is paused: these counters are frozen until it resumes."
ROUTE_UNKNOWN = "No HTTP Exchanges row for this request (HTTP Exchanges disabled, or the row was evicted)"


def n_plus_one(
    rows: list[dict[str, Any]], exchanges: Mapping[str, dict[str, Any]], threshold: int, masker: Masker
) -> list[dict[str, Any]]:
    """BootUI's per-statement rule per request: a request running one SELECT shape ``threshold`` times is one hit.

    Groups by the fingerprint the recorder stored at capture time: the stored ``sql`` may be raw and truncated."""
    counts: dict[tuple[str, str], int] = {}  # (request, fingerprint) -> executions
    shapes: dict[str, str] = {}  # fingerprint -> normalised sql (unmasked until output)
    for row in rows:
        request_id = row["traceId"]
        if request_id is None or row["category"] != "SELECT":
            continue
        shape = row["shape"]
        key = (request_id, shape.fingerprint)
        counts[key] = counts.get(key, 0) + 1
        shapes[shape.fingerprint] = shape.sql
    merged: dict[tuple[str | None, str | None, str], dict[str, Any]] = {}
    for (request_id, fingerprint), count in counts.items():
        if count < threshold:
            continue
        exchange = exchanges.get(request_id)
        method = exchange["method"] if exchange is not None else None
        route = (exchange["endpoint"] or exchange["path"]) if exchange is not None else None
        entry = merged.setdefault(
            (method, route, fingerprint),
            {
                "method": method,
                "route": route,
                "routePath": exchange["path"] if exchange is not None else None,  # what HTTP Exchanges filters on
                "routeReason": None if exchange is not None else ROUTE_UNKNOWN,
                "sql": masker.mask_text(shapes[fingerprint]),
                "executionsPerRequest": 0,
                "requests": 0,
                "threshold": threshold,
            },
        )
        entry["requests"] += 1
        entry["executionsPerRequest"] = max(entry["executionsPerRequest"], count)
    ranked = sorted(merged.values(), key=lambda e: (-e["executionsPerRequest"], e["sql"] or ""))
    return ranked[:MAX_N_PLUS_ONE]


def _unavailable_reason(ctx: SharpitContext) -> str | None:
    if not ctx.settings.panels["sql-trace"].enabled:
        return panels.disabled_reason("sql-trace")
    reason = sqla.sql_trace_unavailable_reason(ctx)
    return reason if reason is not None or ctx.capture.sql_trace is not None else sqla.TRACING_DISABLED


def statistics_report(ctx: SharpitContext) -> dict[str, Any]:
    recorder = ctx.capture.sql_trace
    reason = _unavailable_reason(ctx)
    totals = recorder.totals() if recorder is not None else SqlTotals(0, 0, 0, None)
    rows = recorder.rows() if recorder is not None else []
    exchanges = {row["id"]: row for row in ctx.capture.exchanges.rows()} if ctx.capture.exchanges is not None else {}
    statistics: dict[str, Any] = dict.fromkeys(NULL_KEYS)
    statistics.update(
        queryExecutionCount=totals.selects,
        queryExecutionMaxTime=totals.max_millis,
        queryExecutionMaxTimeQueryString=totals.max_sql,
        queryCacheEnabled=False,
        secondLevelCacheEnabled=False,
        secondLevelCacheRegions=[],
        statementCount=totals.statements,
        nPlusOne=n_plus_one(rows, exchanges, ctx.settings.sql_trace_n_plus_one_threshold, ctx.masker),
        nPlusOneWindow=f"retained SQL Trace window ({len(rows)} statements)",
        warnings=[RECORDING_PAUSED] if recorder is not None and not recorder.recording else [],
    )
    statistics.update(dict.fromkeys(CACHE_COUNT_KEYS, 0))
    return {
        "available": reason is None,
        "enableAvailable": False,
        "unavailableReason": reason,
        "statistics": {key: statistics[key] for key in STATISTICS_KEYS},
    }
