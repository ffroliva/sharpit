"""Runtime Insights K1: ``route-time-breakdown`` over the journal's ``http`` and ``sql`` sources.

Requests go through the http producer (``http_event``) and statements through the production listener path
(``dispatch.deliver``), never hand-made rows. A statement is placed on its request by the monotonic clocks both
producers read (``perf_counter_ns``: the http event's ``startNanos`` and the sql event's ``completedNanos``), as BootUI
does; sharpit marks no handler phases, so the rest of the request is unattributed (BootUI's WebFlux shape).
"""

from __future__ import annotations

import json
import secrets
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
from sharpit.engine.collectors.insights.requests import RequestIndex, project_requests
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
Sql = tuple[float, float]  # (offset in ms from the request's start, duration in ms)
PERF0 = 5_000_000_000  # where the monotonic clock stands at the first request
SEC = 1_000_000_000
SUB_MS = 600_000  # a request starts 0.6 ms into a wall-clock millisecond, as a real one almost never starts on one


def _ns(ms: float) -> int:
    return round(ms * MS)


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

    def request(
        self,
        route: str,
        duration_ms: float,
        *statements: Sql,
        status: int = 200,
        text: str = "select 1",
        path: str | None = None,
        matched: bool = True,
        monotonic_start: bool = True,
    ) -> str:
        method, label = route.split(" ", 1)
        template = label if matched else None  # unmatched: the route label comes from the masked path
        self.requests += 1
        request_id = f"r{self.requests}"
        start_ns, epoch_ns = PERF0 + self.requests * SEC, (BASE_MS + self.requests * 1000) * MS + SUB_MS
        shown = path if path is not None else label.replace("{id}", "42")
        info = RequestInfo(
            request_id, self.ctx.context_id, method, shown, template, start_ns, start_ns + _ns(duration_ms)
        )
        token = REQUEST.set(info)
        try:
            for offset, ms in statements:
                self.statement(start_ns + _ns(offset), _ns(ms), epoch_ns + _ns(offset + ms), text)
        finally:
            REQUEST.reset(token)
        event = http_event(info, [], epoch_ns, status, template)
        if not monotonic_start:
            event.pop("startNanos", None)  # a producer that does not write BootUI's ``timing.startNanos``
        self.journal.offer(event)
        return request_id

    def statement(self, started_ns: int, duration_ns: int, ended_epoch_ns: int, text: str) -> None:
        event = SqlEvent("sqlalchemy", text, None, False, None, started_ns, duration_ns, -1, None, None, None,
                         Dialect.POSTGRESQL)  # fmt: skip
        clock = SimpleNamespace(time_ns=lambda: ended_epoch_ns)
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
        "Its warm median is under 20 ms, so it is not prominent."
    )  # no sharpit producer records authorization, so the text must not claim its share


def test_an_unsplit_route_that_is_not_slow_says_so(run: Run) -> None:
    for _ in range(6):
        run.request("GET /api/tiny", 7)
    unlisted = run.findings()["GET /api/tiny"].unlisted
    assert unlisted is not None
    assert unlisted == (
        "Its time is not split into phases, since its requests reached no handler sharpit marks or named nothing at "
        "all, and its warm median is under 20 ms."
    )


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


def test_a_request_without_a_monotonic_start_is_left_out_and_said_never_placed_by_wall_clock(run: Run) -> None:
    for _ in range(6):
        run.request(ORDERS, 40, (10, 10))
    run.request(
        ORDERS, 40, (10, 10), monotonic_start=False
    )  # has epochMillis and a duration, as a wall-clock guess needs
    row = run.rows()[ORDERS]
    assert "over 5 requests" in str(row["sentence"])
    assert "1 request had no monotonic start and is left out." in row["limitations"]


def test_a_hand_made_request_with_only_an_id_is_left_out_too(run: Run) -> None:
    for _ in range(6):
        run.request(ORDERS, 40, (10, 10))
    run.journal.offer({"source": "http", "requestId": "rx", "route": ORDERS})
    assert "1 request had no monotonic start and is left out." in run.rows()[ORDERS]["limitations"]


def _share(run: Run, row: Row, phase: str) -> int:
    cells = {c[0]: c for c in run.cells(row)}
    assert phase in cells, f"no {phase} row in {sorted(cells)}"
    return int(cells[phase][2].removesuffix(" %"))


def test_sequential_sub_millisecond_statements_read_their_true_sql_share_with_no_overlap(run: Run) -> None:
    for _ in range(6):  # 20 statements of 0.2 ms, one every 0.3 ms, in a 6 ms request: 4 ms of 6 is SQL
        run.request("GET /api/many", 6, *((i * 0.3, 0.2) for i in range(20)))
    row = run.rows()["GET /api/many"]
    assert abs(_share(run, row, "SQL") - 67) <= 5
    assert "Overlapping calls, counted once above" not in {c[0] for c in run.cells(row)}


