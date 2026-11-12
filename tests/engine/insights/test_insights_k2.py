"""Runtime Insights K2: ``errors-behind-2xx`` over the journal; ``exception-hotspots`` and
``framework-warnings-by-route`` answer not applicable while no producer writes their ``exception`` and ``log`` sources.

The http events are what ``http_event`` writes. The ``transaction``, ``exception``, ``log`` and ``rest-client`` events
have no producer yet: the tests record those sources by widening ``PRODUCED_SOURCES`` and seed BootUI's payload field
names (``rolledBack``, ``nested``, ``method``, ``exceptionClass``, ``level``, ``logger``, ``status``, ``failed``,
``authority``), which a future producer must write.
"""

from __future__ import annotations

import json

import pytest

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.masking import Exposure, Masker

KIND = "errors-behind-2xx"
ORDERS = "GET /api/orders/{id}"
EVIDENCE_SOURCES = frozenset({"http", "transaction", "exception", "log", "rest-client"})
ILLEGAL_STATE = "java.lang.IllegalStateException"
REAL_PRODUCED_SOURCES = snapshot_module.PRODUCED_SOURCES  # before the autouse widening
Row = dict[str, object]


@pytest.fixture(autouse=True)
def evidence_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", EVIDENCE_SOURCES)


def tx(method: str | None, *, nested: bool = False, rolled_back: bool = True) -> Row:
    return {"source": "transaction", "method": method, "rolledBack": rolled_back, "nested": nested}


def exception(cls: str) -> Row:
    return {"source": "exception", "exceptionClass": cls}


def log(level: str, logger: str | None = "app.orders") -> Row:
    return {"source": "log", "level": level, "logger": logger}


def downstream(status: int | None, failed: bool = False) -> Row:
    return {
        "source": "rest-client", "method": "GET", "authority": "stock:8080", "status": status, "failed": failed,
    }  # fmt: skip


class Run:
    def __init__(self, exposure: Exposure = Exposure.MASKED) -> None:
        self.journal = RuntimeJournal(masker=Masker(exposure, True))
        self.requests = 0

    def request(self, status: int, *children: Row, route: str = ORDERS) -> str:
        self.requests += 1
        request_id = f"r{self.requests}"
        method, _, template = route.partition(" ")
        info = RequestInfo(request_id, "ctx", method, template.replace("{id}", "42"), None, 0, 30_000_000)
        for child in children:
            self.journal.offer({**child, "requestId": request_id})
        self.journal.offer(http_event(info, [], 1_000_000, status, template))
        return request_id

    def report(self) -> Row:
        return InsightsService(self.journal).report()

    def check(self, kind: str = KIND) -> Row:
        return next(c for c in self.report()["checks"] if c["kind"] == kind)  # type: ignore[attr-defined]

    def rows(self, kind: str = KIND) -> list[Row]:
        return [o for o in self.report()["observations"] if o["kind"] == kind]  # type: ignore[attr-defined]


# ported: JournalFactObservationsTests.errorsBehind2xxCountsSeveralRequestsInPlainWords
def test_errors_behind_2xx_counts_several_requests_in_plain_words() -> None:
    run = Run()
    for _ in range(2):
        run.request(200, exception(ILLEGAL_STATE), tx("OrderService.place"))
    rows = run.rows()
    assert len(rows) == 1
    (row,) = rows
    assert row["sentence"] == (
        f"`{ORDERS}` answered 2xx in 2 of 2 successful requests: 2 requests whose transaction rolled back, "
        "2 requests that recorded an exception."
    )


