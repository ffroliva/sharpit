from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

import pytest

import sharpit.engine.testsession as testsession_pkg
from engine.testsession.tsfakes import NODE, event, run_phase, selects
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.capture.sqltrace import normalize
from sharpit.engine.testsession.facts import PhaseFacts, TestFacts, TestKey, UnboundedReadFact
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


def test_n_plus_one_names_lazy_relationship_and_loader() -> None:
    call = PhaseFacts(
        selects=Counter({"fp": 6}),
        sql_of={"fp": "SELECT * FROM performances WHERE player_id = ?"},
        relationship_loads=Counter({"Player.performances": 6}),
        relationship_of={"fp": ("Player.performances", True)},
        relationship_sites={"Player.performances": "test_app.py:18"},
    )
    [finding] = evaluate_test(_facts(call=call), NONE, 5, ())

    assert "Player.performances lazy-loaded 6 times" in finding.message
    assert "selectinload(Player.performances)" in finding.message
    assert "test_app.py:18" in finding.message


def test_n_plus_one_falls_back_without_relationship_evidence() -> None:
    [finding] = evaluate_test(_facts(call=selects("fp", 6, "SELECT * FROM items")), NONE, 5, ())

    assert finding.message == "6 executions of one SELECT in the call phase"


def test_n_plus_one_suggests_joinedload_for_many_to_one() -> None:
    call = PhaseFacts(
        selects=Counter({"fp": 6}),
        sql_of={"fp": "SELECT * FROM players WHERE id = ?"},
        relationship_loads=Counter({"Performance.player": 6}),
        relationship_of={"fp": ("Performance.player", False)},
    )
    [finding] = evaluate_test(_facts(call=call), NONE, 5, ())

    assert "Performance.player lazy-loaded 6 times" in finding.message
    assert "joinedload(Performance.player)" in finding.message


def test_n_plus_one_message_includes_masked_statement_and_source() -> None:
    call = PhaseFacts(
        selects=Counter({"fp": 6}),
        sql_of={"fp": "SELECT * FROM performances WHERE token = ?"},
        relationship_loads=Counter({"Player.performances": 6}),
        relationship_of={"fp": ("Player.performances", True)},
        relationship_sites={"Player.performances": "app/tests.py:42"},
    )
    [finding] = evaluate_test(_facts(call=call), NONE, 5, ())

    assert "masked statement: SELECT * FROM performances WHERE token = ?" in finding.message
    assert "app/tests.py:42" in finding.message


def test_relationship_facts_survive_json_round_trip() -> None:
    facts = PhaseFacts(
        relationship_loads=Counter({"Player.performances": 6}),
        relationship_of={"statement-fingerprint": ("Player.performances", True)},
        relationship_sites={"Player.performances": "tests/app.py:18"},
    )

    restored = PhaseFacts.from_json(json.loads(json.dumps(facts.to_json())))

    assert restored.relationship_loads == facts.relationship_loads
    assert restored.relationship_of == facts.relationship_of
    assert restored.relationship_sites == facts.relationship_sites


def test_relationship_message_keeps_statement_fingerprint() -> None:
    plain = evaluate_test(_facts(call=selects("fp", 6, "SELECT * FROM performances")), NONE, 5, ())[0]
    relation = PhaseFacts(
        selects=Counter({"fp": 6}),
        sql_of={"fp": "SELECT * FROM performances"},
        relationship_loads=Counter({"Player.performances": 6}),
        relationship_of={"fp": ("Player.performances", True)},
    )
    [enriched] = evaluate_test(_facts(call=relation), NONE, 5, ())

    assert enriched.fingerprint == plain.fingerprint


def test_explicit_dismissal_wins_over_baseline() -> None:
    facts = _facts(call=PhaseFacts(queries=6))
    current = evaluate_test(facts, Budget(5, False, 0), 5, ())[0]
    [finding] = evaluate_test(
        facts, Budget(5, False, 0), 5, (current.fingerprint,), baseline={current.fingerprint: None}
    )
    assert finding.dismissed is True
    assert fails(finding.to_dto()) is False


def _unbounded_read(*, loaded: int = 10, has_limit: bool = False, statement: str = "SELECT * FROM teams") -> TestFacts:
    fact = UnboundedReadFact("/teams", statement, "Team", loaded, 5, has_limit, "app.py:12")
    return _facts(call=PhaseFacts(unbounded_reads=[fact]))


def test_unbounded_read_exact_threshold_boundary_flags() -> None:
    found = evaluate_test(_unbounded_read(loaded=10), Budget(None, False, 0), 5, ())

    assert len(found) == 1
    assert found[0].rule_id == "sharpit.unbounded-read"
    assert "app.py:12" in found[0].message


@pytest.mark.parametrize(
    "statement",
    ["SELECT * FROM teams LIMIT 5", "SELECT * FROM teams FETCH FIRST 5 ROWS ONLY"],
    ids=["limit", "fetch"],
)
def test_select_with_limit_or_fetch_is_not_flagged(statement: str) -> None:
    assert (
        evaluate_test(_unbounded_read(loaded=52, has_limit=True, statement=statement), Budget(None, False, 0), 5, ())
        == []
    )


