from __future__ import annotations

from typing import Any

import pytest

from engine.testsession.tsfakes import NODE, call_test, part, passed_run, source
from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.testsession.facts import SessionFacts
from sharpit.engine.testsession.outcome import MergedFacts, exit_fails, merge, session_status

NO_APP = "no application: pass --sharpit-app or call sharpit.install in the tests"


def _status(*parts: SessionFacts, missing: tuple[str, ...] = (), **kwargs: Any) -> tuple[str, list[str]]:
    options: dict[str, Any] = {"allow_unknown": False, "max_unattributed": 10.0, "advisors_enabled": True}
    return session_status(merge(list(parts), list(missing)), **{**options, **kwargs})


def _failing(attempt: int = 1, worker: str = "gw0", node: str = NODE, *, dismissed: bool = False) -> Any:
    test = call_test(node, worker=worker, attempt=attempt)
    finding = Finding("sharpit.max-queries", "test-runtime", "HIGH", node, "m", node, dismissed=dismissed)
    test.findings = [finding.to_dto()]
    return test


def _run(status_findings: list[Finding], *, app: str = "A#1", limitations: list[str] | None = None) -> AdvisorRun:
    evidence = {"usable": True, "coverageComplete": not limitations, "limitations": limitations or []}
    return AdvisorRun.of("rest-api", status_findings, evidence, app=app)


def test_status_pass() -> None:
    assert _status(part()) == ("pass", [])


def test_status_fail_beats_unknown() -> None:
    assert _status(part(tests=[_failing()], sources=[])) == ("fail", ["1 test failed sharpit gates"])


def test_status_fail_counts_tests_in_plural() -> None:
    tests = [_failing(node="a"), _failing(node="b")]
    assert _status(part(tests=tests)) == ("fail", ["2 tests failed sharpit gates"])


def test_status_dismissed_gate_finding_passes() -> None:
    assert _status(part(tests=[_failing(dismissed=True)])) == ("pass", [])


def test_status_advisor_failed() -> None:
    finding = Finding("RAPI-MAP-001", "rest-api", "HIGH", "GET /x", "m")
    medium = Finding("RAPI-MAP-002", "rest-api", "MEDIUM", "GET /y", "m")
    assert _status(part(advisor_runs=[_run([finding, medium])])) == (
        "fail",
        ["advisor 'rest-api' found 1 finding at or above HIGH"],
    )
    assert _status(part(advisor_runs=[_run([finding, medium])]), fail_on="MEDIUM")[1] == [
        "advisor 'rest-api' found 2 findings at or above MEDIUM"
    ]


def test_status_no_source_unknown() -> None:
    assert _status(part(sources=[source("exceptions")])) == ("unknown", ["no SQL source attached"])
    assert _status(part(sources=[source(attached=False, reason="not installed"), source("exceptions")]))[1] == [
        "no SQL source attached",
        "source 'sqlalchemy' not attached in worker gw0",
    ]


def test_status_none_attributed_unknown() -> None:
    reasons = _status(part(tests=[], unattributed=5))[1]
    assert reasons == [
        "no SQL statement was attributed to a test",
        "100.0% of SQL statements were not attributed to a test (limit 10%)",
    ]


def test_status_no_sql_passes_with_warning() -> None:
    sql_free = part(tests=[call_test(queries=0)])
    assert _status(sql_free) == ("pass", [])
    assert "no SQL statement was executed" in merge([sql_free], []).warnings


def test_status_no_sql_with_early_alias_unknown() -> None:
    sql_free = part(tests=[call_test(queries=0)], aliases=["app.db.connect"])
    assert _status(sql_free) == (
        "unknown",
        ["SQL may have run outside capture: early connect alias in app.db.connect"],
    )
    early = part(tests=[call_test(queries=0)], preexisting=2)
    assert _status(early)[1] == ["SQL may have run outside capture: 2 connections opened before capture started"]


def test_status_early_alias_with_attributed_sql_stays_pass() -> None:
    assert _status(part(aliases=["app.db.connect"], preexisting=1)) == ("pass", [])


def test_status_unattributed_share_over_limit_unknown() -> None:
    assert _status(part(tests=[call_test(queries=8)], unattributed=2))[1] == [
        "20.0% of SQL statements were not attributed to a test (limit 10%)"
    ]
    assert _status(part(tests=[call_test(queries=9)], unattributed=1)) == ("pass", [])
    assert _status(part(tests=[call_test(queries=8)], unattributed=2), max_unattributed=25.0) == ("pass", [])


def test_status_untraced_driver_unknown() -> None:
    reasons = _status(part(untraced_drivers={"asyncpg"}))[1]
    assert reasons == ["untraced database driver in use: asyncpg"]
    merged = merge([part(untraced_drivers={"asyncpg"})], [])
    assert {k: merged.sources[-1][k] for k in ("name", "attached")} == {"name": "asyncpg", "attached": False}


def test_status_driver_dual_use_limitation() -> None:
    """A driver that is also an engine's driver stays a listed limitation and does not change the status."""
    dual = part(untraced_drivers={"aiosqlite"}, engine_drivers={"aiosqlite"})
    assert _status(dual) == ("pass", [])
    limitations = next(s for s in merge([dual], []).sources if s["name"] == "sqlalchemy")["limitations"]
    assert limitations == ["aiosqlite calls outside SQLAlchemy are not traced"]


