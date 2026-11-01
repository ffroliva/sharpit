from __future__ import annotations

import gc
import json
import os

import pytest

from engine.testsession.tsfakes import NODE, event, run_phase
from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.spi import ApiModel
from sharpit.engine.testsession.facts import PhaseFacts, SessionFacts, TestFacts, TestKey
from sharpit.engine.testsession.gates import Budget
from sharpit.engine.testsession.sink import TestSessionSink, report_masker, report_masker_warnings

SECRET = "hunter2-S3CRET"
EMPTY = ApiModel((), (), ())


def _sink() -> TestSessionSink:
    return TestSessionSink("gw0")


def _call(sink: TestSessionSink) -> PhaseFacts:
    assert sink.current_test is not None
    return sink.current_test.phases["call"]


def test_attribution_same_test_counts() -> None:
    """B6: a statement tagged with the running test counts against it, in the tag's phase."""
    sink = _sink()
    attempt = sink.begin_test(NODE)
    run_phase(sink, NODE, attempt, "call", "SELECT * FROM pets", "SELECT * FROM owners")
    run_phase(sink, NODE, attempt, "setup", "INSERT INTO pets VALUES (1)")
    assert _call(sink).queries == 2
    assert sink.current_test is not None
    assert sink.current_test.phases["setup"].queries == 1
    assert sink.facts.unattributed == 0


def test_attribution_no_tag_unattributed() -> None:
    """B6: a statement with no tag (a dropped context, aiosqlite's thread) is reported, never gated."""
    sink = _sink()
    sink.begin_test(NODE)
    sink.on_sql(event("SELECT * FROM jobs"), None)
    assert sink.facts.unattributed == 1
    assert sink.facts.top_unattributed == {"SELECT * FROM jobs": 1}
    assert sink.current_test is not None
    assert "call" not in sink.current_test.phases


def test_attribution_stale_test_unattributed() -> None:
    """B6: a lifespan worker still tagged with an earlier test lands in unattributed."""
    sink = _sink()
    sink.begin_test("tests/test_a.py::test_one")
    sink.end_test()
    sink.begin_test("tests/test_b.py::test_two")
    sink.on_sql(event("SELECT * FROM jobs"), ("tests/test_a.py::test_one", 1, "call"))
    assert sink.facts.unattributed == 1


def test_attribution_stale_attempt_unattributed() -> None:
    """B6: the same node id on an earlier attempt (a rerun) is stale."""
    sink = _sink()
    assert sink.begin_test(NODE) == 1
    sink.end_test()
    assert sink.begin_test(NODE) == 2
    sink.on_sql(event("SELECT 1"), (NODE, 1, "call"))
    sink.on_sql(event("SELECT 2"), (NODE, 2, "call"))
    assert sink.facts.unattributed == 1
    assert _call(sink).queries == 1


def test_no_test_window_means_unattributed() -> None:
    sink = _sink()
    sink.on_sql(event("SELECT 1"), (NODE, 1, "call"))
    assert sink.facts.unattributed == 1


def test_filtered_statements_are_counted_apart() -> None:
    """B7: filtered statements never reach queries, in a test or outside one."""
    sink = _sink()
    attempt = sink.begin_test(NODE)
    run_phase(sink, NODE, attempt, "setup", "PRAGMA foreign_keys=ON", "BEGIN")
    sink.on_sql(event("COMMIT"), None)
    assert sink.current_test is not None
    assert sink.current_test.phases["setup"].queries == 0
    assert sink.current_test.phases["setup"].filtered == 2
    assert sink.facts.filtered == 3
    assert sink.facts.unattributed == 0


def test_parameters_never_stored() -> None:
    """B4: a bound secret appears nowhere in the facts."""
    sink = _sink()
    attempt = sink.begin_test(NODE)
    sink.on_sql(event("INSERT INTO users (token) VALUES (?)", parameters=(SECRET,)), (NODE, attempt, "call"))
    sink.on_sql(event("INSERT INTO users (token) VALUES (?)", parameters=[(SECRET,)], batch=1), None)
    sink.end_test()
    assert SECRET not in json.dumps(sink.facts.to_json())


