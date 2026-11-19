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
        "source": "sql",
        "sql": statement,
        "traceId": None,
        "thread": "MainThread",
        "durationNanos": 1,
        "startedAt": 1,
        "dataSource": None,
        "failed": False,
        "phase": None,
        "completedNanos": 20,
        "codePathStamp": 0,
        "provenance": "EXECUTION",
        "batchSize": batch_size,
        "callSite": "app.py:1",
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


# ported: UnbatchedWriteLoopTests.aLoopOfSingleWritesInTwoRequestsIsReportedWithItsShapeCallSiteAndTime


def test_unbatched_write_loop_requires_ten_single_executions_in_two_requests() -> None:
    run = Run()
    statement = "update orders set status = 'pending' where api_token = 'secret-value-12345'"
    run.request(*(sql(statement) for _ in range(10)))
    run.request(
        *(sql("update orders set status = 'pending' where api_token = 'secret-value-98765'") for _ in range(10))
    )

    report = run.report()
    findings = [row for row in report["observations"] if row["kind"] == KIND]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["status"] == "OBSERVED"
    assert finding["sentence"] == (
        "`POST /api/orders` ran one write statement shape 10 or more times, "
        "each without a JDBC batch, in 2 of 2 requests, up to 10 times in one."
    )
    assert "secret-value-12345" not in str(finding)
    assert "secret-value-98765" not in str(finding)
    detail = InsightsService(run.journal).insight(str(finding["id"]))
    assert "secret-value-12345" not in str(detail)
    assert "secret-value-98765" not in str(detail)


# ported: UnbatchedWriteLoopTests.aBatchNineSinglesAndAnUnbatchedReadAreNotLoops


def test_unbatched_write_loop_does_not_count_nine_writes_or_reads() -> None:
    run = Run()
    run.request(*(sql("insert into orders (customer_id) values (?)") for _ in range(9)))
    run.request(*(sql("select id from orders") for _ in range(12)))

    assert not any(row["kind"] == KIND for row in run.report()["observations"])


# ported: UnbatchedWriteLoopTests.aBatchOfOneIsAnOrdinaryExecutionAndCounts


def test_batch_size_one_counts_as_unbatched() -> None:
    run = Run()
    statement = "insert into orders (id) values (?)"
    for _ in range(2):
        run.request(*(sql(statement, 1) for _ in range(10)))

    assert any(row["kind"] == KIND for row in run.report()["observations"])


# ported: UnbatchedWriteLoopTests.aSingleQualifyingRequestIsInsufficient


def test_unbatched_write_loop_is_insufficient_until_two_requests_show_the_loop() -> None:
    run = Run()
    run.request(*(sql("insert into orders (id) values (?)") for _ in range(10)))

    finding = next(row for row in run.report()["observations"] if row["kind"] == KIND)
    assert finding["status"] == "INSUFFICIENT"