def test_allow_unbounded_read_marker() -> None:
    from sharpit.pytest_plugin.marker import budget_for

    class Marker:
        name = "sharpit"
        kwargs = {"allow_unbounded_read": True}

    class Item:
        own_markers = [Marker()]

        def listchain(self) -> list[object]:
            return [self]

    budget = budget_for(Item(), None)

    assert budget.allow_unbounded_read is True
    assert evaluate_test(_unbounded_read(loaded=52), budget, 5, ()) == []


def test_unbounded_read_factor_default_and_override() -> None:
    from sharpit.pytest_plugin.marker import budget_for
    from sharpit.settings import load_settings

    class Item:
        own_markers: list[object] = []

        def listchain(self) -> list[object]:
            return [self]

    default_settings = load_settings({}, {})
    override_settings = load_settings({}, {"SHARPIT_ACTIVITY_UNBOUNDED_READ_FACTOR": "3"})
    default = budget_for(Item(), None, unbounded_read_factor=default_settings.activity_unbounded_read_factor)
    override = budget_for(Item(), None, unbounded_read_factor=override_settings.activity_unbounded_read_factor)

    assert default.unbounded_read_factor == 2
    assert override.unbounded_read_factor == 3


def test_unbounded_read_facts_and_budget_survive_json_round_trip() -> None:
    fact = UnboundedReadFact("/teams", "SELECT * FROM teams", "Team", 52, 5, False, "app.py:12")
    original = TestFacts(
        TestKey(NODE, "gw0", 1),
        phases={"call": PhaseFacts(unbounded_reads=[fact])},
        budget=Budget(None, False, 0, unbounded_read_factor=3),
    )
    restored = TestFacts.from_json(json.loads(json.dumps(original.to_json())))

    assert restored.phases["call"].unbounded_reads == [fact]
    assert restored.budget is not None
    assert restored.budget.unbounded_read_factor == 3


def test_lookup_query_does_not_add_to_count() -> None:
    facts = _facts(
        call=PhaseFacts(
            unbounded_reads=[
                UnboundedReadFact("/teams", "SELECT teams", "Team", 52, 5, False, "app.py:12"),
                UnboundedReadFact("/teams", "SELECT lookup", "Lookup", 1, 5, False, "app.py:13"),
            ]
        )
    )
    found = evaluate_test(facts, Budget(None, False, 0), 5, ())

    assert len(found) == 1
    assert found[0].message.startswith("/teams materialized 52 Team rows")


def test_unbounded_read_respects_report_only_and_baseline() -> None:
    current = evaluate_test(_unbounded_read(loaded=52), Budget(None, False, 0), 5, ())
    assert len(current) == 1
    [existing] = evaluate_test(
        _unbounded_read(loaded=52),
        Budget(None, False, 0),
        5,
        (),
        baseline={current[0].fingerprint: 60},
    )
    assert existing.baseline_state == "existing"
    assert fails(existing.to_dto()) is False


# --- sharpit.swallowed-exception (spec 0.4.0 §5.5 F1) ---------------------------------------------------------------

SWALLOWED_RULE = "sharpit.swallowed-exception"


def _swallowed(type_name: str, programming_error: bool) -> TestFacts:
    from sharpit.engine.testsession.facts import SwallowedFact

    return _facts(call=PhaseFacts(swallowed=[SwallowedFact("app/weeks.py:21", type_name, programming_error)]))


def _swallowed_findings(facts: TestFacts, budget: Budget = NONE) -> list[dict[str, object]]:
    return [f.to_dto() for f in evaluate_test(facts, budget, 5, ()) if f.rule_id == SWALLOWED_RULE]


def test_swallowed_attribute_error_fails_test_by_default() -> None:
    found = _swallowed_findings(_swallowed("AttributeError", True))

    assert len(found) == 1
    assert found[0]["severity"] == "HIGH"
    assert fails(found[0]) is True
    assert found[0]["target"] == "app/weeks.py:21"


def test_non_programming_error_swallow_is_a_note() -> None:
    found = _swallowed_findings(_swallowed("ValueError", False))

    assert len(found) == 1
    assert found[0]["severity"] == "INFO"
    assert fails(found[0]) is False


def test_allow_swallowed_marker() -> None:
    from sharpit.pytest_plugin.marker import budget_for

    class Marker:
        name = "sharpit"
        kwargs = {"allow_swallowed": True}

    class Item:
        own_markers = [Marker()]

        def listchain(self) -> list[object]:
            return [self]

    budget = budget_for(Item(), None)
    found = _swallowed_findings(_swallowed("AttributeError", True), budget)

    assert budget.allow_swallowed is True
    assert len(found) == 1
    assert found[0]["severity"] == "INFO"


def test_swallowed_message_names_handler_and_type_only() -> None:
    found = _swallowed_findings(_swallowed("AttributeError", True))

    assert [f["message"] for f in found] == [
        "AttributeError swallowed by a broad except clause at app/weeks.py:21 (neither re-raised nor logged)"
    ]