def test_sql_literal_secret_is_folded_and_masked() -> None:
    """B4: a secret written into the SQL text is folded or masked."""
    sink = _sink()
    attempt = sink.begin_test(NODE)
    run_phase(sink, NODE, attempt, "call", f"SELECT * FROM users WHERE token = '{SECRET}'")
    sink.on_sql(event(f"SELECT * FROM jobs WHERE note = 'password={SECRET}'"), None)
    sink.end_test()
    assert SECRET not in json.dumps(sink.facts.to_json())


def test_report_masker_ignores_full_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console's FULL exposure or masking off never reaches a report."""
    monkeypatch.setenv("SHARPIT_EXPOSE_VALUES", "FULL")
    monkeypatch.setenv("SHARPIT_MASK_SECRETS", "false")
    masked = report_masker().mask_text(f"connect failed password={SECRET}")
    assert masked is not None
    assert SECRET not in masked
    assert report_masker_warnings(os.environ) == [
        "report ignores SHARPIT_EXPOSE_VALUES=FULL",
        "report ignores SHARPIT_MASK_SECRETS=false",
    ]


def test_report_masker_no_warning_by_default() -> None:
    assert report_masker_warnings({}) == []


def test_exception_dedup_by_object() -> None:
    sink = _sink()
    attempt = sink.begin_test(NODE)
    tag = (NODE, attempt, "call")
    boom = ValueError(f"boom password={SECRET}")
    sink.on_exception(boom, "logging", tag)
    sink.on_exception(boom, "middleware", tag)
    sink.on_exception(KeyError("other"), "logging", tag)
    assert _call(sink).exceptions == 2
    assert len(_call(sink).exception_groups) == 2
    assert SECRET not in json.dumps(sink.facts.to_json())


def test_escaped_exception_excluded() -> None:
    """A copy already counted is taken back, and a later logged copy is ignored."""
    sink = _sink()
    attempt = sink.begin_test(NODE)
    tag = (NODE, attempt, "call")
    first, second = ValueError("a"), ValueError("b")
    sink.on_exception(first, "logging", tag)
    sink.on_exception(KeyError("kept"), "logging", tag)
    sink.on_escaped(first)
    sink.on_escaped(second)
    sink.on_exception(second, "logging", tag)
    assert _call(sink).exceptions == 1
    assert [name for name, _message in _call(sink).exception_groups.values()] == ["KeyError"]


def test_exception_window_rule() -> None:
    """Exceptions follow the statement rule: only the current window's tag counts."""
    sink = _sink()
    attempt = sink.begin_test(NODE)
    sink.on_exception(ValueError("x"), "logging", None)
    sink.on_exception(ValueError("y"), "logging", ("tests/test_a.py::test_one", 1, "call"))
    sink.on_exception(ValueError("z"), "logging", (NODE, attempt + 1, "call"))
    assert sink.current_test is not None
    assert "call" not in sink.current_test.phases
    assert sink.facts.unattributed_exceptions == 3


def test_sink_hook_failure_costs_a_warning_not_an_exception() -> None:
    """A malformed event never raises out of the sink; one warning says so."""
    sink = _sink()
    sink.begin_test(NODE)
    sink.on_sql(object(), (NODE, 1, "call"))  # type: ignore[arg-type]
    sink.on_sql(object(), (NODE, 1, "call"))  # type: ignore[arg-type]
    assert len(sink.facts.warnings) == 1


def test_latest_snapshot_kept_after_gc() -> None:
    class App:
        title = "Owners API"

    sink = _sink()
    app = App()
    sink.register_app(app)
    sink.snapshot_apps(lambda _app: EMPTY)
    del app
    gc.collect()
    sink.snapshot_apps(lambda _app: ApiModel((), (), ("changed",)))  # the app is gone: this is never called
    snapshots = sink.app_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0][0].startswith("Owners API#")
    assert snapshots[0][1] == EMPTY


