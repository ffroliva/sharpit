# G1+G2 — Report-Only and Baselines Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. One task/commit at a time; start only after D1 and F have merged.

**Goal:** Let CI report findings without gating on them and compare stable fingerprints to an explicitly written baseline, while unknown capture reasons continue to fail closed.

**Architecture:** Extend pytest options, test-session gates/outcome/report DTO, and xdist worker facts. Baseline data is read on every worker and written only after a complete, non-unknown run; report-only changes finding failure behavior while preserving unknown failures.

**Tech Stack:** Python 3.12+, pytest/xdist, stdlib JSON/hashlib/pathlib; report schema Draft 2020-12.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §§5.1–5.2; lane order §10.3.

## Header and ownership

- **Lane:** G1G2 (one lane because both alter the gate path).
- **Worker profile:** L, judgement-heavy (unknown precedence, partial-run facts, fingerprint semantics).
- **Dependencies:** F and D1 merged first; F supplies plugin split, accepted inert CLI options and lane gate.
- **May touch:** `src/sharpit/engine/testsession/gates.py` (`evaluate_test`, line 34), `outcome.py` (`exit_fails`, line 303), `facts.py`, `report.py` (`render`, line 69), `report.schema.json`; `src/sharpit/engine/advisors/findings.py` (`Finding`, line 17), advisor assessment call sites; pytest plugin option/gate/report/xdist modules created by F; `tests/engine/testsession/`, `tests/pytest_plugin/`, both schema copies, `docs/reference/` report contract, lane evidence folder.
- **Must not touch:** G3 action/summary modules; G4 procurement docs/dependabot; panel routes, registries or UI; `scripts/dev/lane_gate.py`; `tests/complexity_baseline.json`, `sonar-baseline.txt`, overhead budget constants, dependency lists or `uv.lock`.

## Global constraints

- Report-only suppresses finding failures only; unknown reasons fail unless `--sharpit-allow-unknown`, including when aggregate status is `fail`.
- Baselines are not dismissals; explicit dismissal wins. Vulnerability findings are excluded in 0.4.0.
- Baseline bytes are stable, masked, sorted by fingerprint, and omit timestamp/version.
- Partial runs never mark unseen findings fixed and never produce a baseline.
- Emit every report key including nulls; `sharpit-report/1` accepts additive keys.

## Review Focus

1. Aggregate `fail` masks a simultaneous unknown reason: `test_report_only_unknown_fails_when_status_fail` asserts exit 1 without allow-unknown.
2. xdist controller lacks collection facts: `test_xdist_partial_selection_facts_reach_controller` asserts worker and controller facts mark partial.
3. Count regression stays existing: `test_baselined_query_count_increase_is_new` asserts baseline 12 vs observed 500 fails.
4. Runtime values churn baselines: `test_fingerprint_stable_across_runtime_values` runs real gate/advisor code twice while varying ids, timings and parameters and compares fingerprints.
5. Baseline acts like dismissal or hides dismissal: `test_existing_baseline_keeps_dismissed_false` and `test_explicit_dismissal_wins_over_baseline` pin precedence.

---

### Task 1: Define baseline document and comparison model

**Files:** Create `src/sharpit/engine/testsession/baseline.py`; test `tests/engine/testsession/test_baseline.py`.

**Interfaces:** `read(path: Path) -> Baseline` validates schema `sharpit-baseline/1`, shape, unique fingerprints and readable JSON. `compare(findings: Sequence[Finding], baseline: Baseline | None, *, partial: bool) -> BaselineComparison` returns per-finding state (`existing`/`new`) and unseen fingerprints as `fixed` only for complete runs; partial unseen entries have `fixed=None`, `fixed_reason="partial run"`. `write(path: Path, findings: Sequence[Finding]) -> None` emits stable sorted keys `fingerprint,target,message,observed`, masked messages, and no timestamp/version.

- [ ] **Step 1: Failing tests.** `test_baseline_schema_and_sorted_bytes`, `test_baseline_rejects_bad_schema`, `test_baseline_rejects_duplicate_fingerprint`, `test_compare_existing_new_and_fixed`, `test_partial_unseen_is_null_with_reason`, `test_baseline_write_masks_values`, `test_count_gate_increase_is_new`.
- [ ] **Step 2: Run `tests/engine/testsession/test_baseline.py`; expected named assertion failures.**
- [ ] **Step 3: Implement read/compare/write.** `observed` is null for non-count findings; a count increase changes a listed fingerprint to `new`.
- [ ] **Step 4: Run targeted tests; expected PASS.**
- [ ] **Step 5: Commit** `feat: add stable sharpit baseline format and comparison`.

