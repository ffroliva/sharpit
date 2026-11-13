"""A request whose events were evicted is left out and counted (BootUI ``RuntimeInsightsService.visibleEntries``).

The journal is one bounded ring and a request's sql and exception events are offered before its http event, so under
eviction the ring drops the statements first and keeps the http event. BootUI leaves such a request out whole, counts
it, and names the count in the check's reason; sharpit projected it with part of its evidence gone (K4a review probe).
Times are explicit milliseconds so the 16 ms slack never makes a neighbouring request look lost.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, cast

import pytest

from sharpit.engine.capture import journal as journal_module
from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.finding import Evaluation
from sharpit.engine.collectors.insights.requests import RequestIndex, project_requests
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.collectors.insights.snapshot import project
from sharpit.engine.masking import Exposure, Masker

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


def only_http(journal: RuntimeJournal, started_at: int) -> None:
    info = RequestInfo("r-only", "ctx", "GET", "/api/items", None, 0, started_at * 1_000_000)
    journal.offer(http_event(info, [], started_at * 1_000_000, 200, "/api/items"))


def after_losing_a_statement_at(lost_at: int, started_at: int) -> RuntimeJournal:
    """A one-event ring: the statement started at ``lost_at`` is evicted by the http event of the request."""
    journal = RuntimeJournal(max_events=1)
    journal.offer({**sql("select 1", lost_at), "requestId": "gone"})
    only_http(journal, started_at)
    return journal


# ported: EvidenceRing.add (v2.3.0 l.92-93): an event larger than the whole byte bound is lost, and moves the horizon
def test_an_event_larger_than_the_whole_byte_bound_moves_the_horizon_and_leaves_its_request_out() -> None:
    journal = RuntimeJournal(max_bytes=1_500)
    request(journal, 1, 1_000, sql("update t set n = ? /* " + "x" * 5_000 + " */", 1_005))
    request(journal, 2, 2_000, sql("select id from products", 2_005))
    assert journal.view([])[3] == 1_005


def test_an_oversize_statement_leaves_its_request_out_of_the_safe_method_dml_check() -> None:
    journal = RuntimeJournal(max_bytes=1_500)
    request(journal, 1, 1_000, sql("update t set n = ? /* " + "x" * 5_000 + " */", 1_005))
    request(journal, 2, 2_000, sql("select id from products", 2_005))
    row = check(journal, SAFE)
    assert ONE_LEFT_OUT in str(row["reason"])  # after "The journal dropped 1 events ..."
    assert row["eligibleRequests"] == 1  # r2 only


# BootUI v2.3.0 offers nothing to the ring while paused or for a source it does not record, and calls no ring.lost
# there (RuntimeJournal.offer l.265-270; the lost() calls on those paths arrive after 2.3.0): the horizon stays put.
def test_a_statement_refused_while_recording_is_paused_does_not_move_the_horizon() -> None:
    journal = RuntimeJournal()
    journal.suspend()
    journal.offer({**sql("update t set n = ?", 1_005), "requestId": "r1"})
    assert journal.view([])[3] is None


def test_a_statement_of_a_source_not_configured_does_not_move_the_horizon() -> None:
    journal = RuntimeJournal(sources=["http"])
    journal.offer({**sql("update t set n = ?", 1_005), "requestId": "r1"})
    assert journal.view([])[3] is None


def test_the_window_counts_only_the_requests_it_still_judges() -> None:
    journal = RuntimeJournal(max_events=3)
    request(journal, 1, 1_000, sql("select 1", 1_005))
    request(journal, 2, 2_000, sql("select 2", 2_005))
    assert InsightsService(journal).report()["window"]["requests"] == 1  # type: ignore[index]  # r1 is left out


def test_the_loss_horizon_never_moves_past_now() -> None:
    journal = RuntimeJournal(max_events=1)
    journal.offer({**sql("select 1", 4_000_000_000_000), "requestId": "future"})  # year 2096
    only_http(journal, 1_000)
    assert journal.view([])[3] <= time.time_ns() // 1_000_000  # type: ignore[operator]


# ported: EvidenceRing.lost (v2.3.0 l.155-172) only raises the horizon, clamped to now at loss time; a clock stepped
# back afterwards leaves it where it was, as in BootUI. The audit's NTP scenario is BootUI's own behaviour.
def test_a_clock_stepped_back_after_a_loss_keeps_the_horizon(monkeypatch: pytest.MonkeyPatch) -> None:
    journal = RuntimeJournal(max_events=1)
    monkeypatch.setattr(time, "time_ns", lambda: 10_000 * 1_000_000)
    journal.offer({**sql("select 1", 9_000), "requestId": "a"})
    journal.offer({**sql("select 2", 9_500), "requestId": "b"})  # evicts a: horizon 9_000
    monkeypatch.setattr(time, "time_ns", lambda: 1_000 * 1_000_000)  # stepped back ten minutes' worth
    journal.offer({**sql("select 3", 900), "requestId": "c"})  # evicts b: min(9_500, now 1_000) is below the horizon
    assert journal.view([])[3] == 9_000


# BootUI v2.3.0 RuntimeJournal.enqueue (l.337-338) counts a refused or failed offer and stamps droppedAt of its source;
# it calls no ring.lost, so the horizon stays put. Sharpit has no per-source lostMillis (deviation row, not ported).
def test_a_failed_or_reentrant_offer_does_not_move_the_horizon() -> None:
    journal = RuntimeJournal()
    journal.offer({"source": 5, "requestId": "r1", "startedAt": 1_005})  # not a source: failed
    journal.count_dropped("reentrant")
    assert journal.view([])[3] is None


def test_a_request_starting_within_the_slack_of_the_horizon_is_left_out() -> None:
    journal = after_losing_a_statement_at(1_000, 1_016)  # ported: LOSS_HORIZON_SLACK_MILLIS = 16, inclusive
    assert ONE_LEFT_OUT in str(check(journal, ROUTE_TIME)["reason"])


def test_a_request_starting_after_the_slack_is_judged() -> None:
    journal = after_losing_a_statement_at(1_000, 1_017)
    assert LEFT_OUT not in str(check(journal, ROUTE_TIME)["reason"])


@pytest.mark.parametrize("kind", [SAFE, ERRORS, ROUTE_TIME])
def test_every_request_left_out_is_not_request_ids_withheld(kind: str) -> None:
    journal = after_losing_a_statement_at(1_000, 1_005)
    assert "withheld" not in str(check(journal, kind)["reason"])


def test_a_request_starting_inside_the_slack_is_left_out() -> None:
    journal = after_losing_a_statement_at(1_000, 1_010)  # 10 ms after the horizon: only the slack leaves it out
    assert ONE_LEFT_OUT in str(check(journal, ROUTE_TIME)["reason"])


def traced_event(source: str, trace: str, at: int) -> Row:
    return {"source": source, "traceId": trace, "thread": "MainThread", "epochMillis": at}


def two_requests_one_trace_after_a_loss() -> RuntimeJournal:
    """r1 (trace t) lost a statement and is left out; a trace-only event of r1 stays; r2 (also trace t) is judged."""
    journal = RuntimeJournal(max_events=4)
    info = RequestInfo("r1", "ctx", "GET", "/api/items", None, 0, 1_000_000_000)
    journal.offer({**sql("select 1", 1_005), "requestId": "r1"})
    journal.offer({**http_event(info, [], 1_000_000_000, 200, "/api/items"), "traceId": "t"})
    journal.offer(traced_event("sql", "t", 1_010))  # a trace-only event of r1
    info = RequestInfo("r2", "ctx", "GET", "/api/items", None, 0, 5_000_000_000)
    journal.offer({**http_event(info, [], 5_000_000_000, 200, "/api/items"), "traceId": "t"})
    journal.offer({**sql("select 2", 5_005), "requestId": "r2"})  # evicts r1's statement: r1 is left out
    return journal


# ported: RuntimeInsightsService.visibleEntries (v2.3.0): `owner = aiCallOwners.ownerOf(event)`, then the event is
# skipped when `incomplete.contains("request:" + owner)`; the owner is resolved among ALL retained requests
def test_a_trace_only_event_of_a_left_out_request_joins_no_later_request_of_the_same_trace() -> None:
    snapshot = project(two_requests_one_trace_after_a_loss())
    judged = project_requests(snapshot, "sql")
    assert [r.request_id for r in judged] == ["r2"]
    assert [e["epochMillis"] for e in judged[0].children["sql"] if e.get("requestId") is None] == []


def test_the_trace_only_event_of_a_left_out_request_is_not_counted_as_linked_by_trace() -> None:
    coverage = next(
        c for c in InsightsService(two_requests_one_trace_after_a_loss()).report()["coverage"] if c["source"] == "sql"
    )  # type: ignore[attr-defined]
    assert coverage["byTraceId"] == 0


def two_requests_the_first_left_out() -> RuntimeJournal:
    """Ring of 4: r1's first statement is evicted, so r1 is left out while its second statement stays retained."""
    journal = RuntimeJournal(max_events=4)
    journal.offer({**sql("select 1a", 1_005), "requestId": "r1"})
    journal.offer({**sql("select 1b", 1_006), "requestId": "r1"})
    info = RequestInfo("r1", "ctx", "GET", "/api/items", None, 0, 1_000_000_000)
    journal.offer(http_event(info, [], 1_000_000_000, 200, "/api/items"))
    journal.offer({**sql("select 2", 2_005), "requestId": "r2"})
    info = RequestInfo("r2", "ctx", "GET", "/api/items", None, 0, 2_000_000_000)
    journal.offer(http_event(info, [], 2_000_000_000, 200, "/api/items"))
    return journal


