"""Runtime Insights K2b: ``exception-hotspots`` and ``framework-warnings-by-route`` over the journal.

The ``exception`` and ``log`` events are what ``capture/exceptions.py`` and ``capture/logtail.py`` write: ``groupId``,
``signature``, ``exceptionClass``, ``types``; ``logger``, ``level``, ``template``. Per-finding listing is read from the
kind's own ``evaluate`` (the service applies the kind-wide default list on top, as BootUI's ``assumeValidated`` tests
switch off).
"""

from __future__ import annotations

import json
import logging
from importlib import import_module
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.collectors.insights.snapshot import project
from sharpit.engine.masking import Exposure, Masker

HOTSPOTS, WARNINGS = "exception-hotspots", "framework-warnings-by-route"
MODULES = {HOTSPOTS: "exception_hotspots", WARNINGS: "framework_warnings_by_route"}
ORDERS = "GET /api/orders/{id}"
API = "/sharpit/api/runtime-insights"
ILLEGAL_STATE = "IllegalStateException"
Row = dict[str, Any]
CANARY = "abcdef0123456789"
POOL = "sqlalchemy.pool.impl.QueuePool"
LEAK = "The garbage collector is trying to clean up non-checked-in connection"


def exc(cls: str, sig: str | None = None, *types: str) -> Row:
    sig = sig or cls
    return {"source": "exception", "exceptionClass": cls, "signature": sig, "groupId": f"g-{sig}", "types": list(types)}


def log(logger: str, level: str, template: str | None) -> Row:
    return {"source": "log", "logger": logger, "level": level, "template": template}


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

    def unowned(self, *events: Row) -> None:
        for event in events:
            self.journal.offer({**event, "requestId": None})

    def evaluate(self, kind: str) -> Evaluation:
        module = import_module(f"sharpit.engine.collectors.insights.kinds.{MODULES[kind]}")
        evaluate = getattr(module, "evaluate", None)
        assert evaluate is not None, f"{kind} is not implemented"
        return evaluate(project(self.journal))

    def report(self) -> Row:
        return InsightsService(self.journal).report()

    def check(self, kind: str) -> Row:
        return next(c for c in self.report()["checks"] if c["kind"] == kind)

    def rows(self, kind: str) -> list[Row]:
        return [o for o in self.report()["observations"] if o["kind"] == kind]

    def detail(self, row: Row) -> Row:
        return InsightsService(self.journal).insight(str(row["id"]))

    def dump(self, kind: str) -> str:
        details = [self.detail(r) for r in self.rows(kind)]
        return json.dumps([self.report(), details])


def by_subject(findings: list[Finding], subject: str) -> list[Finding]:
    return [f for f in findings if f.subject == subject]


def group_of(finding: Finding) -> str:
    return finding.rows[0][3]


# ported: JournalFactObservationsTests.exceptionHotspotsListFailedNewAndRedirectGroupsAndCountThoseOnlyBehind4xx
# (no previous run in sharpit: a group not seen behind a failure or a redirect is never "new")
def test_exception_hotspots_seeded_case_and_counterexample() -> None:
    run = Run()
    run.request(500, exc("IllegalStateException", "s500"))
    run.request(400, exc("IllegalArgumentException", "s400"))
    run.request(404, exc("IllegalArgumentException", "s400"))
    run.request(200, exc("IllegalStateException", "s200"))
    run.request(400, exc("IllegalStateException", "s200"))
    run.request(302, exc("IllegalStateException", "s302"))
    run.request(400, exc("UnsupportedOperationException", "fresh"))
    run.request(200)  # a clean request: eligible, not affected
    evaluation = run.evaluate(HOTSPOTS)
    assert evaluation.eligible == 8
    groups = {group_of(f): f for f in by_subject(evaluation.findings, ORDERS)}
    assert groups["g-s500"].listed is True  # behind a 5xx
    assert groups["g-s302"].listed is True  # behind a redirect, which no other check reports
    assert groups["g-s400"].unlisted == (
        "It was recorded only behind 4xx responses, which are usually intended, and is counted in the row Behind 4xx "
        "responses."
    )
    assert groups["g-fresh"].unlisted == groups["g-s400"].unlisted  # no previous run to call it new
    assert groups["g-s200"].unlisted == (
        "It was recorded only behind 2xx and 4xx responses: Errors behind 2xx responses reports the 2xx ones."
    )
    counted = by_subject(evaluation.findings, "Behind 4xx responses")[0]
    assert counted.listed is True
    assert counted.sentence == (
        "2 exception groups on 1 route were recorded only behind 4xx responses: 3 occurrences in 3 requests."
    )
    assert (counted.eligible, counted.affected) == (0, 0)  # ranks after the groups it does not collapse
    assert counted.columns == ["Route", "Exception", "Requests", "Occurrences", "Statuses"]
    assert counted.rows == [
        [ORDERS, "IllegalArgumentException", "2", "2", "400, 404"],
        [ORDERS, "UnsupportedOperationException", "1", "1", "400"],
    ]
    assert evaluation.findings[-1] is counted
    s500 = groups["g-s500"]
    assert s500.sentence == f"`{ORDERS}` recorded `IllegalStateException` in 1 of 8 requests (1 occurrence)."
    assert (s500.eligible, s500.affected) == (8, 1)
    assert s500.columns == ["Request", "Status", "Occurrences", "Exception group"]
    assert s500.rows == [["r1", "500", "1", "g-s500"]]
    assert s500.exemplar_request_ids == ["r1"]
    assert s500.what_to_check == ["Open the exception group to read its message and stack trace."]