# ported: JournalFactObservationsTests.errorsBehind2xxOrderEvidenceByStrengthAndReportRecoveredRequestsApart (the
# unrecovered half only: sharpit has no recovered group)
def test_errors_behind_2xx_seeded_case_and_counterexample() -> None:
    run = Run()
    run.request(200, exception(ILLEGAL_STATE), tx("OrderService.place"))
    run.request(200, downstream(404, failed=True), tx("StockService.reserve", nested=True))  # status wins over failed
    run.request(500, exception(ILLEGAL_STATE))  # not a 2xx
    run.request(201, downstream(503))
    run.request(200, log("ERROR"), log("WARN"))
    rows = run.rows()
    assert len(rows) == 1
    (row,) = rows
    assert row["id"].startswith(f"{KIND}:")  # type: ignore[attr-defined]
    assert row["sentence"] == (
        f"`{ORDERS}` answered 2xx in 3 of 4 successful requests: 1 request whose transaction rolled back, "
        "1 request that recorded an exception, 1 request that wrote an ERROR log, 1 request that received a 5xx or "
        "failed downstream call."
    )
    assert row["exemplarRequestIds"] == ["r1", "r5", "r4"]
    assert len(row["whatToCheck"]) == 2  # type: ignore[arg-type]
    assert row["affected"] == 3
    assert row["eligible"] == 4
    assert run.check()["eligibleRequests"] == 4


def test_errors_behind_2xx_a_clean_success_is_not_a_finding() -> None:
    run = Run()
    run.request(200, tx("OrderService.place", nested=True), downstream(404), log("WARN"))
    assert run.rows() == []
    assert run.check()["status"] == "EVALUATED"


# ported: JournalFactObservationsTests.errorsBehind2xxSayWhichEvidenceTheJournalDoesNotRecord
def test_errors_behind_2xx_says_which_evidence_the_journal_does_not_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"http", "exception"}))
    run = Run()
    run.request(200, exception(ILLEGAL_STATE))
    check = run.check()
    assert check["status"] == "EVALUATED"
    assert "Without the transaction source" in str(check["reason"])
    assert any("Without the log source" in t for t in run.rows()[0]["limitations"])  # type: ignore[attr-defined]
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"http", "sql"}))
    assert run.check()["status"] == "NOT_APPLICABLE"


def evidence_cells(run: Run) -> list[str]:
    rows = run.rows()
    assert len(rows) == 1
    detail = InsightsService(run.journal).insight(str(rows[0]["id"]))
    return [str(r["cells"][2]) for r in detail["rows"]]  # type: ignore[index]


@pytest.mark.parametrize(
    ("child", "shown"),
    [
        (downstream(404, failed=True), None),  # BootUI: a status wins over ``failed``
        (downstream(None, failed=True), "downstream 5xx or failure: failed GET stock:8080"),
        (downstream(None, failed=False), None),
        (downstream(500), "downstream 5xx or failure: 500 GET stock:8080"),
        (tx("OrderService.place", rolled_back=False), None),  # a committed transaction is no evidence
        (tx(None), "rolled-back transaction: transaction"),  # BootUI's fallback text for a method-less transaction
    ],
)
# ported: JournalFactObservationsTests.errorsBehind2xxOrderEvidenceByStrengthAndReportRecoveredRequestsApart (the
# unrecovered half only: sharpit has no recovered group)
def test_errors_behind_2xx_evidence_rules(child: Row, shown: str | None) -> None:
    run = Run(Exposure.FULL)  # MASKED masks ``authority`` by key: the text rules are read as recorded
    run.request(200, child)
    if shown is None:
        assert run.rows() == []
    else:
        assert evidence_cells(run) == [shown]


@pytest.mark.parametrize(("status", "counted"), [(199, False), (200, True), (299, True), (300, False)])
def test_errors_behind_2xx_only_2xx_counts(status: int, counted: bool) -> None:
    run = Run()
    run.request(status, exception(ILLEGAL_STATE))
    assert [r["eligible"] for r in run.rows()] == ([1] if counted else [])


