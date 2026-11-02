from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import sharpit.engine.testsession as testsession_pkg
from engine.testsession.tsfakes import NODE, event, run_phase, selects
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.capture.sqltrace import normalize
from sharpit.engine.testsession.facts import PhaseFacts, TestFacts, TestKey
from sharpit.engine.testsession.gates import Budget, evaluate_test, fails
from sharpit.engine.testsession.sink import TestSessionSink

NONE = Budget(None, False, 0)


def test_fails_excludes_existing_and_info() -> None:
    assert fails({"dismissed": False, "baselineState": "existing", "severity": "HIGH"}) is False
    assert fails({"dismissed": False, "baselineState": "new", "severity": "INFO"}) is False
    assert fails({"dismissed": False, "baselineState": "new", "severity": "HIGH"}) is True


def test_per_finding_dismissal_reaches_gate(tmp_path, monkeypatch) -> None:
    pair = ("sharpit.max-queries", NODE)
    monkeypatch.setattr(DismissalStore, "dismissed_pairs", lambda _self: {pair})
    store = DismissalStore(tmp_path)
    [finding] = evaluate_test(_facts(call=PhaseFacts(queries=7)), Budget(5, False, 0), 5, (), store.dismissed_pairs())
    assert fails(finding.to_dto()) is False


def test_baselined_query_count_increase_is_new() -> None:
    facts = _facts(call=PhaseFacts(queries=500))
    current = evaluate_test(facts, Budget(5, False, 0), 5, ())[0]
    [increased] = evaluate_test(facts, Budget(5, False, 0), 5, (), baseline={current.fingerprint: 12})
    assert increased.baseline_state == "new"
    assert fails(increased.to_dto()) is True


def test_existing_baseline_keeps_dismissed_false() -> None:
    facts = _facts(call=PhaseFacts(queries=6))
    current = evaluate_test(facts, Budget(5, False, 0), 5, ())[0]
    [existing] = evaluate_test(facts, Budget(5, False, 0), 5, (), baseline={current.fingerprint: 12})
    assert existing.dismissed is False
    assert fails(existing.to_dto()) is False


def test_unlisted_finding_is_new() -> None:
    facts = _facts(call=PhaseFacts(queries=6))
    [finding] = evaluate_test(facts, Budget(5, False, 0), 5, (), baseline={"other": None})
    assert finding.baseline_state == "new"


def test_unbaselined_run_has_null_baseline_state() -> None:
    [finding] = evaluate_test(_facts(call=PhaseFacts(queries=6)), Budget(5, False, 0), 5, ())
    assert finding.baseline_state is None


def test_explicit_dismissed_finding_stays_dismissed() -> None:
    facts = _facts(call=PhaseFacts(queries=6))
    current = evaluate_test(facts, Budget(5, False, 0), 5, ())[0]
    [finding] = evaluate_test(
        facts,
        Budget(5, False, 0),
        5,
        (current.fingerprint,),
        baseline={current.fingerprint: 12},
    )
    assert finding.dismissed is True
    assert fails(finding.to_dto()) is False


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


def test_fingerprint_stable_across_runtime_values() -> None:
    # spec §5.2: worker, attempt, counts and SQL literals vary between runs; fingerprints must not
    first = evaluate_test(
        TestFacts(TestKey(NODE, "gw0", 1), phases={"call": PhaseFacts(queries=7)}), Budget(5, False, 0), 5, ()
    )
    second = evaluate_test(
        TestFacts(TestKey(NODE, "gw3", 2), phases={"call": PhaseFacts(queries=40)}), Budget(5, False, 0), 5, ()
    )
    assert [f.fingerprint for f in first] == [f.fingerprint for f in second]
    one = evaluate_test(_facts(call=selects("fp", 6, "SELECT * FROM pets WHERE owner_id = 1")), NONE, 5, ())
    two = evaluate_test(
        TestFacts(
            TestKey(NODE, "gw1", 3), phases={"call": selects("fp", 60, "SELECT * FROM pets WHERE owner_id = 99")}
        ),
        NONE,
        5,
        (),
    )
    assert [f.fingerprint for f in one] == [f.fingerprint for f in two]


def test_explicit_dismissal_wins_over_baseline() -> None:
    facts = _facts(call=PhaseFacts(queries=6))
    current = evaluate_test(facts, Budget(5, False, 0), 5, ())[0]
    [finding] = evaluate_test(
        facts, Budget(5, False, 0), 5, (current.fingerprint,), baseline={current.fingerprint: None}
    )
    assert finding.dismissed is True
    assert fails(finding.to_dto()) is False