# ported: JournalFactObservationsTests.aRouteWhoseEveryRequestAnswers4xxWithOneExceptionIsItsOwnRowNotCountedBehind4xx
def test_exception_hotspots_a_route_that_always_answers_4xx_is_its_own_row() -> None:
    run = Run()
    put = "PUT /api/admin/users/{login}"
    for _ in range(4):
        run.request(400, exc("EmailAlreadyUsedException", "email"), route=put)
    for _ in range(3):
        run.request(200)
    run.request(400, exc("IllegalArgumentException", "bad"))
    run.request(404, exc("IllegalArgumentException", "bad"))
    findings = run.evaluate(HOTSPOTS).findings
    (always,) = by_subject(findings, put)
    assert always.listed is True
    assert "in 4 of 4 requests" in always.sentence
    assert always.what_to_check[0].startswith(
        "Every request to this route, or nearly, answered 4xx with this exception"
    )
    (orders,) = by_subject(findings, ORDERS)
    assert orders.unlisted is not None
    assert not any(c.startswith("Every request to this route") for c in orders.what_to_check)
    (counted,) = by_subject(findings, "Behind 4xx responses")
    assert counted.sentence.startswith("1 exception group on 1 route was recorded only behind 4xx responses")


# ported: JournalFactObservationsTests.oneRejectedRequestIsCountedBehind4xxEvenWhenItIsTheRoutesOnlyOne
def test_exception_hotspots_one_rejected_request_is_counted_behind_4xx() -> None:
    run = Run()
    put = "PUT /api/admin/users/{login}"
    run.request(400, exc("Taken", "email"), route=put)
    findings = run.evaluate(HOTSPOTS).findings
    assert by_subject(findings, put)[0].unlisted is not None
    assert by_subject(findings, "Behind 4xx responses")[0].listed is True


# ported: JournalFactObservationsTests.wellKnownFrameworkExceptionsCarryTheirSpecificCheckBeforeTheGenericOne
def test_exception_hotspots_a_known_exception_carries_its_check_before_the_generic_one() -> None:
    run = Run()
    run.request(500, exc("sqlalchemy.exc.PendingRollbackError", "rb", "sqlalchemy.exc.PendingRollbackError"))
    (finding,) = run.evaluate(HOTSPOTS).findings
    assert len(finding.what_to_check) == 2
    assert "marked failed" in finding.what_to_check[0]
    assert finding.what_to_check[1] == "Open the exception group to read its message and stack trace."


# ported: JournalFactObservationsTests.exceptionChecksPreferCausesAndIncludeSubtypeAdviceAcrossOccurrencesOfOneGroup
def test_exception_hotspots_checks_prefer_causes_and_list_at_most_two() -> None:
    run = Run()
    wrapper = "app.errors.WrappedError"
    detached, integrity = "sqlalchemy.orm.exc.DetachedInstanceError", "sqlalchemy.exc.IntegrityError"
    stale = "sqlalchemy.orm.exc.StaleDataError"
    run.request(500, exc(wrapper, "wrapped", detached, wrapper))  # the deepest cause first
    run.request(500, exc(wrapper, "wrapped", "app.DuplicateKey", integrity, wrapper))
    run.request(500, exc(wrapper, "wrapped", stale, wrapper))
    run.request(500, exc("RuntimeError", "pool", "app.DriverConnectionError", "sqlalchemy.exc.TimeoutError"))
    wrapped, pool = run.evaluate(HOTSPOTS).findings
    assert len(wrapped.what_to_check) == 3
    assert "selectinload" in wrapped.what_to_check[0]
    assert "constraint" in wrapped.what_to_check[1]
    assert wrapped.what_to_check[-1].startswith("Open the exception group")
    assert any("first two" in text for text in wrapped.limitations)
    assert "pool timed out" in pool.what_to_check[0]


