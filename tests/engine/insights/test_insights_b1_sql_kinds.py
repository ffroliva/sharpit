from __future__ import annotations

from typing import Any

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.agent_view import Steps, agent_list
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext.constants import UNSUPPORTED_STATEMENT
from sharpit.engine.tools import COMMANDS

Row = dict[str, object]


def sql(statement: str, completed: int = 20, duration: int = 1, batch: int = 1) -> Row:
    return {
        "source": "sql",
        "sql": statement,
        "traceId": None,
        "thread": "MainThread",
        "durationNanos": duration,
        "startedAt": completed - duration,
        "dataSource": None,
        "failed": False,
        "phase": None,
        "completedNanos": completed,
        "codePathStamp": 0,
        "provenance": "EXECUTION",
        "batchSize": batch,
        "callSite": "app.py:1",
    }


class Run:
    def __init__(self, exposure: Exposure = Exposure.MASKED) -> None:
        self.journal = RuntimeJournal(masker=Masker(exposure, True))
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


# ported: RuntimeInsightsServiceTests.repeatedSelectsAfterAParentStatementAreObservedOnceThreeRequestsShowThem


def test_repeated_selects_report_repeated_shape_and_mask_secret_literals() -> None:
    run = Run()
    for _ in range(3):
        run.request(
            sql("select id from orders"),
            *(sql("select id from items where api_token = 'secret-abc'") for _ in range(5)),
        )
    findings = run.findings("repeated-selects")
    assert len(findings) == 1
    assert findings[0]["status"] == "OBSERVED"
    assert "secret-abc" not in str(findings[0])


# derived: route denominator and all-zero timing edge cases


def test_repeated_selects_order_events_by_monotonic_start_before_grouping() -> None:
    run = Run()
    # Parent is published last but starts before the repeated SELECTs.
    run.request(
        sql("select id from items", 30, 10),
        sql("select id from items", 40, 10),
        sql("select id from items", 50, 10),
        sql("select id from items", 60, 10),
        sql("select id from items", 70, 10),
        sql("select id from orders", 20, 10),
    )
    assert run.findings("repeated-selects")


# derived: eligible route requests, not affected requests, are the denominator
def test_repeated_selects_denominator_includes_single_select_requests() -> None:
    run = Run()
    for _ in range(3):
        run.request(sql("select id from orders"), *(sql("select id from items") for _ in range(5)))
    for _ in range(5):
        run.request(sql("select id from orders"))
    finding = run.findings("repeated-selects")[0]
    assert "3 of 8 requests" in finding["sentence"]
    assert finding["eligible"] == 8


# derived: all-zero durations are known but unmeasured, so the floor cannot hide them
def test_repeated_selects_zero_time_is_unmeasured_and_not_under_floor() -> None:
    run = Run(Exposure.FULL)
    run.request(sql("select id from orders"), *(sql("select id from items", duration=0) for _ in range(5)))
    finding = run.findings("repeated-selects")[0]
    assert "Total repeat time is unmeasured: every execution was recorded as 0." in finding["limitations"]
    assert not any("left out of the default agent list" in x for x in finding["limitations"])


# derived: measured repeats under 50 ms and ten executions carry the default-list floor
def test_repeated_selects_marks_cheap_insufficient_finding_under_floor() -> None:
    run = Run(Exposure.FULL)
    run.request(
        sql("select id from orders"),
        *(sql("select id from items") for _ in range(5)),
    )
    finding = run.findings("repeated-selects")[0]
    assert any("left out of the default agent list" in x for x in finding["limitations"])
    listed = agent_list(InsightsService(run.journal).report(), None, None, Steps(COMMANDS))
    assert not any(row["kind"] == "repeated-selects" for row in listed["observations"])


# derived: only negative or missing durations are unknown
def test_repeated_selects_negative_and_missing_durations_are_unknown() -> None:
    run = Run(Exposure.FULL)
    rows = [sql("select id from orders"), *(sql("select id from items", duration=-1) for _ in range(3))]
    missing = sql("select id from items")
    del missing["durationNanos"]
    run.request(*rows, missing, sql("select id from items", duration=-1))
    finding = run.findings("repeated-selects")[0]
    detail = InsightsService(run.journal).insight(str(finding["id"]))
    assert detail["rows"][0]["cells"][2] == "unknown"
    assert "Total repeat time is unknown." in finding["limitations"]


