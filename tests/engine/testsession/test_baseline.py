from __future__ import annotations

import json

import pytest

from sharpit.engine.advisors.findings import Finding
from sharpit.engine.testsession import baseline


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
    result = baseline.compare((_finding(target="seen"), _finding(target="new")), baseline.read(path), partial=False)
    assert [finding.baseline_state for finding in result.findings] == ["existing", "new"]
    assert [entry.target for entry in result.fixed or ()] == ["gone"]
    assert result.fixed_reason is None


def test_partial_unseen_is_null_with_reason(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    baseline.write(path, (_finding(target="gone"),))
    result = baseline.compare((), baseline.read(path), partial=True)
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
    result = baseline.compare((_finding(observed=500),), baseline.read(path), partial=False)
    assert result.findings[0].baseline_state == "new"


def test_vulnerability_findings_excluded_from_baseline(tmp_path) -> None:
    finding = Finding("VULN-001", "vulnerability", "HIGH", "pkg 1", "dependency issue")
    path = tmp_path / "baseline.json"
    baseline.write(path, (finding,))
    assert baseline.read(path).entries == {}


def _baseline_of(tmp_path, *findings: Finding) -> baseline.Baseline:
    path = tmp_path / "old.json"
    baseline.write(path, findings)
    return baseline.read(path)


def test_fixed_only_for_advisors_that_ran(tmp_path) -> None:
    rest = Finding("RAPI-1", "rest-api", "HIGH", "GET /x", "m")
    old = _baseline_of(tmp_path, rest, _finding())
    result = baseline.compare([], old, partial=False, ran={"test-runtime"})
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