def test_a_statement_straddling_the_request_end_is_clipped_to_it(run: Run) -> None:
    for _ in range(6):
        run.request("GET /api/late", 10, (8, 5), (-3, 4))  # [8,13] ends 3 ms after the request; [-3,1] began 3 before
    row = run.rows()["GET /api/late"]
    assert {c[0]: c[1:] for c in run.cells(row)}["SQL"] == ["15", "30 %", "3.0"]  # (2 + 1) ms a request, five warm


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
    assert seeded["whatToCheck"][0] == (
        "Most of the time is SQL: compare its statements in SQL Trace, and see Repeated SELECTs."
    )
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
    canary = secrets.token_hex(16)  # in the sql text (never read) and in an unmatched path: the route label's source
    for _ in range(6):
        run.request("GET /api/orders", 40, (10, 10), text=f"select * from t where x = '{canary}'",
                    path=f"/api/orders/{canary}", matched=False)  # fmt: skip
    subjects = list(run.rows())
    assert len(subjects) == 1, subjects
    assert subjects[0].startswith("GET /api/orders/")
    assert canary not in subjects[0]
    assert canary not in json.dumps(run.report())
    assert canary not in json.dumps(InsightsService(run.journal).insight(str(run.report()["observations"][0]["id"])))


def _bounds(run: Run, route: str, durations: list[int]) -> Any:
    for ms in durations:
        run.request(route, ms)
    return run.findings()[route]


@pytest.mark.parametrize(
    ("durations", "listed"),
    [
        ([100, 100, 100], True),  # cold + 2 warm at the 100 ms edge
        ([100, 99, 99], False),  # the warm median is 99 ms
        ([100, 100], False),  # a single warm request is never listed
    ],
)
def test_a_few_slow_warm_requests_are_listed_from_two_warm_at_100_ms(
    run: Run, durations: list[int], listed: bool
) -> None:
    finding = _bounds(run, "GET /api/few", durations)
    assert finding.sufficient is False
    assert (finding.unlisted is None) is listed


@pytest.mark.parametrize(("median_ms", "prominent"), [(20, True), (19, False)])
def test_a_split_route_is_prominent_from_a_20_ms_warm_median(run: Run, median_ms: int, prominent: bool) -> None:
    finding = _bounds(run, "GET /api/edge", [median_ms] * 7)
    assert (finding.unlisted is None) is prominent


@pytest.mark.parametrize("median_ms", [4, 25])
def test_a_split_route_always_points_at_its_slowest_exemplar(run: Run, median_ms: int) -> None:
    for _ in range(7):
        run.request("GET /api/split", median_ms, (1, median_ms / 2))
    finding = run.findings()["GET /api/split"]
    assert finding.sufficient is True
    assert finding.what_to_check[-1] == "Open the slowest exemplar request in Live Activity to see its timeline."


def test_a_too_slow_few_points_at_the_slowest_exemplar_and_asks_for_more_requests(run: Run) -> None:
    finding = _bounds(run, "GET /api/slowfew", [300, 300, 300])
    assert finding.what_to_check == [
        "Open the slowest exemplar request in Live Activity to see its timeline.",
        "Exercise the route a few more times to read where its time goes.",
    ]


def test_eligible_counts_warm_placed_requests_only(run: Run) -> None:
    run.request(ORDERS, 40)  # cold
    for _ in range(5):
        run.request(ORDERS, 40, (10, 10))
    run.request(ORDERS, 40, monotonic_start=False)  # unplaced
    for _ in range(3):
        run.request("GET /api/other", 12)
    run.request("GET /api/other", 12)
    evaluate = next(k for k in KINDS if k.kind == KIND).evaluate
    assert evaluate is not None
    assert evaluate(project(run.journal)).eligible == 5 + 3


@pytest.mark.parametrize(("statuses", "every"), [([401] * 6, True), ([401, 403, 401, 401, 403, 403], True),
                                                 ([401, 401, 401, 200, 401, 401], False)])  # fmt: skip
def test_the_security_filter_note_needs_every_warm_request_rejected(run: Run, statuses: list[int], every: bool) -> None:
    for status in statuses:
        run.request("GET /api/guarded", 7, status=status)
    sentence = str(run.rows()["GET /api/guarded"]["sentence"])
    assert ("Every one was answered 401 or 403" in sentence) is every


def test_evicted_statements_of_a_retained_request_are_named() -> None:
    run = Run(runtime_journal_max_events=12)
    try:
        for _ in range(10):
            run.request(ORDERS, 40, (10, 10))
        limitations = run.rows()[ORDERS]["limitations"]
        assert any("SQL statements" in text and "evicted" in text and "unattributed" in text for text in limitations)
    finally:
        run.close()


def test_no_eviction_no_evicted_statement_limitation(run: Run) -> None:
    for _ in range(6):
        run.request(ORDERS, 40, (10, 10))
    assert not any("evicted" in text for text in run.rows()[ORDERS]["limitations"])


def test_two_kinds_in_one_report_build_the_request_join_once() -> None:
    run = Run()
    try:
        for _ in range(6):
            run.request(ORDERS, 40, (10, 10), (20, 5))
        snapshot = project(run.journal)
        events = len(snapshot.records["sql"])
        assert events == 12
        calls: list[object] = []
        owner = RequestIndex.owner

        def counting(self: RequestIndex, event: dict[str, object]) -> object:
            calls.append(event)
            return owner(self, event)

        with patch.object(RequestIndex, "owner", counting):
            project_requests(snapshot, "sql", "ai")  # K1's join
            project_requests(snapshot, "ai")  # K9's join
            project_requests(snapshot, "sql", "ai")
        assert len(calls) == events  # every sql event joined once; there are no ai events
    finally:
        run.close()
