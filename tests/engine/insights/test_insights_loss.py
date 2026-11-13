"""A request whose events were evicted is left out and counted (BootUI ``RuntimeInsightsService.visibleEntries``).

The journal is one bounded ring and a request's sql and exception events are offered before its http event, so under
eviction the ring drops the statements first and keeps the http event. BootUI leaves such a request out whole, counts
it, and names the count in the check's reason; sharpit projected it with part of its evidence gone (K4a review probe).
Times are explicit milliseconds so the 16 ms slack never makes a neighbouring request look lost.
"""

from __future__ import annotations

import pytest

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.service import InsightsService

LEFT_OUT = "started before events the journal evicted or cleared"
ONE_LEFT_OUT = f"1 request or execution {LEFT_OUT}, so it is left out: some of its events may be missing."
SAFE, ERRORS, ROUTE_TIME = "safe-method-dml", "errors-behind-2xx", "route-time-breakdown"
Row = dict[str, object]


def sql(text: str, started_at: int) -> Row:
    return {
        "source": "sql", "sql": text, "traceId": None, "thread": "MainThread", "durationNanos": 1_000_000,
        "startedAt": started_at, "dataSource": None, "failed": False, "phase": None, "completedNanos": 20_000_000,
        "codePathStamp": 0, "provenance": "EXECUTION", "batchSize": 1, "callSite": None,
    }  # fmt: skip


def exception(started_at: int) -> Row:
    return {
        "source": "exception", "exceptionClass": "IllegalStateException", "signature": "IllegalStateException",
        "groupId": "g-1", "types": [], "epochMillis": started_at,
    }  # fmt: skip


def request(journal: RuntimeJournal, number: int, started_at: int, child: Row, route: str = "GET /api/items") -> None:
    method, _, template = route.partition(" ")
    info = RequestInfo(f"r{number}", "ctx", method, template, None, 0, started_at * 1_000_000)
    journal.offer({**child, "requestId": info.id})
    journal.offer(http_event(info, [], started_at * 1_000_000, 200, template))


def check(journal: RuntimeJournal, kind: str) -> Row:
    return next(c for c in InsightsService(journal).report()["checks"] if c["kind"] == kind)  # type: ignore[attr-defined]


# the K4a review probe (2026-11-12): r1 runs an UPDATE, r2 a SELECT, and the ring holds three events
def test_safe_method_dml_a_request_that_lost_its_statement_is_left_out_not_reported_clean() -> None:
    journal = RuntimeJournal(max_events=3)
    request(journal, 1, 1_000, sql("update product_views set n = n + ?", 1_005))
    request(journal, 2, 2_000, sql("select id from products", 2_005))
    row = check(journal, SAFE)
    assert row["eligibleRequests"] == 1  # only r2 is judged: r1 lost its UPDATE
    assert row["reason"] == ONE_LEFT_OUT


def test_errors_behind_2xx_a_request_whose_exception_was_evicted_is_left_out() -> None:
    journal = RuntimeJournal(max_events=3)
    request(journal, 1, 1_000, exception(1_005))
    request(journal, 2, 2_000, exception(2_005))
    row = check(journal, ERRORS)
    assert ONE_LEFT_OUT in str(row["reason"])
    assert row["eligibleRequests"] == 1


def test_route_time_breakdown_a_request_that_lost_a_statement_is_left_out() -> None:
    journal = RuntimeJournal(max_events=3)
    request(journal, 1, 1_000, sql("select 1", 1_005))
    request(journal, 2, 2_000, sql("select 2", 2_005))
    assert ONE_LEFT_OUT in str(check(journal, ROUTE_TIME)["reason"])


def test_a_request_that_started_after_the_loss_is_still_judged() -> None:
    journal = RuntimeJournal(max_events=3)
    request(journal, 1, 1_000, sql("select 1", 1_005))
    request(journal, 2, 2_000, sql("select 2", 2_005))
    request(journal, 3, 3_000, sql("update t set n = ?", 3_005))  # r1's http event is evicted, r2's statement too
    row = check(journal, SAFE)
    assert row["eligibleRequests"] == 1  # r3
    assert row["reason"] == ONE_LEFT_OUT  # r2


def test_the_report_limitation_names_the_left_out_requests() -> None:
    journal = RuntimeJournal(max_events=3)
    request(journal, 1, 1_000, sql("select 1", 1_005))
    request(journal, 2, 2_000, sql("select 2", 2_005))
    assert ONE_LEFT_OUT in InsightsService(journal).report()["limitations"]  # type: ignore[operator]


@pytest.mark.parametrize("kind", [SAFE, ERRORS, ROUTE_TIME])
def test_a_journal_that_lost_nothing_leaves_nothing_out(kind: str) -> None:
    journal = RuntimeJournal()
    request(journal, 1, 1_000, sql("update t set n = ?", 1_005))
    request(journal, 2, 2_000, sql("select 2", 2_005))
    reason = check(journal, kind)["reason"]
    assert LEFT_OUT not in str(reason)


def test_the_journal_remembers_the_start_of_the_latest_event_it_lost() -> None:
    journal = RuntimeJournal(max_events=2)
    journal.offer({**sql("select 1", 1_005), "requestId": "r1"})
    journal.offer({**sql("select 2", 2_005), "requestId": "r2"})
    journal.offer({**sql("select 3", 3_005), "requestId": "r3"})
    assert journal.view([])[3:] == (1_005,)  # the latest LOST start, never a retained one ([3:]: no IndexError crash)


def test_the_loss_horizon_is_none_while_the_journal_lost_nothing() -> None:
    journal = RuntimeJournal()
    journal.offer({**sql("select 1", 1_005), "requestId": "r1"})
    assert journal.view([])[3:] == (None,)


def test_an_evicted_event_of_no_request_or_trace_does_not_move_the_horizon() -> None:
    journal = RuntimeJournal(max_events=1)
    journal.offer({"source": "log", "epochMillis": 1_000, "traceId": None})
    journal.offer({"source": "log", "epochMillis": 2_000, "traceId": None})
    assert journal.view([])[3:] == (None,)


def test_clearing_the_journal_moves_the_horizon_past_what_it_dropped() -> None:
    journal = RuntimeJournal()
    journal.offer({**sql("select 1", 1_005), "requestId": "r1"})
    journal.discard()
    assert journal.view([])[3:] == (1_005,)