# derived: the unsupported-database SQL placeholder is counted as unreadable evidence
def test_repeated_selects_reports_unsupported_sql_as_uncounted() -> None:
    run = Run()
    run.request(sql("select id from orders"), *(sql(UNSUPPORTED_STATEMENT) for _ in range(5)))
    report = InsightsService(run.journal).report()
    check = next(row for row in report["checks"] if row["kind"] == "repeated-selects")
    assert "unsupported-database placeholder" in check["reason"]


# derived: route denominator and all-zero timing edge cases
def test_repeated_selects_counts_all_route_requests_and_formats_zero_time() -> None:
    run = Run(Exposure.FULL)
    for _ in range(3):
        run.request(sql("select id from orders"), *(sql("select id from items", duration=0) for _ in range(5)))
    finding = run.findings("repeated-selects")[0]
    assert "3 of 3 requests" in finding["sentence"]
    detail = InsightsService(run.journal).insight(str(finding["id"]))
    assert detail["rows"][0]["cells"][2] == "0.0"
    assert detail["columns"][-2:] == ["Phase", "In transaction"]
    assert detail["rows"][0]["cells"][-2:] == ["unknown", "unknown"]
    assert finding["whatToCheck"] == [
        "Open an exemplar request in Live Activity and check whether each repeat loads the children of one row the "
        "first statement returned.",
        "If it does, load them with one statement, such as a join or an IN list, in SQL Trace's call site.",
    ]
    assert "Total repeat time is unmeasured: every execution was recorded as 0." in finding["limitations"]


# ported: RuntimeInsightsServiceTests.repeatedSelectsAfterAParentStatementAreObservedOnceThreeRequestsShowThem
def test_repeated_selects_insufficient_sentence_uses_threshold_and_bootui_pluralization() -> None:
    for extra in (0, 4):
        run = Run()
        run.request(sql("select id from orders"), *(sql("select id from items") for _ in range(5)))
        for _ in range(extra):
            run.request(sql("select id from orders"))
        finding = run.findings("repeated-selects")[0]
        assert finding["sentence"] == (
            "`GET /api/orders`: 1 of 3 requests needed to report `select id from items` repeated 5 or more times."
        )


# derived: BootUI's insufficient threshold count is independent of the route denominator
def test_repeated_selects_insufficient_sentence_counts_needed_requests() -> None:
    run = Run()
    run.request(sql("select id from orders"), *(sql("select id from items") for _ in range(5)))
    for _ in range(4):
        run.request(sql("select id from orders"))
    finding = run.findings("repeated-selects")[0]
    assert finding["sentence"] == (
        "`GET /api/orders`: 1 of 3 requests needed to report `select id from items` repeated 5 or more times."
    )


# derived: every executed event takes BootUI's first slot before SQL readability and failure checks
def test_repeated_selects_unreadable_executed_statement_can_be_parent() -> None:
    run = Run(Exposure.FULL)
    parent = sql("select id from orders union select id from customers")
    parent["failed"] = True
    run.request(parent, *(sql("select id from items") for _ in range(5)))
    assert run.findings("repeated-selects")


# derived: the displayed call site is the most frequent among the repeats
def test_repeated_selects_shows_the_most_frequent_call_site() -> None:
    run = Run(Exposure.FULL)
    children = [sql("select id from orders")]
    sites = ["rare.py:1", "common.py:2", "common.py:2", "common.py:2", "other.py:3", "common.py:2"]
    for site in sites:
        child = sql("select id from items")
        child["callSite"] = site
        children.append(child)
    run.request(*children)
    finding = run.findings("repeated-selects")[0]
    detail = InsightsService(run.journal).insight(str(finding["id"]))
    assert detail["rows"][0]["cells"][3] == "common.py:2"


