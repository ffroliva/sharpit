"""``sqlalchemy-statistics`` (BootUI ``hibernate-statistics``): the SQL recorder's lifetime totals plus N+1 per route."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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


def n_plus_one(
    rows: list[dict[str, Any]], route_of: Callable[[str], tuple[str, str] | None], threshold: int
) -> list[dict[str, Any]]:
    return []


def statistics_report(ctx: SharpitContext) -> dict[str, Any]:
    statistics: dict[str, Any] = {key: -1 for key in STATISTICS_KEYS} | {"nPlusOne": []}
    return {key: -1 for key in REPORT_KEYS} | {"statistics": statistics}