def test_same_content_scanned_once() -> None:
    class App:
        title = "Owners API"

    sink = _sink()
    apps = [App(), App()]
    for app in apps:
        sink.register_app(app)
    sink.snapshot_apps(lambda _app: EMPTY)
    assert len(sink.app_snapshots()) == 1


def test_reused_id_does_not_overwrite_snapshot() -> None:
    class App:
        def __init__(self, title: str) -> None:
            self.title = title

    sink = _sink()
    first = App("First")
    sink.register_app(first)
    sink.snapshot_apps(lambda _app: EMPTY)
    del first
    gc.collect()
    second = App("Second")  # may reuse the freed id()
    sink.register_app(second)
    sink.snapshot_apps(lambda app: ApiModel((), (), ("x",)) if app is second else EMPTY)
    titles = [identity.partition("#")[0] for identity, _model in sink.app_snapshots()]
    assert titles == ["First", "Second"]


def test_identity_without_title_uses_the_class_name() -> None:
    class Plain:
        pass

    sink = _sink()
    app = Plain()
    sink.register_app(app)
    sink.snapshot_apps(lambda _app: EMPTY)
    assert sink.app_snapshots()[0][0].startswith("Plain#")


def _populated() -> SessionFacts:
    sink = _sink()
    attempt = sink.begin_test(NODE)
    run_phase(sink, NODE, attempt, "call", "SELECT * FROM pets WHERE id = 1", "SELECT * FROM pets WHERE id = 2")
    sink.on_exception(ValueError("boom"), "logging", (NODE, attempt, "call"))
    sink.on_sql(event("SELECT * FROM jobs"), None)
    sink.on_sql(event("PRAGMA x"), None)
    assert sink.current_test is not None
    sink.current_test.outcome = "failed"
    sink.current_test.budget = Budget(5, False, 0)
    finding = Finding("sharpit.max-queries", "test-runtime", "HIGH", NODE, "m", NODE)
    sink.current_test.findings = [finding.to_dto()]
    sink.end_test()
    facts = sink.facts
    facts.sources = [{"name": "sqlalchemy", "attached": True, "reason": None, "limitations": []}]
    facts.untraced_drivers = {"asyncpg"}
    facts.engine_drivers = {"aiosqlite"}
    facts.preexisting = 2
    facts.aliases = ["app.db.connect"]
    facts.warnings = ["w"]
    facts.exceptions_source_ok = False
    facts.advisor_runs = [AdvisorRun.of("rest-api", [finding], {"usable": True, "coverageComplete": True}, app="A#1")]
    return facts


def test_session_facts_json_round_trip_is_exact() -> None:
    facts = _populated()
    data = json.loads(json.dumps(facts.to_json()))
    again = SessionFacts.from_json(data)
    assert json.loads(json.dumps(again.to_json())) == data
    assert again.advisor_runs[0].findings[0].fingerprint == facts.advisor_runs[0].findings[0].fingerprint
    assert again.untraced_drivers == {"asyncpg"}


def test_test_facts_json_round_trip_is_exact() -> None:
    test = _populated().tests[0]
    again = TestFacts.from_json(json.loads(json.dumps(test.to_json())))
    assert again.key == TestKey(NODE, "gw0", 1)
    assert again.budget == Budget(5, False, 0)
    assert again.phases["call"].selects == test.phases["call"].selects


def test_shaped_secret_absent_from_facts_json() -> None:
    sink = _sink()
    attempt = sink.begin_test(NODE)
    secret = "ghp_" + "a1B2c3D4e5" * 3
    run_phase(
        sink,
        NODE,
        attempt,
        "call",
        f"SELECT * FROM t WHERE token = {secret}",
        f"SELECT * FROM t WHERE token = {secret}",
    )
    assert "ghp_" not in json.dumps(sink.facts.to_json())
