"""``sqlalchemy-statistics`` (BootUI ``hibernate-statistics``): SQL recorder lifetime totals plus N+1 per route."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sharpit.engine import sqla
from sharpit.engine.capture.sqltrace import SqlTotals, normalize
from sharpit.engine.context import SharpitContext

NULL_REASON = "SQLAlchemy reports SQL statements, not ORM session or entity operations"
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
)
REPORT_KEYS = ("available", "enableAvailable", "unavailableReason", "statistics")


MAX_N_PLUS_ONE = 20
ROUTE_UNKNOWN = "No HTTP Exchanges row for this request (HTTP Exchanges disabled, or the row was evicted)"


def n_plus_one(
    rows: list[dict[str, Any]], route_of: Callable[[str], tuple[str, str] | None], threshold: int
) -> list[dict[str, Any]]:
    """BootUI's per-statement rule per request: a request running one SELECT shape ``threshold`` times is one hit."""
    groups: dict[tuple[str, str], tuple[str, int]] = {}  # (request, fingerprint) -> (normalised sql, executions)
    for row in rows:
        request_id = row["traceId"]
        if request_id is None or row["category"] != "SELECT":
            continue
        shape = normalize(row["sql"])  # never the raw text: with capture_parameters it holds literals
        key = (request_id, shape.fingerprint)
        groups[key] = (shape.sql, groups.get(key, (shape.sql, 0))[1] + 1)
    merged: dict[tuple[str | None, str | None, str], dict[str, Any]] = {}
    for (request_id, fingerprint), (sql, count) in groups.items():
        if count < threshold:
            continue
        route = route_of(request_id)
        method, path = route if route is not None else (None, None)
        entry = merged.setdefault(
            (method, path, fingerprint),
            {
                "method": method,
                "route": path,
                "routeReason": None if route is not None else ROUTE_UNKNOWN,
                "sql": sql,
                "executionsPerRequest": 0,
                "requests": 0,
                "threshold": threshold,
            },
        )
        entry["requests"] += 1
        entry["executionsPerRequest"] = max(entry["executionsPerRequest"], count)
    ranked = sorted(merged.values(), key=lambda e: (-e["executionsPerRequest"], e["sql"]))
    return ranked[:MAX_N_PLUS_ONE]


def statistics_report(ctx: SharpitContext) -> dict[str, Any]:
    from sharpit.engine.tools import sql_trace_unavailable_reason  # lazy: tools imports the lane tool modules

    recorder = ctx.capture.sql_trace
    reason = sql_trace_unavailable_reason(ctx)
    if recorder is None and reason is None:
        reason = sqla.TRACING_DISABLED
    totals = recorder.totals() if recorder is not None else SqlTotals(0, 0, 0, None)
    rows = recorder.rows() if recorder is not None else []
    exchanges = ctx.capture.exchanges

    def route_of(request_id: str) -> tuple[str, str] | None:
        row = exchanges.get(request_id) if exchanges is not None else None
        return None if row is None else (row["method"], row["endpoint"] or row["path"])

    statistics: dict[str, Any] = dict.fromkeys(NULL_KEYS)
    statistics.update(
        queryExecutionCount=totals.selects,
        queryExecutionMaxTime=totals.max_millis,
        queryExecutionMaxTimeQueryString=totals.max_sql,
        queryCacheEnabled=False,
        secondLevelCacheEnabled=False,
        secondLevelCacheRegions=[],
        statementCount=totals.statements,
        nPlusOne=n_plus_one(rows, route_of, ctx.settings.sql_trace_n_plus_one_threshold),
        nPlusOneWindow=f"retained SQL Trace window ({len(rows)} statements)",
    )
    statistics.update(dict.fromkeys(CACHE_COUNT_KEYS, 0))
    return {
        "available": reason is None,
        "enableAvailable": False,
        "unavailableReason": reason,
        "statistics": {key: statistics[key] for key in STATISTICS_KEYS},
    }