# derived: unbatched unknown count includes only possible writes
def test_unbatched_unknown_count_ignores_unreadable_reads_and_batched_inserts() -> None:
    run = Run()
    statements = [sql("select id from users where api_token = 'secret-value'") for _ in range(20)] + [
        sql("insert into x values (?)", batch=2) for _ in range(10)
    ]
    run.request(*statements)
    report = InsightsService(run.journal).report()
    check = next(row for row in report["checks"] if row["kind"] == "unbatched-write-loop")
    assert "unreadable SQL" not in check["reason"]
    assert "no recorded batch size" not in check["reason"]


# ported: UnbatchedWriteLoopTests.aSingleQualifyingRequestIsInsufficient
def test_unbatched_insufficient_sentence_uses_threshold_for_one_and_five_route_requests() -> None:
    for extra in (0, 3):
        run = Run()
        run.request(*(sql("insert into orders values (?)") for _ in range(10)))
        for _ in range(extra):
            run.request(sql("insert into orders values (?)"))
        finding = run.findings("unbatched-write-loop")[0]
        assert finding["sentence"] == (
            "`GET /api/orders`: 1 of 2 requests needed to report `insert into orders values (?)` run 10 or more times "
            "without a JDBC batch."
        )


# ported: UnbatchedWriteLoopTests.anExecutedWriteWithUnknownBatchSizeIsNeverCountedAndTheCheckSaysSo
def test_unbatched_unknown_reason_uses_bootui_singular_and_plural() -> None:
    for count, phrase in (
        (1, "1 executed write had no recorded batch size, so it is not counted as unbatched."),
        (5, "5 executed writes had no recorded batch size, so they are not counted as unbatched."),
    ):
        run = Run()
        run.request(*(sql("insert into orders values (?)", batch=0) for _ in range(count)))
        report = InsightsService(run.journal).report()
        check = next(row for row in report["checks"] if row["kind"] == "unbatched-write-loop")
        assert phrase in check["reason"]


# derived: route denominator includes requests that ran one insert
def test_unbatched_write_loop_uses_route_request_denominator_and_unknown_time() -> None:
    run = Run()
    for _ in range(2):
        writes = [sql("insert into orders values (?)", duration=-1) for _ in range(5)]
        missing = [sql("insert into orders values (?)") for _ in range(5)]
        for row in missing:
            del row["durationNanos"]
        run.request(*writes, *missing)
    for _ in range(3):
        run.request(sql("insert into orders values (?)"))
    finding = run.findings("unbatched-write-loop")[0]
    assert "2 of 5 requests" in finding["sentence"]
    detail = InsightsService(run.journal).insight(str(finding["id"]))
    assert detail["rows"][0]["cells"][3] == "unknown"
    assert "Total time is unknown." in finding["limitations"]


# ported: UnbatchedWriteLoopTests.aBatchNineSinglesAndAnUnbatchedReadAreNotLoops
def test_unbatched_write_loop_does_not_count_batch_larger_than_one() -> None:
    run = Run()
    for _ in range(2):
        run.request(
            *(sql("insert into orders values (?)") for _ in range(9)),
            sql("insert into orders values (?)", batch=10),
            sql("select * from audit where id = ?"),
        )
    assert not run.findings("unbatched-write-loop")


# ported: UnbatchedWriteLoopTests.anExecutedWriteWithUnknownBatchSizeIsNeverCountedAndTheCheckSaysSo
def test_unbatched_write_loop_batch_size_zero_is_uncounted() -> None:
    run = Run()
    for _ in range(2):
        run.request(*(sql("insert into orders values (?)", batch=0) for _ in range(10)))
    report = InsightsService(run.journal).report()
    assert any("no recorded batch size" in str(check) for check in report["checks"])


# derived: metadata-only exposure withholds request ids required by both SQL kinds
def test_sql_kinds_are_not_applicable_when_request_ids_are_withheld() -> None:
    run = Run(Exposure.METADATA_ONLY)
    run.request(sql("select id from orders"), *(sql("select id from items") for _ in range(10)))
    report = InsightsService(run.journal).report()
    statuses = {check["kind"]: check for check in report["checks"]}
    for kind in ("repeated-selects", "unbatched-write-loop"):
        assert statuses[kind]["status"] == "NOT_APPLICABLE"
        assert "Request ids are withheld" in statuses[kind]["reason"]