# ported: InsightsSnapshot.of (v2.3.0) builds `coverage` and `httpRequests()` from the VISIBLE entries, so a request
# left out is in neither
def test_coverage_counts_only_the_events_of_requests_still_judged() -> None:
    rows = {c["source"]: c for c in InsightsService(two_requests_the_first_left_out()).report()["coverage"]}  # type: ignore[attr-defined]
    assert (rows["http"]["events"], rows["sql"]["events"]) == (1, 1)


def test_coverage_and_the_window_agree_on_the_requests_judged() -> None:
    report = InsightsService(two_requests_the_first_left_out()).report()
    http = next(c for c in report["coverage"] if c["source"] == "http")  # type: ignore[attr-defined]
    assert http["events"] == report["window"]["requests"]  # type: ignore[index]


def test_a_report_with_no_request_left_out_asks_no_event_whether_it_was(monkeypatch: pytest.MonkeyPatch) -> None:
    journal = RuntimeJournal()
    journal.offer({**sql("select 1", 1_005), "requestId": "r1"})
    asked: list[object] = []
    real = RequestIndex.left_out_event
    monkeypatch.setattr(RequestIndex, "left_out_event", lambda self, event: asked.append(event) or real(self, event))
    InsightsService(journal).report()
    assert asked == []


class HostEvent(dict[str, object]):
    """An event whose ``get`` is host code: it must never run while the journal's lock is held."""

    held: list[bool]
    journal: RuntimeJournal

    def get(self, key: str, default: object = None) -> object:  # type: ignore[override]
        self.held.append(self.journal._owned())  # noqa: SLF001
        return super().get(key, default)