def test_status_driver_seen_in_other_worker_covered() -> None:
    """Session conditions are evaluated on the merged facts: worker 1's engine covers worker 0's import."""
    assert _status(part("gw0", untraced_drivers={"asyncpg"}), part("gw1", engine_drivers={"asyncpg"})) == ("pass", [])


@pytest.mark.parametrize(
    ("module", "engines", "covered"),
    [
        ("MySQLdb", {"mysqldb"}, True),
        ("pymysql", {"aiomysql"}, True),
        ("pymysql", {"pymysql"}, True),
        ("pymysql", {"mysqldb"}, False),
        ("psycopg", {"psycopg_async"}, True),
        ("psycopg2", {"psycopg"}, False),
        ("oracledb", {"oracledb"}, True),
        ("pyodbc", {"pyodbc"}, True),
        ("asyncpg", set(), False),
    ],
)
def test_driver_name_table(module: str, engines: set[str], covered: bool) -> None:
    reasons = _status(part(untraced_drivers={module}, engine_drivers=engines))[1]
    assert (reasons == []) is covered


def test_status_advisor_unknown() -> None:
    limited = _run([], limitations=["an opaque mounted app"])
    assert _status(part(advisor_runs=[limited])) == (
        "unknown",
        ["advisor 'rest-api' could not assess: an opaque mounted app"],
    )


def test_status_no_application_is_unknown_for_rest_api() -> None:
    assert _status(part(advisor_runs=[])) == ("unknown", [f"advisor 'rest-api' could not assess: {NO_APP}"])


def test_status_no_advisors_does_not_make_unknown() -> None:
    assert _status(part(advisor_runs=[]), advisors_enabled=False) == ("pass", [])


def test_status_missing_worker_unknown() -> None:
    assert _status(part(), missing=("gw1",)) == ("unknown", ["worker gw1 reported no sharpit facts"])
    workers = merge([part()], ["gw1"]).workers
    assert workers == [{"id": "gw0", "status": "ok"}, {"id": "gw1", "status": "missing"}]


def test_status_any_worker_unattached_unknown() -> None:
    lost = part("gw1", sources=[source(attached=False, reason="boom"), source("exceptions")])
    merged = merge([part("gw0"), lost], [])
    assert next(s for s in merged.sources if s["name"] == "sqlalchemy")["attached"] is False
    assert _status(part("gw0"), lost)[1] == ["source 'sqlalchemy' not attached in worker gw1"]


def test_status_exception_source_lost_unknown() -> None:
    lost = part(exceptions_source_ok=False, sources=[source(), source("exceptions", attached=False, reason="no hook")])
    assert _status(lost) == ("unknown", ["exception capture was lost: no hook"])


def test_merge_advisor_per_app_unknown_wins() -> None:
    limited = _run([], limitations=["partial"], app="A#1")
    merged = merge(
        [part("gw0", advisor_runs=[passed_run("A#1"), passed_run("B#2")]), part("gw1", advisor_runs=[limited])], []
    )
    by_app = {run.app: run.status for run in merged.advisor_runs}
    assert by_app == {"A#1": "UNKNOWN", "B#2": "PASSED"}


def test_merge_advisor_findings_deduplicated_by_fingerprint() -> None:
    finding = Finding("RAPI-MAP-001", "rest-api", "HIGH", "GET /x", "m")
    runs = [_run([finding]), _run([finding])]
    merged = merge([part("gw0", advisor_runs=runs[:1]), part("gw1", advisor_runs=runs[1:])], [])
    assert len(merged.advisor_runs) == 1
    assert len(merged.advisor_runs[0].findings) == 1
    assert merged.advisor_runs[0].status == "FAILED"


def test_merge_rerun_last_attempt_decides() -> None:
    flaky = part(tests=[_failing(attempt=1), call_test(attempt=2)])
    assert _status(flaky) == ("pass", [])
    worse = part(tests=[call_test(attempt=1), _failing(attempt=2)])
    assert _status(worse) == ("fail", ["1 test failed sharpit gates"])
    merged = merge([flaky], [])
    assert len(merged.tests) == 2
    assert [f["fingerprint"] for f in merged.findings] == []


def test_merge_dist_each_entries() -> None:
    """``--dist each``: one entry per worker, each decides on its own."""
    merged = merge([part("gw0", tests=[_failing(worker="gw0")]), part("gw1", tests=[_failing(worker="gw1")])], [])
    assert len(merged.tests) == 2
    assert session_status(merged, allow_unknown=False, max_unattributed=10.0, advisors_enabled=True) == (
        "fail",
        ["2 tests failed sharpit gates"],
    )
    assert len(merged.findings) == 1


def test_merge_sums_counters() -> None:
    merged = merge([part("gw0", unattributed=2, filtered=3), part("gw1", unattributed=1, filtered=4)], [])
    assert merged.unattributed == 3
    assert merged.filtered == 7


def test_merge_top_unattributed_sorted_and_summed() -> None:
    merged = merge([part("gw0", top_unattributed={"a": 1, "b": 5}), part("gw1", top_unattributed={"a": 9})], [])
    assert merged.top_unattributed == [{"sql": "a", "count": 10}, {"sql": "b", "count": 5}]


@pytest.mark.parametrize(
    ("status", "allow", "fails"),
    [("pass", False, False), ("fail", True, True), ("unknown", False, True), ("unknown", True, False)],
)
def test_exit_fails(status: str, allow: bool, fails: bool) -> None:
    assert exit_fails(status, allow) is fails


def test_empty_merge_is_a_merged_facts() -> None:
    assert isinstance(merge([], []), MergedFacts)
