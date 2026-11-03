"""``summarize_http_routes`` (BootUI 2.2.0 ``HttpRouteSummaryService``) and the capture budget pin (lane D2)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sharpit.engine.capture.exchanges import HttpExchangeBuffer, exchange_row
from sharpit.engine.capture.routes import summarize_http_routes
from sharpit.engine.masking import Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)
EPOCH_NS = 1_700_000_000_000_000_000
TIMING = Path(__file__).parents[2] / "fastapi"


def _add(buffer: HttpExchangeBuffer, n: int, method: str, path: str, status: int, ms: int, route: str | None) -> None:
    buffer.add(
        exchange_row(
            MASKED,
            request_id=f"r{n}",
            started_epoch_ns=EPOCH_NS + n * 1_000_000,
            method=method,
            path=path,
            query_string=b"",
            status=status,
            duration_ms=ms,
            size=0,
            client=None,
            user=None,
            request_headers=[],
            response_headers=[],
            route=route,
        )
    )


def _buffer() -> HttpExchangeBuffer:
    buffer = HttpExchangeBuffer(20)
    for n in range(10):  # GET /pets/{id}: 10..100 ms, the last one a 404
        _add(buffer, n, "GET", f"/pets/{n}", 404 if n == 9 else 200, 10 * (n + 1), "/pets/{id}")
    _add(buffer, 10, "POST", "/pets", 500, 5, "/pets")
    _add(buffer, 11, "POST", "/pets", 500, 5, "/pets")
    _add(buffer, 12, "GET", "/nope/123", 404, 1, None)  # no route matched: grouped by the masked path
    return buffer


def _route(report: dict[str, Any], route_id: str) -> dict[str, Any]:
    return next(r for r in report["routes"] if r["id"] == route_id)


def test_summarize_groups_by_method_and_route_and_computes_percentiles():
    # ported: HttpRouteSummaryServiceTests.summarizeGroupsByMethodAndRouteAndComputesPercentiles
    report = summarize_http_routes(_buffer())
    assert report.get("window") == {
        "retainedExchanges": 13,
        "bufferSize": 20,
        "evicted": 0,
        "hiddenSelfExchanges": 0,
        "summarizedExchanges": 13,
        "timedExchanges": 13,
        "oldestTimestamp": 1_700_000_000_000,
        "newestTimestamp": 1_700_000_000_012,
        "totalDurationMs": 561,
    }, "the window covers every retained exchange"
    assert [r["id"] for r in report["routes"]] == ["GET /pets/{id}", "POST /pets", "GET /nope/{value}"]
    assert _route(report, "GET /pets/{id}") == {
        "id": "GET /pets/{id}",
        "method": "GET",
        "route": "/pets/{id}",
        "routeSource": "FRAMEWORK_TEMPLATE",
        "requests": 10,
        "status2xx": 9,
        "status3xx": 0,
        "status4xx": 1,
        "status5xx": 0,
        "statusOther": 0,
        "errorCount": 1,
        "timedRequests": 10,
        "totalDurationMs": 550,
        "avgDurationMs": 55.0,
        "p50DurationMs": 50,
        "p95DurationMs": 100,
        "p99DurationMs": 100,
        "maxDurationMs": 100,
        "shareOfRetainedTimePercent": 98.04,
        "topFor": ["REQUESTS", "TOTAL_DURATION", "P95_DURATION"],
    }
    masked = _route(report, "GET /nope/{value}")
    assert (masked["route"], masked["routeSource"], masked["status4xx"]) == ("/nope/{value}", "MASKED_PATH", 1)
    assert (report["topPerCriterion"], report["routesTruncated"], report["distinctRoutes"]) == (25, False, 3)


def test_summarize_keeps_the_top_routes_per_criterion_and_a_pinned_route():
    # ported: HttpRouteSummaryServiceTests.limitsTopRoutesPerCriterionAndKeepsPinnedRoute
    report = summarize_http_routes(_buffer(), limit=1)
    assert [r["id"] for r in report.get("routes", [])] == ["GET /pets/{id}"], "only the top route per criterion"
    assert (report["topPerCriterion"], report["routesTruncated"], report["distinctRoutes"]) == (1, True, 3)
    pinned = summarize_http_routes(_buffer(), limit=1, route="/nope")
    assert [r["id"] for r in pinned["routes"]] == ["GET /pets/{id}", "GET /nope/{value}"]
    assert _route(pinned, "GET /nope/{value}")["topFor"] == []


def test_summarize_clamps_the_limit():
    assert summarize_http_routes(_buffer(), limit=0).get("topPerCriterion") == 1, "a limit below 1 clamps to 1"
    assert summarize_http_routes(_buffer(), limit=500).get("topPerCriterion") == 100
    assert summarize_http_routes(_buffer()).get("topPerCriterion") == 25


def test_summarize_reports_unavailable_without_capture():
    report = summarize_http_routes(None)
    assert report.get("available") is False, "no buffer: the report says why"
    assert report["unavailableReason"] == "Request capture is not installed"
    assert (report["routes"], report["distinctRoutes"], report["notes"]) == ([], 0, [])
    assert (report["window"]["oldestTimestamp"], report["window"]["retainedExchanges"]) == (None, 0)


def test_capture_overhead_budget_unchanged():
    """D2 adds work to the capture middleware and the SQL listener: their budgets are checked, never raised."""
    budgets = {
        "test_capture_overhead.py": "BUDGET_MS = 0.2",
        "test_sql_trace_overhead.py": "BUDGET_NS = 50_000",
        "test_transactions_overhead.py": "BUDGET_NS = 30_000",
    }
    for name, line in budgets.items():
        found = re.search(r"^BUDGET_\w+ = .+$", (TIMING / name).read_text("utf-8"), re.MULTILINE)
        assert found is not None, name
        assert found.group(0) == line, name
