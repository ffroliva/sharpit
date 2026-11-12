"""``SqlTraceInsightsReport``: statement rankings and route attribution over the retained SQL Trace ring.

Ported from BootUI ``SqlTraceInsightsService``, ``SqlStatementRanking``, ``SqlStatementAggregate``,
``SqlRouteAttribution`` and ``RoutePathMasker``. Computed on demand from ``SqlTraceRecorder.rows()`` and
``HttpExchangeBuffer.rows()``: no new capture, no SQL, no socket. Durations are the ring's whole milliseconds.

sharpit offers one correlation tier, ``TRACE_ID``: a SQL row's ``traceId`` is the capture middleware's request id,
joined exactly to the exchange row with that ``id``. Exchange rows carry no route template, so routes are grouped by
masked path (``MASKED_PATH``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.capture.sqltrace import SqlTraceRecorder

TOP_PER_CRITERION = 10
MAX_ROUTES = 20
MAX_STATEMENTS_PER_ROUTE = 5
MAX_LINKED_ENTRIES = 500
N_PLUS_ONE_THRESHOLD = 5  # BootUI ranks with SqlTraceGrouping.DEFAULT_N_PLUS_ONE_THRESHOLD, not the setting
CORRELATIONS = ["TRACE_ID"]
NO_EXCHANGES = (
    "HTTP exchange capture is off, so no captured request is available to attribute statements to; "
    "the rankings still cover every retained statement."
)
UNATTRIBUTED = (
    "No captured request could have issued these statements: none was in flight for the whole execution, or the "
    "request whose trace id the statement carries is no longer retained. Background jobs, scheduled work, startup "
    "and schema migrations belong here."
)
AMBIGUOUS = (
    "More than one captured request was an equally plausible source, so sharpit refused to pick one. Concurrent "
    "identical requests and a reused inbound trace id both produce this."
)
_ROUTE_WORD = re.compile(r"[A-Za-z_-]*(?:\.[A-Za-z_-]*)?")
_MAX_SEGMENT_LENGTH = 40
_MAX_SEGMENTS = 12


def percentile(sorted_ms: list[int], p: int) -> int:
    """Nearest-rank percentile (``SqlStatementAggregate.percentile``); 0 for no executions."""
    if not sorted_ms:
        return 0
    return sorted_ms[min(len(sorted_ms) - 1, max(0, math.ceil(p / 100 * len(sorted_ms)) - 1))]


def _share(part: int, total: int) -> float:
    """``SqlShares.percent``: two decimals, 0 with no measurable time."""
    return round(100 * part / total, 2) if total > 0 else 0


def _route_word(segment: str) -> bool:
    if len(segment) > _MAX_SEGMENT_LENGTH:
        return False
    if segment.startswith("{") and segment.endswith("}"):
        return True
    return (
        _ROUTE_WORD.fullmatch(segment) is not None
        and any(c.isalpha() for c in segment)
        and segment.lower() not in ("null", "undefined")
    )


def mask_route(path: str | None) -> str:
    """``RoutePathMasker.mask``: every segment that does not read like a fixed route word becomes ``{value}``."""
    bare = re.split(r"[?#]", (path or "").strip(), maxsplit=1)[0]
    segments = [s for s in bare.split("/") if s]
    shown = ["{value}" if not _route_word(s) else s for s in segments[:_MAX_SEGMENTS]]
    tail = "/…" if len(segments) > _MAX_SEGMENTS else ""
    return "/" + "/".join(shown) + tail if shown else "/"


@dataclass(eq=False)
class Group:
    """``SqlStatementAggregate``: one normalized statement (or one route's totals)."""

    id: str
    sql: str
    category: str
    durations: list[int] = field(default_factory=list[int])
    errors: int = 0
    call_sites: dict[str, None] = field(default_factory=dict[str, None])
    entry_ids: list[int] = field(default_factory=list[int])

    def add(self, row: dict[str, Any]) -> None:
        self.durations.append(max(0, row["durationMillis"]))
        self.errors += not row["success"]
        if len(self.entry_ids) < MAX_LINKED_ENTRIES:
            self.entry_ids.append(row["id"])
        site = row.get("callSite")
        if site is not None and len(self.call_sites) < 5:  # SqlTraceGrouping.MAX_CALL_SITES_PER_GROUP
            self.call_sites[site] = None

    @property
    def executions(self) -> int:
        return len(self.durations)

    @property
    def total(self) -> int:
        return sum(self.durations)

    @property
    def max(self) -> int:
        return max(self.durations, default=0)

    @property
    def avg(self) -> float:
        return self.total / self.executions if self.durations else 0

    def percentile(self, p: int) -> int:
        return percentile(sorted(self.durations), p)


CRITERIA: dict[str, Callable[[Group], float]] = {
    "TOTAL_DURATION": lambda g: g.total,
    "MAX_DURATION": lambda g: g.max,
    "EXECUTIONS": lambda g: g.executions,
    "AVG_DURATION": lambda g: g.avg,
    "ERROR_COUNT": lambda g: g.errors,
    "P95_DURATION": lambda g: g.percentile(95),
    "P99_DURATION": lambda g: g.percentile(99),
}
MAX_RANKED_STATEMENTS = TOP_PER_CRITERION * len(CRITERIA)


def _by(metric: Callable[[Group], float]) -> Callable[[Group], tuple[float, str]]:
    """Highest metric first, then the fingerprint ascending, so ties never depend on buffer order."""
    return lambda g: (-metric(g), g.id)


def _add(groups: dict[str, Group], row: dict[str, Any]) -> None:
    # The capture-time shape is the one identity shared with SQL Trace and SQLAlchemy Statistics.
    shape = row["shape"]
    if shape.fingerprint is None:
        return
    group = groups.get(shape.fingerprint)
    if group is None:
        group = groups[shape.fingerprint] = Group(shape.fingerprint, shape.text, row["category"] or "OTHER")
    group.add(row)


def rank(groups: list[Group], total: int) -> list[dict[str, Any]]:
    """``SqlStatementRanking.rank``: the union of each criterion's top 10, ordered by total duration."""
    top_for: dict[str, list[str]] = {}
    for name, metric in CRITERIA.items():
        chosen = sorted((g for g in groups if metric(g) > 0), key=_by(metric))[:TOP_PER_CRITERION]
        for group in chosen:
            top_for.setdefault(group.id, []).append(name)
    ranked = sorted((g for g in groups if g.id in top_for), key=_by(CRITERIA["TOTAL_DURATION"]))
    return [
        {
            "id": g.id,
            "sql": g.sql,
            "category": g.category,
            "executions": g.executions,
            "totalDurationMillis": g.total,
            "maxDurationMillis": g.max,
            "avgDurationMillis": round(g.avg, 2),
            "errorCount": g.errors,
            "p50DurationMillis": g.percentile(50),
            "p95DurationMillis": g.percentile(95),
            "p99DurationMillis": g.percentile(99),
            "shareOfRetainedTimePercent": _share(g.total, total),
            "topFor": top_for[g.id],
            "potentialNPlusOne": g.category.upper() == "SELECT" and g.executions >= N_PLUS_ONE_THRESHOLD,
            "callSites": list(g.call_sites),
            "entryIds": g.entry_ids,
            "entryIdsTruncated": len(g.entry_ids) < g.executions,
        }
        for g in ranked
    ]


@dataclass(eq=False)
class _Route:
    id: str
    method: str
    route: str
    totals: Group
    statements: dict[str, Group] = field(default_factory=dict[str, Group])
    requests: set[str] = field(default_factory=set[str])

    def dto(self, total: int) -> dict[str, Any]:
        ordered = sorted(self.statements.values(), key=_by(CRITERIA["TOTAL_DURATION"]))
        top = ordered[:MAX_STATEMENTS_PER_ROUTE]
        t = self.totals
        return {
            "id": self.id,
            "method": self.method,
            "route": self.route,
            "routeSource": "MASKED_PATH",
            "requests": len(self.requests),
            "executions": t.executions,
            "totalDurationMillis": t.total,
            "maxDurationMillis": t.max,
            "avgDurationMillis": round(t.avg, 2),
            "errorCount": t.errors,
            "distinctStatements": len(self.statements),
            "shareOfRetainedTimePercent": _share(t.total, total),
            "traceCorrelated": t.executions,
            "threadCorrelated": 0,
            "timeWindowCorrelated": 0,
            "topStatements": [
                {
                    "statementId": g.id,
                    "sql": g.sql,
                    "category": g.category,
                    "executions": g.executions,
                    "totalDurationMillis": g.total,
                    "maxDurationMillis": g.max,
                    "errorCount": g.errors,
                }
                for g in top
            ],
            "topStatementsTruncated": len(ordered) > len(top),
            "entryIds": t.entry_ids,
        }


def _bucket(group: Group | None, total: int, reason: str | None) -> dict[str, Any]:
    group = group or Group("", "", "")
    return {
        "executions": group.executions,
        "totalDurationMillis": group.total,
        "errorCount": group.errors,
        "shareOfRetainedTimePercent": _share(group.total, total),
        "reason": reason,
    }


def _attribution_unavailable(reason: str | None) -> dict[str, Any]:
    return {
        "available": False,
        "unavailableReason": reason,
        "supportedCorrelations": [],
        "requestsConsidered": 0,
        "routes": [],
        "routesTruncated": False,
        "distinctRoutes": 0,
        "attributedExecutions": 0,
        "unattributed": _bucket(None, 0, None),
        "ambiguous": _bucket(None, 0, None),
        "notes": [],
    }


def _attribution(rows: list[dict[str, Any]], exchanges: HttpExchangeBuffer | None, total: int) -> dict[str, Any]:
    """``SqlRouteAttribution.attribute`` with the trace-id tier only."""
    if exchanges is None:
        return _attribution_unavailable(NO_EXCHANGES)
    requests = exchanges.rows()
    by_id = {request["id"]: request for request in requests}
    routes: dict[str, _Route] = {}
    unattributed = Group("", "", "")
    for row in rows:
        request = by_id.get(row["traceId"]) if row["traceId"] else None
        if request is None:  # outside any request, or its exchange was evicted: never handed to another request
            unattributed.add(row)
            continue
        method = (request["method"] or "UNKNOWN").upper()
        path = mask_route(request["path"])
        key = f"{method} {path}"
        route = routes.get(key)
        if route is None:
            route = routes[key] = _Route(key, method, path, Group(key, "", ""))
        route.totals.add(row)
        route.requests.add(request["id"])
        _add(route.statements, row)
    ordered = sorted(routes.values(), key=lambda r: (-r.totals.total, r.id))
    notes: list[str] = []
    if not requests:
        notes.append(
            "No captured HTTP requests were available to attribute against, so every retained statement is "
            "reported as unattributed."
        )
    notes.append(
        "This runtime has no one-thread-per-request invariant, so serving-thread correlation is not offered; "
        "attribution relies on trace context first."
    )
    if rows and not any(row["traceId"] for row in rows):
        notes.append(
            "No retained statement carried a request id: none ran inside a request sharpit's capture middleware saw."
        )
    notes.append(
        "Routes are grouped by the route template the runtime reports or the application declares. A path no "
        "declared route matches is grouped by a masked path instead, where every segment that does not read like a "
        "fixed route word is replaced. Query strings are never used."
    )
    notes.append(
        "No declared route mappings were available to match paths against, so masked paths are the only grouping "
        "sharpit can offer here."
    )
    return {
        "available": True,
        "unavailableReason": None,
        "supportedCorrelations": CORRELATIONS,
        "requestsConsidered": len(requests),
        "routes": [route.dto(total) for route in ordered[:MAX_ROUTES]],
        "routesTruncated": len(ordered) > MAX_ROUTES,
        "distinctRoutes": len(ordered),
        "attributedExecutions": len(rows) - unattributed.executions,
        "unattributed": _bucket(unattributed, total, UNATTRIBUTED),
        "ambiguous": _bucket(None, total, AMBIGUOUS),  # a request id names exactly one exchange
        "notes": notes,
    }


def unavailable_report(reason: str) -> dict[str, Any]:
    """``SqlTraceInsightsReport.unavailable``."""
    return {
        "available": False,
        "unavailableReason": reason,
        "capturing": False,
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
        "topPerCriterion": 0,
        "statementsTruncated": False,
        "distinctStatements": 0,
        "attribution": _attribution_unavailable(reason),
        "notes": [],
    }


def insights_report(
    recorder: SqlTraceRecorder | None, exchanges: HttpExchangeBuffer | None, reason: str | None
) -> dict[str, Any]:
    """``SqlTraceInsightsService.insights``; ``reason`` (tracing off, SQLAlchemy absent) makes it unavailable."""
    if recorder is None or reason is not None:
        return unavailable_report(reason or "SQL tracing is not active, so there are no retained statements to rank.")
    rows = recorder.rows()
    groups: dict[str, Group] = {}
    for row in rows:
        _add(groups, row)
    total = sum(g.total for g in groups.values())
    statements = rank(list(groups.values()), total)
    truncated = len(groups) > len(statements)
    stamps = [row["timestamp"] // 1_000_000 for row in rows]  # epoch ns -> ms
    captured, evicted = recorder.counters()
    notes = [
        f"Rankings cover the {len(rows)} statement executions currently retained in the SQL Trace buffer of "
        f"{recorder.max_entries}. They are diagnostic evidence for this window, not lifetime metrics."
    ]
    if evicted > 0:
        notes.append(
            "Older executions have been dropped from the buffer, so totals and percentiles under-report work that "
            "has already aged out."
        )
    if not recorder.recording:
        notes.append("Recording is paused, so the window will not grow until it is resumed.")
    if truncated:
        notes.append(
            f"Only the top {TOP_PER_CRITERION} statements per ranking criterion are listed; {len(groups)} distinct "
            "normalized statements were observed."
        )
    notes.append(
        "Statements are grouped after normalization: literal values are replaced with placeholders, so equivalent "
        "executions aggregate and no bound value is shown."
    )
    return {
        "available": True,
        "unavailableReason": None,
        "capturing": recorder.recording,
        "window": {
            "retainedStatements": len(rows),
            "bufferSize": recorder.max_entries,
            "evicted": evicted,
            "totalCaptured": captured,
            "oldestTimestamp": min(stamps, default=None),
            "newestTimestamp": max(stamps, default=None),
            "totalDurationMillis": total,
        },
        "statements": statements,
        "topPerCriterion": TOP_PER_CRITERION,
        "statementsTruncated": truncated,
        "distinctStatements": len(groups),
        "attribution": _attribution(rows, exchanges, total),
        "notes": notes,
    }
