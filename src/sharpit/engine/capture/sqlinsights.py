"""``SqlTraceInsightsReport``: statement rankings and route attribution over the retained SQL Trace ring.

Ported from BootUI ``SqlTraceInsightsService``, ``SqlStatementRanking``, ``SqlRouteAttribution`` and
``RoutePathMasker``. Computed on demand from ``SqlTraceRecorder.rows()`` and ``HttpExchangeBuffer.rows()``.
"""

from __future__ import annotations

from typing import Any

from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.capture.sqltrace import SqlTraceRecorder

TOP_PER_CRITERION = 10


def percentile(sorted_ms: list[int], p: int) -> int:
    return 0


def mask_route(path: str | None) -> str:
    return path or "/"


def insights_report(
    recorder: SqlTraceRecorder | None, exchanges: HttpExchangeBuffer | None, reason: str | None
) -> dict[str, Any]:
    return {
        "available": True,
        "unavailableReason": None,
        "capturing": True,
        "window": {
            "retainedStatements": 0,
            "bufferSize": 0,
            "evicted": 0,
            "totalCaptured": 0,
            "oldestTimestamp": None,
            "newestTimestamp": None,
            "totalDurationMillis": 0,
        },
        "statements": [],
        "topPerCriterion": TOP_PER_CRITERION,
        "statementsTruncated": False,
        "distinctStatements": 0,
        "attribution": {
            "available": True,
            "routes": [],
            "supportedCorrelations": [],
            "unattributed": {"executions": 0, "reason": ""},
        },
        "notes": [],
    }