def test_exception_hotspots_say_that_sharpit_compares_with_no_previous_run() -> None:
    run = Run()
    run.request(500, exc(ILLEGAL_STATE))
    (finding,) = run.evaluate(HOTSPOTS).findings
    assert "previous run" in " ".join(finding.limitations)


def test_exception_hotspots_group_by_signature_else_group_id_and_skip_an_event_with_neither() -> None:
    run = Run()
    run.request(500, exc("A", "same"), {**exc("B", "same")}, {"source": "exception", "exceptionClass": "NoKey"})
    run.request(500, {**exc("C"), "signature": None, "groupId": "gid"})
    findings = run.evaluate(HOTSPOTS).findings
    assert sorted(f.sentence.split("`")[3] for f in findings) == ["A", "C"]
    assert findings[0].sentence.endswith("(2 occurrences).")


def test_exception_hotspots_a_run_without_exceptions_is_evaluated_and_clean() -> None:
    run = Run()
    run.request(200)
    assert run.rows(HOTSPOTS) == []
    check = run.check(HOTSPOTS)
    assert (check["status"], check["eligibleRequests"]) == ("EVALUATED", 1)


def test_exception_hotspots_without_requests_is_insufficient_not_clean() -> None:
    run = Run()
    run.journal.offer({**exc(ILLEGAL_STATE), "requestId": "gone"})
    assert run.check(HOTSPOTS)["status"] == "INSUFFICIENT"


# the existing K2 test covers the unrecorded source; this one covers the recorded one with ids withheld
def test_exception_hotspots_metadata_only_withholds_and_says_so() -> None:
    run = Run(Exposure.METADATA_ONLY)  # the journal itself nulls ``requestId`` at this exposure
    run.request(500, exc(ILLEGAL_STATE))
    check = run.check(HOTSPOTS)
    assert check["status"] == "NOT_APPLICABLE"
    assert "SHARPIT_EXPOSE_VALUES" in str(check["reason"])
    assert run.rows(HOTSPOTS) == []


def test_exception_hotspots_text_uses_journal_fields_only() -> None:
    run = Run()
    secret = "Bearer " + CANARY
    run.request(500, {**exc(ILLEGAL_STATE), "message": secret, "stack": secret, "args": [secret]})
    rows = run.rows(HOTSPOTS)
    assert len(rows) == 1
    row = rows[0]
    assert CANARY not in run.dump(HOTSPOTS)
    assert row["sentence"] == f"`{ORDERS}` recorded `{ILLEGAL_STATE}` in 1 of 1 request (1 occurrence)."
    assert run.detail(row)["rows"] == [{"cells": ["r1", "500", "1", f"g-{ILLEGAL_STATE}"]}]


# ported: JournalFactObservationsTests.frameworkWarningsAreGroupedPerRouteWithAKnownCodesCheckAndApplicationLoggersAreLeftOut  # noqa: E501
def test_framework_warnings_by_route_seeded_case_and_counterexample() -> None:
    run = Run()
    run.request(200, log(POOL, "WARN", LEAK), log(POOL, "WARN", LEAK))
    run.request(200)
    run.request(200, log("com.example.Orders", "WARN", "Slow order %s"))  # an application logger
    evaluation = run.evaluate(WARNINGS)
    assert evaluation.eligible == 3
    (finding,) = evaluation.findings
    assert finding.sentence == f'`{ORDERS}` logged `WARN` from `QueuePool` in 1 of 3 requests (2 events): "{LEAK}".'
    assert "returned to the pool" in finding.what_to_check[0]
    assert len(finding.what_to_check) == 2
    assert finding.listed is True  # a known message is listed by default
    assert (finding.eligible, finding.affected) == (3, 1)
    assert finding.columns == ["Request", "Status", "Events", "Logger"]
    assert finding.rows == [["r1", "200", "2", POOL]]