### Task 2: Apply baselines to gates and advisor findings

**Files:** Modify `gates.py`, `engine/advisors/findings.py`, advisor assessment entry points including `engine/collectors/restapi/service.py`; tests under `tests/engine/testsession/` and advisor tests.

**Interfaces:** Add `Finding.observed: int | None = None`, emitted as `observed` in its DTO. Extend `gates.evaluate_test(facts, budget, n_plus_one_threshold, dismissed, baseline=None)` and advisor `assess(..., baseline=None)`; annotate findings with `baselineState`. Only `not dismissed and baselineState != "existing"` fails. Preserve existing calls with `baseline=None`.

- [ ] **Step 1: Failing tests.** Review Focus 3–5 plus `test_unlisted_finding_is_new`, `test_unbaselined_run_has_null_baseline_state`, `test_explicit_dismissed_finding_stays_dismissed`, `test_max_queries_fingerprint_is_node_id`, `test_vulnerability_findings_excluded_from_baseline`.
- [ ] **Step 2: Run owning tests; expected baseline-state/count assertions fail.**
- [ ] **Step 3: Implement additive finding fields and baseline-aware gate/advisor evaluation.** Keep dismissal semantics unchanged.
- [ ] **Step 4: Run tests; expected PASS.**
- [ ] **Step 5: Commit** `feat: apply baseline states to gate and advisor findings`.

### Task 3: Capture complete/partial execution facts across xdist

**Files:** Modify post-F pytest option and xdist modules, `facts.py` or a focused partial-run module; test `tests/pytest_plugin/test_plugin_baseline.py`.

**Interfaces:** Worker facts carry deselected count and selection inputs (`-k`, `-m`, node ids, `--lf`, `--deselect`, `--sw`); controller facts carry `-x`/`--maxfail`, `session.shouldstop`, `KeyboardInterrupt`, and collected vs run. `partial_run(worker_facts, controller_facts) -> bool`. Controller reads `workeroutput` without relying on its own collection.

- [ ] **Step 1: Failing tests.** Review Focus 2; `test_partial_when_deselected`, `test_partial_when_keyword_or_nodeid_selected`, `test_partial_when_last_failed_or_deselect_used`, `test_partial_when_maxfail_or_shouldstop`, `test_partial_when_interrupted`, `test_xdist_partial_facts_merged`.
- [ ] **Step 2: Run pytester tests; expected partial-classification assertions fail.**
- [ ] **Step 3: Implement transport and deterministic partial classification.**
- [ ] **Step 4: Run targeted single-process and xdist tests; expected PASS.**
- [ ] **Step 5: Commit** `feat: detect partial sharpit pytest runs across xdist`.

### Task 4: Add report-only mode and preserve unknown failure semantics

**Files:** Modify plugin option/gate/finish modules, `engine/testsession/outcome.py`, `report.py`; tests `tests/pytest_plugin/test_plugin_report_only.py`, `tests/engine/testsession/test_outcome.py`, and JUnit/report tests.

**Interfaces:** `PluginOptions` gains `report_only: bool`. Extend `outcome.exit_fails(status, allow_unknown, *, report_only=False, unknown_reasons=()) -> bool`. In report-only, gate findings do not fail pytest reports or session exitstatus; unknown reasons fail unless allowed, regardless of aggregate status. Report adds `mode` and `unknownReasons`; JUnit finding cases have no `<failure>`, while `sharpit.status` fails only for unknown reasons. Terminal line: `sharpit report-only: N tests would fail, status <status>`.

- [ ] **Step 1: Failing tests.** Review Focus 1; `test_report_only_does_not_fail_finding_test`, `test_report_only_junit_finding_without_failure`, `test_report_only_unknown_reason_fails`, `test_report_only_unknown_fails_when_status_fail`, `test_report_only_allow_unknown_exits_zero`, `test_report_only_mode_report_and_summary`, `test_fail_on_still_selects_advisor_findings`.
- [ ] **Step 2: Run targeted tests; expected report, JUnit and exit assertions fail.**
- [ ] **Step 3: Implement mode-specific behavior without changing gate/advisor computation.**
- [ ] **Step 4: Run targeted plugin/outcome tests; expected PASS.**
- [ ] **Step 5: Commit** `feat: add report-only pytest mode with unknown guard`.

### Task 5: Wire read/write options and baseline lifecycle

