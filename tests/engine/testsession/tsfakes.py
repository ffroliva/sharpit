"""Builders shared by the test-session tests: SQL events, tags and a session part that passes."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.engine.sources.dispatch import SqlEvent
from sharpit.engine.testsession.facts import PhaseFacts, SessionFacts, TestFacts, TestKey
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
