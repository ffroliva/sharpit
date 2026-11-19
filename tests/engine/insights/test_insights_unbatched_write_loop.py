from __future__ import annotations

from typing import Any

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.masking import Exposure, Masker

KIND = "unbatched-write-loop"
ROUTE = "POST /api/orders"
Row = dict[str, object]


def sql(statement: str, batch_size: int = 1) -> Row:
    return {
        "source": "sql", "sql": statement, "traceId": None, "thread": "MainThread", "durationNanos": 1,
        "startedAt": 1, "dataSource": None, "failed": False, "phase": None, "completedNanos": 20,
        "codePathStamp": 0, "provenance": "EXECUTION", "batchSize": batch_size, "callSite": "app.py:1",
    }


class Run:
    def __init__(self) -> None:
        self.journal = RuntimeJournal(masker=Masker(Exposure.MASKED, True))
        self.requests = 0

    def request(self, *children: Row) -> None:
        self.requests += 1
        request_id = f"r{self.requests}"
        info = RequestInfo(request_id, "ctx", "POST", "/api/orders", None, 0, 30_000_000)
        for child in children:
            self.journal.offer({**child, "requestId": request_id})
        self.journal.offer(http_event(info, [], 1_000_000, 200, "/api/orders"))

    def report(self) -> Any:
        return InsightsService(self.journal).report()


# ported: UnbatchedWriteLoopTests.anUnbatchedWriteLoopIsReportedAfterTwoRequests

def test_unbatched_write_loop_requires_ten_single_executions_in_two_requests() -> None:
    run = Run()
    statement = "insert into orders (customer_id) values (12345)"
    run.request(*(sql(statement) for _ in range(10)))
    run.request(*(sql("insert into orders (customer_id) values (98765)") for _ in range(10)))

    report = run.report()
    findings = [row for row in report["observations"] if row["kind"] == KIND]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["status"] == "OBSERVED"
    assert finding["sentence"] == (
        "`POST /api/orders` ran `insert into orders (customer_id) values (?)` 10 or more times, "
        "each without a JDBC batch, in 2 of 2 requests, up to 10 times in one."
    )
    assert "12345" not in str(finding)
    assert "98765" not in str(finding)


# ported: UnbatchedWriteLoopTests.aBatchExecutionIsNotCountedAsUnbatched

def test_unbatched_write_loop_does_not_count_batched_writes() -> None:
    run = Run()
    run.request(*(sql("insert into orders (customer_id) values (?)", 50) for _ in range(12)))

    assert not any(row["kind"] == KIND for row in run.report()["observations"])