**Files:** Modify plugin option modules/hooks, baseline/report modules and both `report.schema.json` copies; tests `tests/pytest_plugin/test_plugin_baseline.py`, `tests/test_report_schema.py`; update report contract under `docs/reference/`.

**Interfaces:** `--sharpit-baseline=PATH` / ini `sharpit_baseline`; `--sharpit-write-baseline=PATH` / ini `sharpit_write_baseline`. Bad/unreadable input raises `pytest.UsageError` at session start. Load baseline on every worker. Write only for complete runs with zero unknown reasons; otherwise session-end `pytest.UsageError` and destination absent/unchanged. Report adds `baseline: null | {path,sha256,existing,new,fixed,fixedReason}` plus finding `baselineState` and `observed`, all keys emitted.

- [ ] **Step 1: Failing tests.** `test_bad_baseline_usage_error_at_session_start`, `test_write_baseline_is_only_writer`, `test_write_refuses_partial_run`, `test_write_refuses_any_unknown_even_when_status_fail`, `test_write_refusal_leaves_file_absent`, `test_baseline_loaded_on_every_xdist_worker`, `test_report_baseline_counts_and_nulls`, `test_schema_accepts_additive_baseline_fields`, `test_schema_copies_identical`.
- [ ] **Step 2: Run tests; expected assertions fail.**
- [ ] **Step 3: Implement lifecycle and synchronized schema changes.**
- [ ] **Step 4: Run targeted tests and four gates; expected PASS.**
- [ ] **Step 5: Commit** `feat: wire baseline options and report contract`.

### Compatibility and precedence matrix

Use these assertions as the acceptance matrix for Tasks 2–5; do not infer behavior only from aggregate status.

| Condition | Finding outcome | Unknown outcome | Session exit |
|---|---|---|---|
| Gate finding, gate mode | failing test | none | fail |
| Gate finding, report-only | reported, no failing test/JUnit finding | none | pass unless unknown |
| Unknown reason, either mode | independent of finding | reported | fail unless allow-unknown |
| Existing baseline finding | remains listed, not dismissed | none | gate does not fail for it |
| Dismissed finding also in baseline | remains dismissed | none | explicit dismissal wins |
| Unseen baseline entry, complete run | fixed | none | report fixed |
| Unseen baseline entry, partial run | fixed is null | partial reason | never write new baseline |

- [ ] **Step 1:** Add `test_report_only_advisor_error_is_unknown` for a BootUI ERROR mapped to sharpit SKIPPED; assert unknown reason appears and report-only still exits 1 by default.
- [ ] **Step 2:** Add `test_partial_run_from_worker_selection_only` and `test_partial_run_from_controller_stop_only` so no single source of partial facts is omitted.
- [ ] **Step 3:** Add `test_baseline_bytes_stable_across_runtime_values` for timestamp/version omission and sorted stable JSON bytes.
- [ ] **Step 4:** Add `test_fixed_reason_null_on_complete_run` and `test_fixed_reason_partial_run_exact_string` for exact nullability and `partial run` contract.
- [ ] **Step 5:** Assert a baseline-listed finding with increased `observed` is `new` in both report and gate behavior; it must remain `dismissed: false`.

### Definition of the report additions

Schema and render tests pin baseline object keys (`path`, `sha256`, `existing`, `new`, `fixed`, `fixedReason`) and finding keys (`baselineState`, `observed`) with nulls emitted. Hash exact loaded baseline bytes, not a reserialized object, so path provenance and review diffs remain reproducible.

- [ ] **Step 1:** Assert baseline summary counts equal per-finding states, with vulnerability findings excluded from every count.
- [ ] **Step 2:** Assert a missing baseline emits `baseline: null`, `baselineState: null`, and `observed: null` in rendered output.
- [ ] **Step 3:** Assert schema validation accepts older reports without additive fields and new reports with them.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/G1G2/` contains current `handoff.md`; reviewer `review.md` ending `VERDICT: APPROVE` with head SHA and reviewer distinct from implementer; `findings.md` with each row fixed/red-test or parked/reason; `field-map.md` for changed report keys; `checklist.md` mapping requirements to evidence; four-gate logs pinned to head SHA.

## Definition of done

- [ ] Tasks 1–5 cover every §5.1–§5.2 rule, including xdist partial runs, unknown precedence, schema additions, and baseline stability.
- [ ] `tests/test_report_schema.py` confirms copies match and rendered reports validate.
- [ ] Lane evidence passes foundation `scripts/dev/lane_gate.py`; protected paths remain untouched.