def host_event(journal: RuntimeJournal, held: list[bool], body: Row) -> HostEvent:
    event = HostEvent(body)
    event.held, event.journal = held, journal
    return event


def test_the_oversize_branch_reads_the_stored_copy_never_the_host_event_under_the_lock() -> None:
    journal = RuntimeJournal(max_bytes=1_500)
    held: list[bool] = []
    big = {**sql("update t set n = ? /* " + "x" * 5_000 + " */", 1_005), "requestId": "r1"}
    journal.offer(host_event(journal, held, big))
    held.clear()  # whatever the copy read before the lock
    journal.offer(host_event(journal, held, big))
    assert True not in held
    assert journal.view([])[3] == 1_005  # and the horizon still moved


def test_an_eviction_is_accounted_before_the_horizon_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    journal = RuntimeJournal(max_events=1)
    journal.offer({**sql("select 1", 1_005), "requestId": "r1"})

    def explode(*_: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(journal_module, "_lost_start", explode)
    journal.offer({**sql("select 2", 2_005), "requestId": "r2"})  # counted failed, never raised into the host
    assert journal.status()["evictedEvents"] == 1  # r1 left the ring, so it is counted
    assert journal._bytes == 0  # noqa: SLF001  # and its bytes are given back


def test_clearing_walks_the_cleared_events_outside_the_ring_lock() -> None:
    journal = RuntimeJournal()
    held: list[bool] = []
    journal.offer_flat(host_event(journal, held, {**sql("select 1", 1_005), "requestId": "r1"}), 100)  # type: ignore[arg-type]
    held.clear()
    journal.discard()
    assert held
    assert True not in held
    assert journal.view([])[3] == 1_005


# the branches of the loss horizon and of the left-out gate that no test above reaches
def test_a_check_that_reads_no_request_names_no_left_out_request() -> None:
    kind = SimpleNamespace(
        kind="no-requests", title="t", minimum_tier="TIME_WINDOW", reads=frozenset(), optional_reads=frozenset(),
        uses_requests=False, evaluate=lambda _snapshot: Evaluation(0),
    )  # fmt: skip
    report = InsightsService(after_losing_a_statement_at(1_000, 1_005), [kind], 5, None, cast(Any, lambda: None))
    assert LEFT_OUT not in str(report.report()["checks"][0]["reason"])  # type: ignore[index]


def test_a_request_with_no_start_time_is_left_out_once_anything_was_lost() -> None:
    record: Row = {"requestId": "r1", "route": "GET /x", "traceId": None, "method": "GET", "status": 200}
    assert RequestIndex((record,), 1_000).left_out == 1  # it cannot be placed: fail closed


def test_a_request_with_no_start_time_is_judged_while_nothing_was_lost() -> None:
    record: Row = {"requestId": "r1", "route": "GET /x", "traceId": None, "method": "GET", "status": 200}
    assert RequestIndex((record,), None).left_out == 0


@pytest.mark.parametrize("ids", [{"executionId": "e1"}, {"traceId": "t1"}], ids=["execution", "trace"])
def test_an_evicted_execution_or_trace_only_event_moves_the_horizon(ids: Row) -> None:
    journal = RuntimeJournal(max_events=1)
    journal.offer({"source": "sql", "epochMillis": 1_000, **ids})
    journal.offer({"source": "sql", "epochMillis": 2_000, **ids})
    assert journal.view([])[3] == 1_000


def test_clearing_events_that_name_no_request_no_execution_and_no_trace_moves_no_horizon() -> None:
    journal = RuntimeJournal()
    journal.offer({"source": "log", "epochMillis": 1_000, "traceId": None})
    journal.discard()
    assert journal.view([])[3] is None


def test_clearing_never_lowers_a_horizon_an_eviction_already_set() -> None:
    journal = RuntimeJournal(max_events=1)
    journal.offer({"source": "sql", "epochMillis": 5_000, "requestId": "r1"})
    journal.offer({"source": "sql", "epochMillis": 1_000, "requestId": "r2"})  # evicts r1: horizon 5000
    journal.discard()  # clears r2, which started earlier
    assert journal.view([])[3] == 5_000


def test_at_metadata_only_a_loss_reads_as_withheld_ids_never_as_a_clean_check() -> None:
    journal = RuntimeJournal(max_events=1, masker=Masker(Exposure.METADATA_ONLY, True))
    journal.offer({**sql("select 1", 1_005), "requestId": "gone"})
    only_http(journal, 1_010)  # evicts the statement
    reason = str(check(journal, ROUTE_TIME)["reason"])
    assert "withheld" in reason
