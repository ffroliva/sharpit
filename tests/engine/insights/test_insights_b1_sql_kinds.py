from __future__ import annotations

from typing import Any

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.masking import Exposure, Masker

Row = dict[str, object]


def sql(statement: str, completed: int = 20, duration: int = 1) -> Row:
    return {"source": "sql", "sql": statement, "traceId": None, "thread": "MainThread", "durationNanos": duration,
            "startedAt": completed-duration, "dataSource": None, "failed": False, "phase": None,
            "completedNanos": completed, "codePathStamp": 0, "provenance": "EXECUTION", "batchSize": 1,
            "callSite": "app.py:1"}


class Run:
    def __init__(self) -> None:
        self.journal = RuntimeJournal(masker=Masker(Exposure.MASKED, True))
        self.requests = 0

    def request(self, *children: Row) -> None:
        self.requests += 1
        request_id = f"r{self.requests}"
        info = RequestInfo(request_id, "ctx", "GET", "/api/orders", None, 0, 30_000_000)
        for child in children:
            self.journal.offer({**child, "requestId": request_id})
        self.journal.offer(http_event(info, [], 1_000_000, 200, "/api/orders"))

    def findings(self, kind: str) -> list[dict[str, Any]]:
        return [row for row in InsightsService(self.journal).report()["observations"] if row["kind"] == kind]


# ported: RepeatedSelectsTests.aRepeatedSelectAfterAParentQueryIsReported

def test_repeated_selects_report_repeated_shape_and_mask_secret_literals() -> None:
    run = Run()
    for _ in range(3):
        run.request(sql("select id from orders"), *(sql("select id from items where api_token = 'secret-abc'") for _ in range(5)))
    findings = run.findings("repeated-selects")
    assert len(findings) == 1
    assert findings[0]["status"] == "OBSERVED"
    assert "secret-abc" not in str(findings[0])


# ported: RepeatedSelectsTests.sqlEventsAreSortedByTheirMonotonicStart

def test_repeated_selects_order_events_by_monotonic_start_before_grouping() -> None:
    run = Run()
    # Journal order differs from execution order: parent starts before child queries.
    run.request(sql("select id from orders", 50, 30), sql("select id from items", 30, 10),
                sql("select id from items", 40, 10), sql("select id from items", 50, 10),
                sql("select id from items", 60, 10), sql("select id from items", 70, 10))
    assert run.findings("repeated-selects")


# ported: PagedWithoutOrderTests.anUnorderedPageIsReportedPerRoute

def test_paged_without_order_reports_unordered_page_and_masks_literal() -> None:
    run = Run()
    for _ in range(2):
        run.request(sql("select id from orders where status = 'secret-abc' limit ? offset ?"))
    findings = run.findings("paged-without-order")
    assert len(findings) == 1
    assert findings[0]["status"] == "OBSERVED"
    assert "secret-abc" not in str(findings[0])


# ported: PagedWithoutOrderTests.aSortedPageIsNotReported

def test_paged_without_order_ignores_sorted_page() -> None:
    run = Run()
    for _ in range(2):
        run.request(sql("select id from orders order by id limit ? offset ?"))
    assert not run.findings("paged-without-order")