# ported: JournalFactObservationsTests.frameworkWarningsListErrorsAndKnownWarningsAndCountErrorsWithoutARequest
# (no "Resolved [" row, and no thread rule: the unowned events are all counted)
def test_framework_warnings_by_route_list_errors_and_known_warnings_and_count_errors_without_a_request() -> None:
    run = Run()
    run.request(200, log("starlette.routing", "WARN", "Odd %s"))
    run.request(400, log("uvicorn.error", "WARN", "Invalid HTTP request received."))
    run.request(500, log("fastapi.routing", "ERROR", "Broke %s"))
    run.unowned(*[log(POOL, "ERROR", "Exception during reset or similar")] * 3)
    run.unowned(
        log("uvicorn.error", "ERROR", "Error parsing request"),
        log("uvicorn.error", "WARN", "Slow request"),  # a WARN without an id is not counted
        log("com.example.Orders", "ERROR", "Application failure %s"),  # not a framework logger
    )
    findings = run.evaluate(WARNINGS).findings
    (unowned,) = by_subject(findings, "No request")
    assert unowned.listed is True
    assert unowned.sentence == (
        "Framework loggers wrote 4 `ERROR` events that carried no request or execution id, from 2 messages; the most "
        "frequent from `QueuePool`, 3 times."
    )
    assert (unowned.eligible, unowned.affected, unowned.exemplar_request_ids) == (0, 4, [])
    assert unowned.columns == ["Logger", "Message", "Events"]
    assert [row[2] for row in unowned.rows] == ["3", "1"]
    assert unowned.rows[0] == [POOL, "Exception during reset or similar", "3"]
    assert any("sharpit keeps no previous-run summary" in text for text in unowned.limitations)
    broke = next(f for f in by_subject(findings, ORDERS) if "Broke" in f.sentence)
    assert broke.listed is True
    odd = next(f for f in by_subject(findings, ORDERS) if "Odd" in f.sentence)
    assert odd.unlisted == "It is a WARN message sharpit has no specific check for."
    invalid = next(f for f in by_subject(findings, ORDERS) if "Invalid HTTP" in f.sentence)
    assert invalid.listed is True
    assert findings[-1] is unowned


# ported: JournalFactObservationsTests.frameworkMessagesThatDifferOnlyByIdsOrPathNumbersAreOneGroup
def test_framework_warnings_by_route_messages_that_differ_only_by_ids_or_path_numbers_are_one_group() -> None:
    base = "2878fa40-6f44-40d9-8381-ae15903c0b3d"
    run = Run()
    for i in range(1, 4):
        run.request(
            500, log("starlette.errors", "ERROR", f"HTTP Request to /api/orders/{40 + i} failed, error id: {base}-{i}")
        )
    run.request(500, log("starlette.errors", "ERROR", "Request body too large"))
    findings = by_subject(run.evaluate(WARNINGS).findings, ORDERS)
    assert len(findings) == 2
    grouped = next(f for f in findings if "HTTP Request" in f.sentence)
    assert grouped.sentence.startswith(f"`{ORDERS}` logged `ERROR` from `errors` in 3 of 4 requests (3 events): ")
    assert "/api/orders/<n> failed, error id: <id>" in grouped.sentence
    assert base not in grouped.sentence
    assert grouped.affected == 3


# ported: JournalFactObservationsTests.aMessageKeyDropsIdsAndNumericPathSegmentsOnly (read through the sentence)
@pytest.mark.parametrize(
    ("template", "shown"),
    [
        (
            "HTTP Request to /api/records/12?page=2 failed, error id: 2878fa40-6f44-40d9-8381-ae15903c0b3d-7",
            "HTTP Request to /api/records/<n>?page=2 failed, error id: <id>",
        ),
        ("trace 4bf92f3577b34da6a3ce929d0e0e4736 broke", "trace <id> broke"),
        (
            "SAWarning: maxResults specified with collection fetch; applying in memory",
            "SAWarning: maxResults specified with collection fetch; applying in memory",
        ),  # codes, words and short hexadecimal-looking text are kept
        ("Pool QueuePool-1 has 10 of 10 connections in use", "Pool QueuePool-1 has 10 of 10 connections in use"),
    ],
)
def test_framework_warnings_by_route_message_key_drops_ids_and_numeric_path_segments_only(
    template: str, shown: str
) -> None:
    run = Run()
    run.request(500, log("starlette.errors", "ERROR", template))
    (finding,) = run.evaluate(WARNINGS).findings
    assert finding.sentence.endswith(f': "{shown}".')


@pytest.mark.parametrize(
    ("logger", "counted"),
    [
        ("uvicorn", True), ("uvicorn.error", True), ("gunicorn.error", True), ("hypercorn.error", True),
        ("starlette", True), ("fastapi.routing", True), ("sqlalchemy.engine.Engine", True), ("alembic.runtime", True),
        ("asyncio", True), ("anyio", True), ("httpx", True), ("httpcore.connection", True),
        ("uvicornx.extra", False), ("app.uvicorn", False), ("fastapi_users", False), ("sqlalchemy2", False),
        ("com.zaxxer.hikari.HikariPool", False), ("org.springframework.web.Some", False), ("app.orders", False),
        ("", False),
    ],
)  # fmt: skip
def test_framework_warnings_by_route_python_framework_loggers_only(logger: str, counted: bool) -> None:
    run = Run()
    run.request(200, log(logger, "ERROR", "Boom"))
    assert bool(run.evaluate(WARNINGS).findings) is counted


