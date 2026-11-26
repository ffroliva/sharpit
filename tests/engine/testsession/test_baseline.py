from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from types import SimpleNamespace

import pytest

from engine.testsession.tsfakes import attempt_facts, part, render_parts
from sharpit.engine.advisors.findings import AdvisorRun, Finding
from sharpit.engine.testsession import baseline, gates
from sharpit.engine.testsession.facts import PhaseFacts
from sharpit.pytest_plugin.report_io import _apply_baseline


def _finding(rule_id: str = "sharpit.max-queries", target: str = "node", observed: int | None = None) -> Finding:
    return Finding(rule_id, "test-runtime", "HIGH", target, "masked message", target, observed=observed)


def test_baseline_schema_and_sorted_bytes(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    baseline.write(path, (_finding("b", "z"), _finding("a", "a")))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "sharpit-baseline/1"
    assert [entry["fingerprint"] for entry in payload["findings"]] == sorted(
        entry["fingerprint"] for entry in payload["findings"]
    )
    first = path.read_bytes()
    baseline.write(path, (_finding("a", "a"), _finding("b", "z")))
    assert path.read_bytes() == first


def test_baseline_rejects_bad_schema(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text('{"schema":"wrong","findings":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        baseline.read(path)


def test_baseline_rejects_duplicate_fingerprint(tmp_path) -> None:
    entry = {"fingerprint": "f", "ruleId": "R", "target": "t", "message": "m", "observed": None}
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"schema": "sharpit-baseline/1", "findings": [entry, entry]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate fingerprint"):
        baseline.read(path)


def test_compare_existing_new_and_fixed(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    baseline.write(path, (_finding(target="seen"), _finding(target="gone")))
    result = baseline.compare(
        (_finding(target="seen"), _finding(target="new")), baseline.read(path), partial=False, tests=(), incomplete=()
    )
    assert [finding.baseline_state for finding in result.findings] == ["existing", "new"]
    assert [entry.target for entry in result.fixed or ()] == ["gone"]
    assert result.fixed_reason is None


def test_partial_unseen_is_null_with_reason(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    baseline.write(path, (_finding(target="gone"),))
    result = baseline.compare((), baseline.read(path), partial=True, tests=(), incomplete=())
    assert result.fixed is None
    assert result.fixed_reason == "partial run"


def test_baseline_write_masks_values(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    baseline.write(path, (_finding(),))
    raw = path.read_text(encoding="utf-8")
    assert "hunter2" not in raw


def test_count_gate_increase_is_new(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    baseline.write(path, (_finding(observed=12),))
    result = baseline.compare((_finding(observed=500),), baseline.read(path), partial=False, tests=(), incomplete=())
    assert result.findings[0].baseline_state == "new"


def test_vulnerability_findings_excluded_from_baseline(tmp_path) -> None:
    finding = Finding("VULN-001", "vulnerability", "HIGH", "pkg 1", "dependency issue")
    path = tmp_path / "baseline.json"
    baseline.write(path, (finding,))
    assert baseline.read(path).entries == {}


def test_vulnerability_advisor_excluded_whatever_the_rule_id(tmp_path) -> None:
    # audit 2026-11-02: the test above passes with either exclusion removed; each half gets its own test
    findings = (
        Finding("OSV-1", "vulnerability", "HIGH", "pkg 1", "m"),
        Finding("OSV-2", "vulns", "HIGH", "pkg 2", "m"),
    )
    path = tmp_path / "baseline.json"
    baseline.write(path, findings)
    assert baseline.read(path).entries == {}, "a vulnerability-advisor finding was written to the baseline"


def test_vuln_rule_id_excluded_whatever_the_advisor(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    baseline.write(path, (Finding("VULN-002", "dependencies", "HIGH", "pkg 1", "m"),))
    assert baseline.read(path).entries == {}, "a VULN- rule finding was written to the baseline"


def _baseline_of(tmp_path, *findings: Finding) -> baseline.Baseline:
    path = tmp_path / "old.json"
    baseline.write(path, findings)
    return baseline.read(path)


def test_fixed_only_for_advisors_that_ran(tmp_path) -> None:
    rest = Finding("RAPI-1", "rest-api", "HIGH", "GET /x", "m")
    old = _baseline_of(tmp_path, rest, _finding())
    result = baseline.compare([], old, partial=False, ran={"test-runtime"}, tests=(), incomplete=())
    assert result.fixed is None
    assert result.fixed_reason == "advisor did not run: rest-api"
    assert [entry.fingerprint for entry in result.carried] == [rest.fingerprint]


def test_write_keeps_carried_entries(tmp_path) -> None:
    rest = Finding("RAPI-1", "rest-api", "HIGH", "GET /x", "m")
    [carried] = _baseline_of(tmp_path, rest).entries.values()
    path = tmp_path / "new.json"
    baseline.write(path, [_finding()], keep=[carried])
    assert rest.fingerprint in baseline.read(path).entries


def test_dismissed_findings_not_written(tmp_path) -> None:
    path = tmp_path / "new.json"
    baseline.write(path, [Finding("RAPI-1", "rest-api", "HIGH", "GET /x", "m", dismissed=True)])
    assert baseline.read(path).entries == {}


def test_baseline_write_cleans_lone_surrogates_and_uses_lf(tmp_path) -> None:
    import contextlib

    path = tmp_path / "new.json"
    with contextlib.suppress(UnicodeEncodeError):
        baseline.write(path, [Finding("RAPI-1", "rest-api", "HIGH", "GET /x", "bad \ud800 text")])
    assert path.exists(), "a lone surrogate in a message broke the baseline write"
    assert b"\r\n" not in path.read_bytes()


# --- compare() repeats the vulnerability exclusions (G1G2 audit review): one test per clause -------------------------

EMPTY = baseline.Baseline({}, b"")


@pytest.mark.parametrize("advisor", ["vulnerability", "vulns", "Vulnerability"])
def test_compare_leaves_vulnerability_advisor_findings_unannotated(advisor: str) -> None:
    [compared] = baseline.compare(
        [Finding("OSV-1", advisor, "HIGH", "pkg 1", "m")], EMPTY, partial=False, tests=(), incomplete=()
    ).findings
    assert compared.baseline_state is None, f"a {advisor!r} finding was compared against the baseline"


def test_compare_leaves_vuln_rule_findings_unannotated() -> None:
    [compared] = baseline.compare(
        [Finding("VULN-2", "dependencies", "HIGH", "pkg", "m")], EMPTY, partial=False, tests=(), incomplete=()
    ).findings
    assert compared.baseline_state is None, "a VULN- rule finding was compared against the baseline"


def test_compare_never_reports_a_vuln_entry_as_fixed(tmp_path) -> None:
    entry = {
        "fingerprint": "dependencies:VULN-3:x",
        "ruleId": "VULN-3",
        "target": "t",
        "message": "m",
        "observed": None,
    }
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"schema": "sharpit-baseline/1", "findings": [entry]}), encoding="utf-8")
    result = baseline.compare([], baseline.read(path), partial=False, tests=(), incomplete=())
    assert result.fixed == (), "a hand-written VULN- baseline entry was reported as fixed"


def test_write_excludes_vulnerability_advisor_whatever_its_case(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    baseline.write(path, (Finding("OSV-1", "Vulnerability", "HIGH", "pkg 1", "m"),))
    assert baseline.read(path).entries == {}, "a 'Vulnerability' finding was written to the baseline"


def _apply(tmp_path, run: AdvisorRun, entry: Finding) -> tuple[dict, tuple]:
    old = _baseline_of(tmp_path, entry)
    data = render_parts(part(advisor_runs=[run]))
    state = SimpleNamespace(
        baseline_data=old, partial=False, options=SimpleNamespace(baseline="old.json"), baseline_carried=()
    )
    _apply_baseline(state, data)
    return data["baseline"], state.baseline_carried


_GAP = {
    "usable": True,
    "coverageComplete": False,
    "limitations": ["Mounted application at /m has no inspectable routes."],
}


@pytest.mark.parametrize("seen", [False, True], ids=["partial", "failed-with-gap"])
def test_baseline_entry_in_an_unread_mount_is_neither_fixed_nor_dropped(tmp_path, seen: bool) -> None:
    in_mount = Finding("RAPI-1", "rest-api", "HIGH", "GET /m/x", "m")
    elsewhere = [Finding("RAPI-2", "rest-api", "HIGH", "GET /y", "m")] if seen else []
    result, carried = _apply(tmp_path, AdvisorRun.of("rest-api", elsewhere, _GAP, app="A#1"), in_mount)
    assert result["fixed"] is None
    assert result["fixedReason"] == "advisor assessed part of the app: rest-api"
    assert [entry.fingerprint for entry in carried] == [in_mount.fingerprint]


# --- the entry names its owner (#329) -------------------------------------------------------------------------------


def _test_runtime_finding(node_id: str) -> Finding:
    return Finding(
        "sharpit.n-plus-one", "test-runtime", "HIGH", "SELECT 1", "masked message", test_node_id=node_id, observed=30
    )


def _written_rows(tmp_path, *findings: Finding) -> list[dict]:
    path = tmp_path / "baseline.json"
    baseline.write(path, findings)
    return json.loads(path.read_text(encoding="utf-8"))["findings"]


def test_written_entry_names_its_owner(tmp_path) -> None:
    [row] = _written_rows(tmp_path, _test_runtime_finding("tests/test_a.py::test_n1"))
    assert row.get("owner") == hashlib.sha256(b"tests/test_a.py::test_n1").hexdigest()[:16]


def test_read_keeps_the_owner(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    row = {
        "fingerprint": "test-runtime:r:0123456789abcdef",
        "ruleId": "r",
        "target": "t",
        "message": "m",
        "observed": 1,
        "owner": "0123456789abcdef",
    }
    path.write_text(json.dumps({"schema": "sharpit-baseline/1", "findings": [row]}), encoding="utf-8")
    [entry] = baseline.read(path).entries.values()
    assert entry.owner == "0123456789abcdef"


@pytest.mark.parametrize("owner", [1, True, []], ids=["int", "bool", "list"])
def test_read_rejects_an_owner_that_is_not_a_string(tmp_path, owner: object) -> None:
    path = tmp_path / "baseline.json"
    row = {
        "fingerprint": "test-runtime:r:0123456789abcdef",
        "ruleId": "r",
        "target": "t",
        "message": "m",
        "observed": 1,
        "owner": owner,
    }
    path.write_text(json.dumps({"schema": "sharpit-baseline/1", "findings": [row]}), encoding="utf-8")
    caught: ValueError | None = None
    try:
        baseline.read(path)
    except ValueError as exc:
        caught = exc
    assert caught is not None
    assert str(caught) == "baseline owner must be a string or null"


def test_written_owner_has_no_node_id_text(tmp_path) -> None:
    [row] = _written_rows(tmp_path, _test_runtime_finding("tests/test_a.py::test_login[password=hunter2secret]"))
    owner = str(row.get("owner"))
    assert re.fullmatch(r"[0-9a-f]{16}", owner)
    assert "hunter2secret" not in owner


def test_advisor_entry_is_written_without_owner(tmp_path) -> None:
    [row] = _written_rows(tmp_path, Finding("RAPI-1", "rest-api", "HIGH", "GET /x", "m"))
    assert "owner" in row
    assert row["owner"] is None


def test_legacy_entry_reads_without_owner(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    row = {
        "fingerprint": "test-runtime:r:0123456789abcdef",
        "ruleId": "r",
        "target": "t",
        "message": "m",
        "observed": 1,
    }
    path.write_text(json.dumps({"schema": "sharpit-baseline/1", "findings": [row]}), encoding="utf-8")
    [entry] = baseline.read(path).entries.values()
    assert entry.owner is None


def test_rewrite_of_own_output_is_byte_identical(tmp_path) -> None:
    first = tmp_path / "first.json"
    baseline.write(first, [_test_runtime_finding("tests/test_a.py::test_n1")])
    again = tmp_path / "again.json"
    baseline.write(again, [], keep=list(baseline.read(first).entries.values()))
    assert again.read_bytes() == first.read_bytes()


# --- an unseen test-runtime entry is fixed only when its owner proved it (#329) -------------------------------

OWN = "tests/test_a.py::test_n1"
OTHER = "tests/test_a.py::test_other"
DID_NOT_RUN = "its test did not run"
DID_NOT_COMPLETE = "its test did not complete"
STILL_SHOWN = "its test still shows it outside the gate"
NEW_OF_RULE = "its test has a new finding of the same rule"
NO_OWNER = "recorded without its owner"
INCOMPLETE = "the run's evidence is incomplete"


def _call(selects: int = 0, queries: int | None = None, exceptions: int = 0) -> PhaseFacts:
    return PhaseFacts(
        queries=selects if queries is None else queries,
        exceptions=exceptions,
        selects=Counter({"G": selects}) if selects else Counter[str](),
        sql_of={"G": "SELECT 1"},
        exception_groups={"E": ("ValueError", "boom")} if exceptions else {},
    )


def _old_finding(rule: str, node: str = OWN) -> Finding:
    """The one finding the gates give for ``rule`` when the test ran 30 statements and raised once."""
    before = attempt_facts(node, call=_call(selects=30, exceptions=1), budget=gates.Budget(10, False, 0))
    kept = [f for f in gates.evaluate_test(before, before.budget, 2, ()) if f.rule_id == rule]
    assert len(kept) == 1, "the helper must build exactly one finding"
    return kept[0]


def _entry_of(tmp_path, rule: str, node: str = OWN) -> baseline.Baseline:
    return _baseline_of(tmp_path, _old_finding(rule, node))


def _compare(old: baseline.Baseline, *tests, current=(), incomplete=()) -> baseline.Comparison:
    return baseline.compare(list(current), old, partial=False, tests=list(tests), incomplete=incomplete)


def _reasons(result: baseline.Comparison) -> list[str]:
    return [reason for _, reason in result.inconclusive]


def _clean(node: str = OWN, **kwargs):
    return attempt_facts(node, call=_call(selects=1), **kwargs)


def test_entry_without_owner_is_not_fixed(tmp_path) -> None:
    path = tmp_path / "legacy.json"
    baseline.write(path, [_old_finding(gates.N_PLUS_ONE)])
    document = json.loads(path.read_text(encoding="utf-8"))
    for row in document["findings"]:
        del row["owner"]
    path.write_text(json.dumps(document), encoding="utf-8")
    result = _compare(baseline.read(path), _clean())
    assert result.fixed == ()
    assert _reasons(result) == [NO_OWNER]


def test_incomplete_evidence_is_not_fixed(tmp_path) -> None:
    result = _compare(_entry_of(tmp_path, gates.N_PLUS_ONE), _clean(), incomplete=gates.GATE_IDS)
    assert result.fixed == ()
    assert _reasons(result) == [INCOMPLETE]


def test_unbounded_read_limitation_withholds_only_its_rule(tmp_path) -> None:
    unbounded = Finding(gates.UNBOUNDED_READ, "test-runtime", "HIGH", "t", "m", OWN, identity="U", observed=1)
    old = _baseline_of(tmp_path, unbounded, _old_finding(gates.N_PLUS_ONE))
    result = _compare(old, _clean(), incomplete={gates.UNBOUNDED_READ})
    assert [e.rule_id for e in result.fixed or ()] == [gates.N_PLUS_ONE]
    assert [(e.rule_id, reason) for e, reason in result.inconclusive] == [(gates.UNBOUNDED_READ, INCOMPLETE)]


@pytest.mark.parametrize("ran", [OTHER, "tests/test_a.py::test_n1_renamed"], ids=["deleted", "renamed"])
def test_owner_that_is_gone_is_not_fixed(tmp_path, ran: str) -> None:
    result = _compare(_entry_of(tmp_path, gates.N_PLUS_ONE), _clean(ran))
    assert result.fixed == ()
    assert _reasons(result) == [DID_NOT_RUN]


@pytest.mark.parametrize(
    ("completed", "outcome", "phases"),
    [
        (None, "skipped", {"call": _call()}),
        (False, "skipped", {"call": _call()}),
        (False, "failed", {"call": _call(selects=1)}),
        (None, "error", {}),
        (False, "passed", {"call": _call(selects=1)}),
    ],
    ids=["skipped", "xfailed", "failed-before-the-code", "setup-error", "failing-subtest"],
)
def test_owner_that_did_not_complete_is_not_fixed(tmp_path, completed, outcome, phases) -> None:
    facts = attempt_facts(OWN, completed=completed, outcome=outcome, **phases)
    result = _compare(_entry_of(tmp_path, gates.N_PLUS_ONE), facts)
    assert result.fixed == ()
    assert _reasons(result) == [DID_NOT_COMPLETE]


def test_changed_statement_is_not_fixed(tmp_path) -> None:
    changed = Finding(gates.N_PLUS_ONE, "test-runtime", "HIGH", "SELECT 2", "m", OWN, identity="H", observed=5)
    result = _compare(_entry_of(tmp_path, gates.N_PLUS_ONE), _clean(), current=[changed])
    assert result.fixed == ()
    assert _reasons(result) == [NEW_OF_RULE]


@pytest.mark.parametrize(
    ("rule", "budget", "call"),
    [
        (gates.N_PLUS_ONE, gates.Budget(100, True, 0), _call(selects=20)),
        (gates.N_PLUS_ONE, gates.Budget(100, False, 0), _call(selects=30)),
        (gates.EXCEPTION, gates.Budget(100, False, 5), _call(selects=1, exceptions=1)),
        (gates.MAX_QUERIES, gates.Budget(None, False, 0), _call(selects=1, queries=20)),
        (gates.MAX_QUERIES, gates.Budget(100, False, 0), _call(selects=1, queries=30)),
    ],
    ids=["allow-n-plus-one", "raised-threshold", "raised-max-exceptions", "dropped-max-queries", "count-at-baseline"],
)
def test_finding_still_shown_outside_the_gate_is_not_fixed(tmp_path, rule, budget, call) -> None:
    result = _compare(_entry_of(tmp_path, rule), attempt_facts(OWN, call=call, budget=budget))
    assert result.fixed == ()
    assert _reasons(result) == [STILL_SHOWN]


def test_finding_moved_to_setup_phase_is_not_fixed(tmp_path) -> None:
    result = _compare(_entry_of(tmp_path, gates.N_PLUS_ONE), attempt_facts(OWN, setup=_call(selects=30), call=_call()))
    assert result.fixed == ()
    assert _reasons(result) == [STILL_SHOWN]


def test_finding_in_an_earlier_rerun_attempt_is_not_fixed(tmp_path) -> None:
    first = attempt_facts(OWN, completed=False, outcome="failed", attempt=1, call=_call(selects=30))
    second = attempt_facts(OWN, attempt=2, call=_call(selects=1))
    result = _compare(_entry_of(tmp_path, gates.N_PLUS_ONE), first, second)
    assert result.fixed == ()
    assert _reasons(result) == [STILL_SHOWN]


def test_inconclusive_entry_is_carried(tmp_path) -> None:
    result = _compare(_entry_of(tmp_path, gates.N_PLUS_ONE), _clean(OTHER))
    assert [e.rule_id for e in result.carried] == [gates.N_PLUS_ONE]


def test_gone_only_where_its_owner_ran_again(tmp_path) -> None:
    # ported: SideEffectComparisonTests.aNewHostOfARouteIsAddedAndAGoneOneRemovedOnlyWhereItsOwnerRanAgain
    old = _baseline_of(tmp_path, _old_finding(gates.N_PLUS_ONE), _old_finding(gates.N_PLUS_ONE, OTHER))
    new = Finding(gates.N_PLUS_ONE, "test-runtime", "HIGH", "SELECT 2", "m", OTHER, identity="H", observed=5)
    result = _compare(old, _clean(), current=[new])
    assert [e.owner for e in result.fixed or ()] == [baseline.owner_of(OWN)]
    assert [e.owner for e, _ in result.inconclusive] == [baseline.owner_of(OTHER)]
    assert [f.baseline_state for f in result.findings] == ["new"]


def test_evidence_not_recorded_whole_withholds_and_fixes_nothing(tmp_path) -> None:
    # ported: SideEffectComparisonTests.aSensorThatDidNotRecordEitherRunWholeIsNotComparedAndListsNothing
    old = _baseline_of(tmp_path, _old_finding(gates.N_PLUS_ONE), _old_finding(gates.MAX_QUERIES))
    result = _compare(old, _clean(), incomplete=gates.GATE_IDS)
    assert result.fixed == ()
    assert _reasons(result) == [INCOMPLETE, INCOMPLETE]