def test_errors_behind_2xx_lists_at_most_three_distinct_items_per_evidence() -> None:
    run = Run()
    names = ["a.A", "a.B", "a.C", "a.D"]
    run.request(200, *(exception(n) for n in names), exception("a.A"))
    assert evidence_cells(run) == ["exception: A, B, C"]  # ``.distinct().limit(3)``


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY])
def test_errors_behind_2xx_secret_in_a_read_field_is_never_shown(exposure: Exposure) -> None:
    secret = "Bearer " + "abcdef0123456789"
    run = Run(exposure)
    run.request(
        200,
        {**exception(secret), "method": secret},
        {**log("ERROR", logger=secret)},
        {**downstream(503), "authority": secret, "method": secret},
        tx(secret),
    )
    if exposure is Exposure.MASKED:
        rows = run.rows()
        assert len(rows) == 1
        dumped = json.dumps([run.report(), InsightsService(run.journal).insight(str(rows[0]["id"]))])
    else:
        assert run.rows() == []  # METADATA_ONLY withholds the request ids: no row, so no row text
        dumped = json.dumps(run.report())
    assert "abcdef0123456789" not in dumped


def test_errors_behind_2xx_real_install_evaluates_now_that_exception_is_produced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", REAL_PRODUCED_SOURCES)
    assert "exception" in REAL_PRODUCED_SOURCES  # W5a P-exception
    run = Run()
    run.request(200, exception(ILLEGAL_STATE))
    assert run.check()["status"] == "EVALUATED"


def test_errors_behind_2xx_without_any_evidence_producer_is_not_applicable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", REAL_PRODUCED_SOURCES - EVIDENCE_SOURCES | {"http"})
    run = Run()
    run.request(200)
    check = run.check()
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == (
        "The runtime journal records none of the transaction, exception, log, and rest-client sources, or their "
        "panels are disabled."
    )


def test_errors_behind_2xx_not_applicable_when_http_unproduced(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Run()
    run.request(200, exception(ILLEGAL_STATE))
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"exception", "log"}))
    check = run.check()
    assert check["status"] == "NOT_APPLICABLE"
    assert "http source" in str(check["reason"])


def test_errors_behind_2xx_is_not_applicable_when_ids_are_withheld() -> None:
    run = Run(Exposure.METADATA_ONLY)  # the journal itself nulls ``requestId`` at this exposure
    run.request(200, exception(ILLEGAL_STATE))
    assert run.journal.records("http")[0]["requestId"] is None
    check = run.check()
    assert check["status"] == "NOT_APPLICABLE"
    assert "SHARPIT_EXPOSE_VALUES" in str(check["reason"])


def test_errors_behind_2xx_text_uses_journal_fields_only() -> None:
    run = Run()
    secret = "Bearer " + "abcdef0123456789"
    run.request(200, {**exception(ILLEGAL_STATE), "message": secret, "stack": secret})
    rows = run.rows()
    assert len(rows) == 1
    detail = InsightsService(run.journal).insight(str(rows[0]["id"]))
    assert "abcdef0123456789" not in json.dumps([run.report(), detail])
    assert detail["rows"] == [{"cells": ["r1", "200", "exception: IllegalStateException"]}]


@pytest.mark.parametrize(
    ("kind", "source"), [("exception-hotspots", "exception"), ("framework-warnings-by-route", "log")]
)
def test_unproduced_source_kinds_answer_not_applicable(kind: str, source: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"http", "ai", "sql"}))
    run = Run()
    run.request(200)
    check = run.check(kind)
    assert check["status"] == "NOT_APPLICABLE"
    assert (
        check["reason"] == f"The runtime journal does not record the {source} source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."
    )
    assert run.rows(kind) == []


def test_errors_behind_2xx_real_install_evaluates_over_the_produced_log_source_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", REAL_PRODUCED_SOURCES - {"exception"})
    assert "log" in REAL_PRODUCED_SOURCES  # W5a P-log
    run = Run()
    run.request(200, log("ERROR"))
    check = run.check()
    assert check["status"] == "EVALUATED"
    assert len(run.rows()) == 1