def test_framework_warnings_by_route_a_clean_run_is_evaluated_and_clean() -> None:
    run = Run()
    run.request(200, log("app.orders", "WARN", "Slow"))
    assert run.rows(WARNINGS) == []
    assert run.check(WARNINGS)["status"] == "EVALUATED"


def test_framework_warnings_by_route_without_requests_is_insufficient_not_clean() -> None:
    run = Run()
    run.unowned(log(POOL, "WARN", LEAK))
    assert run.check(WARNINGS)["status"] == "INSUFFICIENT"


def test_framework_warnings_by_route_metadata_only_withholds_and_says_so() -> None:
    run = Run(Exposure.METADATA_ONLY)
    run.request(200, log(POOL, "WARN", LEAK))
    check = run.check(WARNINGS)
    assert check["status"] == "NOT_APPLICABLE"
    assert "SHARPIT_EXPOSE_VALUES" in str(check["reason"])
    assert run.rows(WARNINGS) == []


def test_framework_warnings_by_route_text_uses_journal_fields_only() -> None:
    run = Run()
    secret = "Bearer " + CANARY
    run.request(200, {**log(POOL, "WARN", LEAK), "message": secret, "args": [secret], "exceptionClass": "X"})
    rows = run.rows(WARNINGS)
    assert len(rows) == 1
    row = rows[0]
    assert CANARY not in run.dump(WARNINGS)
    assert row["sentence"] == f'`{ORDERS}` logged `WARN` from `QueuePool` in 1 of 1 request (1 event): "{LEAK}".'
    assert run.detail(row)["rows"] == [{"cells": ["r1", "200", "1", POOL]}]


def _client(exposure: str) -> TestClient:
    app = FastAPI()
    log_ = logging.getLogger("uvicorn.error")

    @app.get("/boom")
    def boom() -> None:
        raise ValueError(f"password={CANARY}")

    @app.get("/warn")
    def warn() -> dict[str, bool]:
        log_.warning("pool low for %s", f"password={CANARY}")
        log_.error("pool broke for %s", f"password={CANARY}")
        return {"ok": True}

    install(app, enabled="ON", show_banner=False, config_scan=False, expose_values=exposure)
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), raise_server_exceptions=False)


def _kind(client: TestClient, kind: str) -> tuple[Row, list[Row], str]:
    body = client.get(API).json()
    check = next(c for c in body["checks"] if c["kind"] == kind)
    rows = [o for o in body["observations"] if o["kind"] == kind]
    details = [client.get(f"{API}/insights/{r['id']}").json() for r in rows]
    return check, rows, json.dumps([body, details])


@pytest.mark.parametrize("exposure", ["MASKED", "FULL"])
def test_exception_hotspots_real_install_finds_the_route_that_raises(exposure: str) -> None:
    client = _client(exposure)
    assert client.get("/boom").status_code == 500
    check, rows, dumped = _kind(client, HOTSPOTS)
    assert check["status"] == "EVALUATED"
    (row,) = rows
    assert row["subject"] == "GET /boom"
    assert row["sentence"] == "`GET /boom` recorded `ValueError` in 1 of 1 request (1 occurrence)."
    assert CANARY not in dumped


@pytest.mark.parametrize("exposure", ["MASKED", "FULL"])
def test_framework_warnings_by_route_real_install_finds_the_route_that_logs(exposure: str) -> None:
    client = _client(exposure)
    assert client.get("/warn").status_code == 200
    check, rows, dumped = _kind(client, WARNINGS)
    assert check["status"] == "EVALUATED"
    assert sorted(r["sentence"] for r in rows) == [
        '`GET /warn` logged `ERROR` from `error` in 1 of 1 request (1 event): "pool broke for %s".',
        '`GET /warn` logged `WARN` from `error` in 1 of 1 request (1 event): "pool low for %s".',
    ]
    assert CANARY not in dumped


def test_both_kinds_real_install_metadata_only_says_ids_are_withheld() -> None:
    client = _client("METADATA_ONLY")
    client.get("/boom")
    client.get("/warn")
    for kind in (HOTSPOTS, WARNINGS):
        check, rows, dumped = _kind(client, kind)
        assert check["status"] == "NOT_APPLICABLE"
        assert "SHARPIT_EXPOSE_VALUES" in str(check["reason"])
        assert rows == []
        assert CANARY not in dumped
