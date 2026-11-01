from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import sharpit.engine.testsession as testsession_pkg
from engine.testsession.tsfakes import NODE, event, run_phase, selects
from sharpit.engine.capture.sqltrace import normalize
from sharpit.engine.testsession.facts import PhaseFacts, TestFacts, TestKey
from sharpit.engine.testsession.gates import Budget, evaluate_test
from sharpit.engine.testsession.sink import TestSessionSink

NONE = Budget(None, False, 0)


def _facts(**phases: PhaseFacts) -> TestFacts:
    return TestFacts(TestKey(NODE, "gw0", 1), phases=dict(phases))


def test_max_queries_gate() -> None:
    [finding] = evaluate_test(_facts(call=PhaseFacts(queries=7)), Budget(5, False, 0), 5, ())
    assert finding.rule_id == "sharpit.max-queries"
    assert finding.advisor == "test-runtime"
    assert finding.severity == "HIGH"
    assert finding.target == NODE
    assert finding.test_node_id == NODE
    assert finding.message == "7 queries in the call phase (budget 5)"


def test_max_queries_at_budget_passes() -> None:
    assert evaluate_test(_facts(call=PhaseFacts(queries=5)), Budget(5, False, 0), 5, ()) == []


def test_no_budget_not_evaluated() -> None:
    assert evaluate_test(_facts(call=PhaseFacts(queries=10_000)), NONE, 5, ()) == []


def test_n_plus_one_threshold_and_minimum_2() -> None:
    assert evaluate_test(_facts(call=selects("fp", 4)), NONE, 5, ()) == []
    [at_threshold] = evaluate_test(_facts(call=selects("fp", 5)), NONE, 5, ())
    assert at_threshold.rule_id == "sharpit.n-plus-one"
    assert at_threshold.message == "5 executions of one SELECT in the call phase"
    assert at_threshold.target == "SELECT * FROM pets WHERE owner_id = ?"
    assert evaluate_test(_facts(call=selects("fp", 1)), NONE, 1, ()) == []
    assert len(evaluate_test(_facts(call=selects("fp", 2)), NONE, 1, ())) == 1


def test_n_plus_one_allowed_by_the_marker() -> None:
    assert evaluate_test(_facts(call=selects("fp", 50)), Budget(None, True, 0), 5, ()) == []


def test_n_plus_one_case_and_literal_folding() -> None:
    """``WHERE id=41`` and ``WHERE ID=42`` are one group (case and literal fold, spacing is the fingerprint's)."""
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)
    run_phase(sink, NODE, attempt, "call", "SELECT * FROM pets WHERE id=41", "SELECT * FROM pets WHERE ID=42")
    assert sink.current_test is not None
    [finding] = evaluate_test(sink.current_test, NONE, 2, ())
    assert finding.message == "2 executions of one SELECT in the call phase"


def test_n_plus_one_identity_is_the_normalized_fingerprint() -> None:
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)
    sql = "SELECT * FROM pets WHERE id = 41"
    run_phase(sink, NODE, attempt, "call", sql, "SELECT * FROM pets WHERE ID = 42")
    assert sink.current_test is not None
    [finding] = evaluate_test(sink.current_test, NONE, 2, ())
    assert finding.identity == normalize(sql).fingerprint


def test_n_plus_one_ignores_writes() -> None:
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)
    run_phase(sink, NODE, attempt, "call", *["INSERT INTO pets VALUES (1)"] * 6)
    assert sink.current_test is not None
    assert evaluate_test(sink.current_test, NONE, 5, ()) == []


def test_exception_gate_max_exceptions() -> None:
    groups = {"A\nm:f:1": ("ValueError", "boom"), "B\nm:g:2": ("KeyError", "k")}
    call = PhaseFacts(exceptions=2, exception_groups=groups)
    found = evaluate_test(_facts(call=call), NONE, 5, ())
    assert [f.target for f in found] == [f"{NODE}#A\nm:f:1", f"{NODE}#B\nm:g:2"]
    assert found[0].message == "ValueError: boom (swallowed)"
    assert evaluate_test(_facts(call=call), Budget(None, False, 2), 5, ()) == []


def test_gates_ignore_setup_and_teardown() -> None:
    """B7: only the call phase gates."""
    noisy = selects("fp", 50)
    noisy.exceptions = 3
    noisy.exception_groups = {"A": ("ValueError", "x")}
    assert evaluate_test(_facts(setup=noisy, teardown=noisy), Budget(1, False, 0), 5, ()) == []


def test_filtered_not_counted() -> None:
    """B7: a PRAGMA-heavy call phase does not trip max_queries."""
    sink = TestSessionSink("gw0")
    attempt = sink.begin_test(NODE)
    run_phase(sink, NODE, attempt, "call", *["PRAGMA table_info(pets)"] * 20, "SELECT * FROM pets")
    assert sink.current_test is not None
    assert evaluate_test(sink.current_test, Budget(1, False, 0), 5, ()) == []


def test_dismissed_gate_finding_does_not_fail() -> None:
    [finding] = evaluate_test(_facts(call=PhaseFacts(queries=7)), Budget(5, False, 0), 5, ())
    [again] = evaluate_test(_facts(call=PhaseFacts(queries=7)), Budget(5, False, 0), 5, [finding.fingerprint])
    assert again.dismissed
    assert again.fingerprint == finding.fingerprint
    assert not finding.dismissed


def test_gates_read_no_duration() -> None:
    """B8: the same statements at any duration give the same gate result."""

    def run(duration_ns: int) -> list[str]:
        sink = TestSessionSink("gw0")
        attempt = sink.begin_test(NODE)
        for _ in range(6):
            sink.on_sql(event("SELECT * FROM pets WHERE id = 1", duration_ns=duration_ns), (NODE, attempt, "call"))
        assert sink.current_test is not None
        return [f.fingerprint for f in evaluate_test(sink.current_test, Budget(3, False, 0), 5, ())]

    assert run(1) == run(10**12)
    assert len(run(1)) == 2


def test_gates_module_never_reads_duration() -> None:
    """B8 code shape: no attribute or name in the gating modules contains ``duration``."""
    root = Path(testsession_pkg.__file__).parent
    for name in ("gates.py", "outcome.py", "sink.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        names = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
        names += [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)]
        names += [n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)]
        assert [n for n in names if "duration" in n.lower()] == [], name


def test_selects_counter_is_a_counter() -> None:
    assert isinstance(selects("fp", 2).selects, Counter)
