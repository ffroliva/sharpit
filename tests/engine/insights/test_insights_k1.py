"""Runtime Insights K1: ``route-time-breakdown`` over the journal's ``http`` and ``sql`` sources.

Requests go through the http producer (``http_event``) and statements through the production listener path
(``dispatch.deliver``), never hand-made rows. sharpit's http event has no monotonic start and no handler marks, so a
statement is placed on its request by wall clock and the rest of the request is unattributed (BootUI's WebFlux shape).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.registry import KINDS
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.collectors.insights.snapshot import project
from sharpit.engine.sources import dispatch
from sharpit.engine.sources.dispatch import SqlEvent
from sharpit.engine.sqltext import Dialect

MS = 1_000_000
KIND = "route-time-breakdown"
BASE_MS = 1_700_000_000_000
ORDERS = "GET /api/orders/{id}"
Row = dict[str, Any]
Sql = tuple[int, int]  # (offset in ms from the request's start, duration in ms)


class Run:
    def __init__(self, sources: tuple[str, ...] = ("http", "sql", "ai"), **options: Any) -> None:
        sqla.detach_all()
        self.handle = install(
            FastAPI(), enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=sources, **options
        )
        self.ctx = self.handle.context
        self.journal: Any = self.ctx.capture.journal
        self.requests = 0

    def close(self) -> None:
        self.handle.uninstall_capture()

    def request(self, route: str, duration_ms: int, *statements: Sql, status: int = 200, text: str = "select 1") -> str:
        method, template = route.split(" ", 1)
        self.requests += 1
        request_id, epoch_ms = f"r{self.requests}", BASE_MS + self.requests * 1000
        info = RequestInfo(
            request_id, self.ctx.context_id, method, template.replace("{id}", "42"), template, 0, duration_ms * MS
        )
        token = REQUEST.set(info)
        try:
            for offset, ms in statements:
                self.statement(epoch_ms + offset + ms, ms, text)
        finally:
            REQUEST.reset(token)
        self.journal.offer(http_event(info, [], epoch_ms * MS, status, template))
        return request_id

    def statement(self, ended_epoch_ms: int, ms: int, text: str) -> None:
        event = SqlEvent("sqlalchemy", text, None, False, None, 0, ms * MS, -1, None, None, None, Dialect.POSTGRESQL)
        clock = SimpleNamespace(time_ns=lambda: ended_epoch_ms * MS)
        with patch.object(dispatch, "time", clock), patch.object(dispatch, "call_site", lambda *_: None):
            dispatch.deliver(event, [self.ctx])

    def report(self) -> Row:
        return InsightsService(self.journal).report()

    def check(self) -> Row:
        return next(c for c in self.report()["checks"] if c["kind"] == KIND)

    def rows(self) -> dict[str, Row]:
        return {str(o["subject"]): o for o in self.report()["observations"] if o["kind"] == KIND}

    def cells(self, row: Row) -> list[list[str]]:
        rows: list[Row] = InsightsService(self.journal).insight(str(row["id"]))["rows"]
        return [r["cells"] for r in rows]

    def findings(self) -> dict[str, Any]:
        evaluate = next(k for k in KINDS if k.kind == KIND).evaluate
        assert evaluate is not None, "route-time-breakdown is still a stub"
        return {f.subject: f for f in evaluate(project(self.journal)).findings}


@pytest.fixture
def run() -> Any:
    current = Run()
    yield current
    current.close()


# ported: RouteTimeBreakdownTests.warmRequestsAreSplitIntoNamedPhasesWithOverlappingCallsCountedOnceAndTheColdRequestApart  # noqa: E501
def test_warm_requests_are_split_into_phases_with_overlapping_calls_counted_once_and_the_cold_request_apart(
    run: Run,
) -> None:
    run.request(ORDERS, 400)
    for _ in range(5):
        run.request(ORDERS, 40, (10, 10), (15, 10))  # [10,20] and [15,25]: 15 ms in the union, 5 ms overlapping
    for _ in range(3):
        run.request("GET /api/customers", 12)
    rows = run.rows()
    orders = rows[ORDERS]
    assert orders["status"] == "OBSERVED"
    assert orders["sentence"] == (
        "`GET /api/orders/{id}`: warm median 40 ms over 5 requests; Unattributed 63 %, SQL 38 %. "
        "First request 400 ms (cold)."
    )
    assert len(orders["exemplarRequestIds"]) == 3
    assert "r1" not in orders["exemplarRequestIds"]
    assert run.cells(orders) == [
        ["SQL", "75", "38 %", "15"], ["Unattributed", "125", "63 %", "25"],
        ["Overlapping calls, counted once above", "25", "", ""],
    ]  # fmt: skip
    customers = rows["GET /api/customers"]
    assert customers["status"] == "INSUFFICIENT"
    assert customers["sentence"] == "`GET /api/customers`: 2 of 5 warm requests needed. First request 12 ms (cold)."


# ported: RouteTimeBreakdownTests.withoutPhasesTheTimeAroundTheCallsIsUnattributed
def test_without_phases_the_time_around_the_calls_is_unattributed(run: Run) -> None:
    for _ in range(6):
        run.request("GET /api/orders", 10, (6, 4))
    row = run.rows()["GET /api/orders"]
    assert row["status"] == "OBSERVED"
    assert "Unattributed 60 %, SQL 40 %" in str(row["sentence"])
    assert "does not tell apart" in row["whatToCheck"][0]
    assert "hottest frames" not in row["whatToCheck"][0]
    assert any("marks no handler or response phase" in text for text in row["limitations"])


# ported: RouteTimeBreakdownTests.withoutPhasesOrRecordedCallsABreakdownSaysItCannotTellWhereTheTimeWent
def test_without_phases_or_recorded_calls_a_breakdown_says_it_cannot_tell_where_the_time_went(run: Run) -> None:
    for _ in range(6):
        run.request("GET /api/greetings/{id}", 7, status=401)
    row = run.rows()["GET /api/greetings/{id}"]
    assert row["status"] == "INSUFFICIENT"
    assert row["sentence"] == (
        "`GET /api/greetings/{id}`: warm median 7.0 ms over 5 requests, none of it in a recorded call; sharpit marks "
        "no phases, so where that time went is not known. Every one was answered 401 or 403, as security filters do "
        "when they reject a request. First request 7.0 ms (cold)."
    )


# ported: RouteTimeBreakdownTests.aFewSlowWarmRequestsAreListedButOneSlowRequestOrAFewFastOnesAreNot
def test_a_few_slow_warm_requests_are_listed_but_one_slow_request_or_a_few_fast_ones_are_not(run: Run) -> None:
    for _ in range(5):
        run.request("GET /api/report", 800)
    for _ in range(2):
        run.request("GET /api/once", 539)
    for _ in range(3):
        run.request("GET /api/quick", 30)
    findings = run.findings()
    report = findings["GET /api/report"]
    assert report.sufficient is False
    assert report.unlisted is None
    assert report.sentence == (
        "`GET /api/report`: warm median 800 ms over 4 requests; phases need 5 warm requests. "
        "First request 800 ms (cold)."
    )
    assert len(report.exemplar_request_ids) == 3
    assert "It has fewer than 5 warm requests" in findings["GET /api/once"].unlisted
    assert "It has fewer than 5 warm requests" in findings["GET /api/quick"].unlisted


# ported: RouteTimeBreakdownTests.onlyProminentRoutesAreListedByDefaultWithAuthorizationAsATrigger
def test_only_a_prominent_route_is_listed_by_its_median(run: Run) -> None:
    for _ in range(6):
        run.request("GET /api/slow", 25, (2, 20))
        run.request("GET /api/fast", 4, (1, 2))
    findings = run.findings()
    assert findings["GET /api/slow"].unlisted is None
    assert findings["GET /api/fast"].unlisted == (
        "Its warm median is under 20 ms, and authorization takes under 20 % of its time and under 50 decisions a "
        "request, so it is not prominent."
    )  # authorization is never recorded, so the clause is BootUI's text for a route with none


def test_an_unsplit_route_that_is_not_slow_says_so(run: Run) -> None:
    for _ in range(6):
        run.request("GET /api/tiny", 7)
    unlisted = run.findings()["GET /api/tiny"].unlisted
    assert unlisted is not None
    assert "Its time is not split into phases" in unlisted


def test_an_evicting_journal_reports_no_cold_request() -> None:
    run = Run(runtime_journal_max_events=8)
    try:
        for _ in range(12):
            run.request(ORDERS, 40)
        row = run.rows()[ORDERS]
        assert "cold" not in str(row["sentence"])
        assert any("evicted older events" in text for text in row["limitations"])
    finally:
        run.close()


def test_a_request_without_a_start_is_left_out_and_said(run: Run) -> None:
    for _ in range(6):
        run.request(ORDERS, 40, (10, 10))
    run.journal.offer({"source": "http", "requestId": "rx", "route": ORDERS})
    row = run.rows()[ORDERS]
    assert "over 5 requests" in str(row["sentence"])
    assert "1 request had no start time and is left out." in row["limitations"]


def test_statements_are_placed_by_wall_clock_and_the_limitation_says_to_the_millisecond(run: Run) -> None:
    for _ in range(6):
        run.request(ORDERS, 40, (10, 10))
    limitations = run.rows()[ORDERS]["limitations"]
    assert any("placed by their wall-clock start to the millisecond" in text for text in limitations)


def test_ai_calls_are_not_placed_and_the_breakdown_says_their_time_is_unattributed(run: Run) -> None:
    from sharpit.engine.collectors.ai.recognizer import ai_journal_event  # noqa: PLC0415

    for _ in range(6):
        request_id = run.request(ORDERS, 40, (10, 10))
        span = SimpleNamespace(
            context=SimpleNamespace(trace_id=1, span_id=7), kind=SimpleNamespace(name="INTERNAL"), name="chat",
            start_time=0, end_time=5 * MS, status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET")),
            attributes={"gen_ai.operation.name": "chat"},
        )  # fmt: skip
        token = REQUEST.set(RequestInfo(request_id, run.ctx.context_id, "GET", "/x", None, 0, None))
        try:
            run.journal.offer(ai_journal_event(span))
        finally:
            REQUEST.reset(token)
    limitations = run.rows()[ORDERS]["limitations"]
    assert any("made AI calls" in text and "unattributed" in text for text in limitations)


def test_route_time_breakdown_seeded_case_and_counterexample(run: Run) -> None:
    for _ in range(6):
        run.request("GET /api/seeded", 30, (5, 20))  # seeded: two thirds of the request is SQL
        run.request("GET /api/counter", 30, (-50, 20))  # counterexample: the statement ran before the request began
    rows = run.rows()
    seeded, counter = rows["GET /api/seeded"], rows["GET /api/counter"]
    assert seeded["status"] == "OBSERVED"
    assert "SQL 67 %" in str(seeded["sentence"])
    assert "SQL Trace" in seeded["whatToCheck"][0] or "does not tell apart" in seeded["whatToCheck"][0]
    assert counter["status"] == "INSUFFICIENT"
    assert "none of it in a recorded call" in str(counter["sentence"])


def test_route_time_breakdown_not_applicable_when_http_unproduced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"sql", "ai"}))
    run = Run()
    try:
        check = run.check()
        assert check["status"] == "NOT_APPLICABLE"
        assert (
            check["reason"] == "The runtime journal does not record the http source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."
        )
    finally:
        run.close()


def test_without_the_sql_source_the_check_says_its_evidence_is_not_counted() -> None:
    run = Run(("http",))
    try:
        for _ in range(6):
            run.request(ORDERS, 40)
        row = run.rows()[ORDERS]
        assert (
            "Without the sql source, which the runtime journal does not record, its evidence is not counted."
            in (row["limitations"])
        )
    finally:
        run.close()


def test_http_ids_withheld_by_metadata_only_exposure_are_not_a_clean_nothing_found() -> None:
    run = Run(expose_values="METADATA_ONLY")
    try:
        for _ in range(6):
            run.request(ORDERS, 40, (10, 10))
        check = run.check()
        assert check["status"] == "NOT_APPLICABLE"
        assert "withheld at METADATA_ONLY exposure" in str(check["reason"])
    finally:
        run.close()


def test_route_time_breakdown_text_uses_journal_fields_only(run: Run) -> None:
    canary = "CANARY-sql-literal-5d2e"
    for _ in range(6):
        run.request(ORDERS, 40, (10, 10), text=f"select * from t where x = '{canary}'")
    row = run.rows()[ORDERS]
    assert canary not in json.dumps(run.report())
    assert canary not in json.dumps(InsightsService(run.journal).insight(str(row["id"])))
