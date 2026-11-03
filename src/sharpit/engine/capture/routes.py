"""HTTP route summary (BootUI 2.2.0 ``HttpRouteSummaryService``): ``GET /http-exchanges/routes`` over the ring.

Rows carry their route at capture time (``exchange_row``): the template the framework matched, else the masked path
with every value-like segment replaced (``mask_route``), so a raw id or token in a 404 path never becomes a route.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from sharpit.engine.capture.exchanges import HttpExchangeBuffer

DEFAULT_TOP_PER_CRITERION: Final[int] = 25
MAX_TOP_PER_CRITERION: Final[int] = 100
FRAMEWORK_TEMPLATE: Final = "FRAMEWORK_TEMPLATE"
MASKED_PATH: Final = "MASKED_PATH"
NOT_INSTALLED = "Request capture is not installed"
# (criterion, the HttpRouteDto key it ranks by): BootUI's golden tags every route with these three
_CRITERIA = (("REQUESTS", "requests"), ("TOTAL_DURATION", "totalDurationMs"), ("P95_DURATION", "p95DurationMs"))


def route_of(template: str | None, masked_path: str) -> tuple[str, str]:
    """``(route, routeSource)`` of one exchange: the matched template, else the masked path."""
    if template:
        return template, FRAMEWORK_TEMPLATE
    from sharpit.engine.capture.sqlinsights import mask_route  # sqlinsights imports exchanges, which imports this

    return mask_route(masked_path), MASKED_PATH


def _notes(retained: int) -> list[str]:
    return [
        f"Every figure covers only the {retained} retained, visible exchanges. These are diagnostic evidence for this "
        "window, not lifetime or service-level metrics, and a route with few requests has few samples behind its "
        "percentiles.",
        "Routes use the template the framework matched, then the path with every value-like segment masked. Query "
        "strings are never used.",
    ]


def _nearest_rank(ordered: list[int], fraction: float) -> int | None:
    return ordered[max(1, math.ceil(fraction * len(ordered))) - 1] if ordered else None


def _window(retention: dict[str, Any], hidden: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    starts = [r["startNs"] // 1_000_000 for r in rows]
    return {
        "retainedExchanges": len(rows),
        "bufferSize": retention["capacity"],
        "evicted": retention["evicted"],
        "hiddenSelfExchanges": hidden,
        "summarizedExchanges": len(rows),  # sharpit never stores its own requests: every retained row is visible
        "timedExchanges": len(rows),
        "oldestTimestamp": min(starts, default=None),
        "newestTimestamp": max(starts, default=None),
        "totalDurationMs": sum(r["durationMs"] for r in rows),
    }


def _route_dto(rows: list[dict[str, Any]], window_ms: int) -> dict[str, Any]:
    first = rows[0]
    durations = sorted(r["durationMs"] for r in rows)
    total = sum(durations)
    families = [r["statusFamily"] for r in rows]
    return {
        "id": f"{first['method']} {first['route']}",
        "method": first["method"],
        "route": first["route"],
        "routeSource": first["routeSource"],
        "requests": len(rows),
        "status2xx": families.count("2xx"),
        "status3xx": families.count("3xx"),
        "status4xx": families.count("4xx"),
        "status5xx": families.count("5xx"),
        "statusOther": sum(f not in ("2xx", "3xx", "4xx", "5xx") for f in families),
        "errorCount": sum(r["status"] >= 400 or r["error"] for r in rows),
        "timedRequests": len(durations),
        "totalDurationMs": total,
        "avgDurationMs": round(total / len(durations), 2),
        "p50DurationMs": _nearest_rank(durations, 0.50),
        "p95DurationMs": _nearest_rank(durations, 0.95),
        "p99DurationMs": _nearest_rank(durations, 0.99),
        "maxDurationMs": durations[-1],
        "shareOfRetainedTimePercent": round(100 * total / window_ms, 2) if window_ms > 0 else 0.0,
        "topFor": [],
    }


def unavailable_routes(reason: str, top: int) -> dict[str, Any]:
    """``HttpRoutesReport.unavailable``."""
    empty = {"capacity": 0, "evicted": 0}
    return {
        "available": False,
        "unavailableReason": reason,
        "window": _window(empty, 0, []),
        "routes": [],
        "topPerCriterion": top,
        "routesTruncated": False,
        "distinctRoutes": 0,
        "notes": [],
    }


def summarize_http_routes(
    exchanges: HttpExchangeBuffer | None, *, limit: int | None = None, route: str | None = None
) -> dict[str, Any]:
    """``HttpRoutesReport``: one row per ``METHOD route``, the top ``limit`` per criterion plus a pinned ``route``."""
    top = min(max(DEFAULT_TOP_PER_CRITERION if limit is None else limit, 1), MAX_TOP_PER_CRITERION)
    if exchanges is None:
        return unavailable_routes(NOT_INSTALLED, top)
    if exchanges.unavailable_reason is not None:
        return unavailable_routes(exchanges.unavailable_reason, top)
    rows, hidden, retention = exchanges.snapshot()
    window = _window(retention, hidden, rows)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["method"], row["route"]), []).append(row)
    dtos = [_route_dto(group, window["totalDurationMs"]) for group in grouped.values()]
    for criterion, key in _CRITERIA:
        ranked = sorted(dtos, key=lambda d: (-(d[key] or 0), d["id"]))
        for dto in ranked[:top]:
            dto["topFor"].append(criterion)
    pinned = (route or "").strip().lower()
    shown = [d for d in dtos if d["topFor"] or (pinned and pinned in d["route"].lower())]
    shown.sort(key=lambda d: (-d["totalDurationMs"], d["id"]))
    return {
        "available": True,
        "unavailableReason": None,
        "window": window,
        "routes": shown,
        "topPerCriterion": top,
        "routesTruncated": len(shown) < len(dtos),
        "distinctRoutes": len(dtos),
        "notes": _notes(len(rows)),
    }
