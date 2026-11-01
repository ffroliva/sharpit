"""Builders shared by the test-session tests: SQL events, tags and a session part that passes."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.engine.sources.dispatch import SqlEvent
from sharpit.engine.testsession.facts import PhaseFacts, SessionFacts, TestFacts, TestKey
from sharpit.engine.testsession.gates import Budget, evaluate_test
from sharpit.engine.testsession.outcome import merge, session_status
from sharpit.engine.testsession.report import render
from sharpit.engine.testsession.sink import TestSessionSink

NODE = "tests/test_owners.py::test_list"


def event(
    sql: str = "SELECT 1", *, duration_ns: int = 1000, parameters: object = (), batch: int | None = None
) -> SqlEvent:
    return SqlEvent("sqlalchemy", sql, parameters, batch is not None, batch, 0, duration_ns, 1, None, None, None)


def run_phase(sink: TestSessionSink, node_id: str, attempt: int, phase: str, *sql: str) -> None:
    for statement in sql:
        sink.on_sql(event(statement), (node_id, attempt, phase))


def source(
    name: str = "sqlalchemy", *, attached: bool = True, reason: str | None = None, **extra: Any
) -> dict[str, Any]:
    return {"name": name, "attached": attached, "reason": reason, "limitations": [], **extra}


def passed_run(app: str = "App#00000001") -> AdvisorRun:
    evidence = {"usable": True, "coverageComplete": True, "limitations": []}
    return AdvisorRun("rest-api", "PASSED", (), evidence, None, app)


def call_test(node_id: str = NODE, *, worker: str = "gw0", attempt: int = 1, queries: int = 3) -> TestFacts:
    return TestFacts(TestKey(node_id, worker, attempt), phases={"call": PhaseFacts(queries=queries)}, outcome="passed")


def part(worker: str = "gw0", **overrides: Any) -> SessionFacts:
    """A session part that yields ``pass``; a test overrides the one thing it is about."""
    base: dict[str, Any] = {
        "tests": [call_test(worker=worker)],
        "sources": [source(), source("exceptions")],
        "advisor_runs": [passed_run()],
    }
    return SessionFacts(worker, **{**base, **overrides})


def selects(fingerprint: str, count: int, sql: str = "SELECT * FROM pets WHERE owner_id = ?") -> PhaseFacts:
    return PhaseFacts(queries=count, selects=Counter({fingerprint: count}), sql_of={fingerprint: sql})


GATES = {
    "maxQueriesPerTest": None,
    "nPlusOneThreshold": 5,
    "failOnSeverity": "HIGH",
    "allowUnknown": False,
    "maxUnattributedPercent": 10,
}
NOW = 1_761_955_200_000


def render_parts(*parts: SessionFacts, missing: tuple[str, ...] = (), advisors_enabled: bool = True) -> dict[str, Any]:
    merged = merge(list(parts), list(missing))
    status, reasons = session_status(
        merged, allow_unknown=False, max_unattributed=10.0, advisors_enabled=advisors_enabled
    )
    return render(merged, status, reasons, gates=GATES, version="0.3.0", now_ms=NOW, advisors_enabled=advisors_enabled)


def busy_part(worker: str = "gw0") -> SessionFacts:
    """Two tests (one over its query budget with an N+1), an exception, unattributed and filtered statements."""
    sink = TestSessionSink(worker)
    attempt = sink.begin_test(NODE)
    run_phase(sink, NODE, attempt, "setup", "PRAGMA foreign_keys=ON", "INSERT INTO owners VALUES (1)")
    run_phase(sink, NODE, attempt, "call", *[f"SELECT * FROM pets WHERE owner_id = {i}" for i in range(8)])
    sink.on_exception(ValueError("boom"), "logging", (NODE, attempt, "call"))
    assert sink.current_test is not None
    sink.current_test.outcome = "failed"
    sink.current_test.budget = Budget(5, False, 0)
    found = evaluate_test(sink.current_test, sink.current_test.budget, 5, ())
    sink.current_test.findings = [f.to_dto() for f in found]
    sink.end_test()
    other = "tests/test_owners.py::test_get"
    attempt = sink.begin_test(other)
    run_phase(sink, other, attempt, "call", "SELECT * FROM owners")
    assert sink.current_test is not None
    sink.current_test.outcome = "passed"
    sink.end_test()
    sink.on_sql(event("SELECT * FROM jobs WHERE state = 'x'"), None)
    facts = sink.facts
    facts.sources = [source(), source("exceptions")]
    facts.advisor_runs = [passed_run()]
    return facts
