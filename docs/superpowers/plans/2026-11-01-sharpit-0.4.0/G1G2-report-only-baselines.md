# G1+G2 — Report-Only and Baselines Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. One task/commit at a time; start after F and G6. D1 is not a dependency; whichever of D1 and G1G2 merges second wires per-finding dismissals into the pytest gate.

**Goal:** Let CI report findings without gating on them and compare stable fingerprints to an explicitly written baseline, while unknown capture reasons continue to fail closed.

**Architecture:** Extend pytest options, test-session gates/outcome/report DTO, and xdist worker facts. Baseline data is read on every worker and written only after a complete, non-unknown run; report-only changes finding failure behavior while preserving unknown failures.

**Tech Stack:** Python 3.12+, pytest/xdist, stdlib JSON/hashlib/pathlib; report schema Draft 2020-12.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §§5.1–5.2; lane order §10.3.

## Header and ownership

- **Lane:** G1G2 (one lane because both alter the gate path).
- **Worker profile:** L, judgement-heavy (unknown precedence, partial-run facts, fingerprint semantics).
- **Dependencies:** F and G6 (exactly as PLAN.md). G6 supplies `SKIPPED` support; F supplies plugin split, accepted inert CLI options and lane gate.
- **May touch:** `src/sharpit/engine/testsession/gates.py` (`evaluate_test`, line 34), `outcome.py` (`exit_fails`, line 303), `facts.py`, `report.py` (`render`, line 69), `report.schema.json`; `src/sharpit/engine/advisors/findings.py` (`Finding`, line 17), advisor assessment call sites; pytest plugin option/gate/report/xdist modules created by F; `tests/engine/testsession/`, `tests/pytest_plugin/`, both schema copies, `docs/reference/` report contract, lane evidence folder.
- **Must not touch:** G3 action/summary modules; G4 procurement docs/Dependabot; panel routes, registries or UI; `scripts/dev/lane_gate.py`; `tests/complexity_baseline.json`, `sonar-baseline.txt`, overhead budget constants, dependency lists or `uv.lock`.

## Global constraints

- Report-only suppresses finding failures only; unknown reasons fail unless `--sharpit-allow-unknown`, including when aggregate status is `fail`.
- Baselines are not dismissals; explicit dismissal wins. Vulnerability findings are excluded in 0.4.0.
- Baseline bytes are stable, masked, sorted by fingerprint, and omit timestamp/version.
- Partial runs never mark unseen findings fixed and never produce a baseline.
- Emit every report key including nulls; `sharpit-report/1` accepts additive keys.

## Review Focus

1. Aggregate `fail` masks a simultaneous unknown reason: `test_report_only_still_fails_on_unknown_reason_when_status_is_fail` asserts exit 1 without allow-unknown.
2. xdist controller lacks collection facts: `test_write_baseline_refused_on_partial_xdist_run` asserts a partial `-n 2 -k x` run refuses writing and keeps `fixed` null.
3. Count regression stays existing: `test_baselined_query_count_increase_is_new` asserts baseline 12 vs observed 500 fails.
4. Runtime values churn baselines: `test_fingerprint_stable_across_runtime_values` runs real gate/advisor code twice while varying ids, timings and parameters and compares fingerprints.
5. Baseline acts like dismissal or hides dismissal: `test_existing_baseline_keeps_dismissed_false` and `test_explicit_dismissal_wins_over_baseline` pin precedence.

---

### Task 1: Define baseline document and comparison model

**Files:** Create `src/sharpit/engine/testsession/baseline.py`; test `tests/engine/testsession/test_baseline.py`.

**Interfaces:** `read(path: Path) -> Baseline` validates schema `sharpit-baseline/1`, shape, unique fingerprints and readable JSON. `compare(findings: Sequence[Finding], baseline: Baseline | None, *, partial: bool) -> BaselineComparison` returns per-finding state (`existing`/`new`) and unseen fingerprints as `fixed` only for complete runs; partial unseen entries have `fixed=None`, `fixedReason="partial run"`. Baseline entries include `ruleId`. `write(path: Path, findings: Sequence[Finding]) -> None` emits stable sorted keys `fingerprint,target,ruleId,message,observed`, masked messages, and no timestamp/version.

- [ ] **Step 1: Failing tests.** `test_baseline_schema_and_sorted_bytes`, `test_baseline_rejects_bad_schema`, `test_baseline_rejects_duplicate_fingerprint`, `test_compare_existing_new_and_fixed`, `test_partial_unseen_is_null_with_reason`, `test_baseline_write_masks_values`, `test_count_gate_increase_is_new`.
- [ ] **Step 2: Run `tests/engine/testsession/test_baseline.py`; expected named assertion failures.**
- [ ] **Step 3: Implement read/compare/write.** `observed` is null for non-count findings; a count increase changes a listed fingerprint to `new`.
- [ ] **Step 4: Run targeted tests; expected PASS.**
- [ ] **Step 5: Commit** `feat: add stable sharpit baseline format and comparison`.

### Task 2: Apply baselines to gates and advisor findings

**Files:** Modify `gates.py`, `engine/advisors/findings.py`, advisor assessment entry points including `engine/collectors/restapi/service.py`; tests under `tests/engine/testsession/` and advisor tests.

**Interfaces:** Add `Finding.observed: int | None = None`, emitted by `Finding.to_dto`; preserve `observed` and `baselineState` through `engine/testsession/facts.py::_finding_from` and `Finding.to_dto`. Extend `gates.evaluate_test` with optional baseline input and annotate findings with `baselineState`. Only `not dismissed and baselineState != "existing"` fails. Preserve existing calls with no baseline.

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

- [ ] **Step 1: Failing tests.** Review Focus 1; `test_report_only_does_not_fail_finding_test`, `test_report_only_junit_finding_without_failure`, `test_report_only_unknown_reason_fails`, `test_report_only_still_fails_on_unknown_reason_when_status_is_fail`, `test_report_only_allow_unknown_exits_zero`, `test_report_only_mode_report_and_summary`, `test_fail_on_still_selects_advisor_findings`.
- [ ] **Step 2: Run targeted tests; expected report, JUnit and exit assertions fail.**
- [ ] **Step 3: Implement mode-specific behavior without changing gate/advisor computation.**
- [ ] **Step 4: Run targeted plugin/outcome tests; expected PASS.**
- [ ] **Step 5: Commit** `feat: add report-only pytest mode with unknown guard`.

### Task 5: Wire read/write options and baseline lifecycle

**Files:** Modify plugin option modules/hooks, baseline/report modules and both `report.schema.json` copies; tests `tests/pytest_plugin/test_plugin_baseline.py`, `tests/test_report_schema.py`; update report contract under `docs/reference/`.

**Interfaces:** `--sharpit-baseline=PATH` / ini `sharpit_baseline`; `--sharpit-write-baseline=PATH` / ini `sharpit_write_baseline`. Bad/unreadable input raises `pytest.UsageError` at session start. Load baseline on every worker. Write only for complete runs with zero unknown reasons; otherwise session-end `pytest.UsageError` and destination absent/unchanged. `outcome.py::session_status` and `testsession/finish.py::finish` always compute unknown reasons, including when aggregate status is `fail`; `_failing_tests` and `_fail_reasons` exclude findings with `baselineState == "existing"`. Compute `fixed` on the controller from merged findings, never per worker. Report adds `baseline: null | {path,sha256,existing,new,fixed,fixedReason}` plus finding `baselineState` and `observed`, all keys emitted. Per-finding dismissals are Task 6's conditional step (the second of D1 and G1G2 to merge wires `dismissed_pairs()`); preserve the existing `DismissalStore.list()` rule-id behavior.

- [ ] **Step 1: Failing tests.** `test_bad_baseline_usage_error_at_session_start`, `test_write_baseline_is_only_writer`, `test_write_refuses_partial_run`, `test_write_refuses_any_unknown_even_when_status_fail`, `test_write_refusal_leaves_file_absent`, `test_baseline_loaded_on_every_xdist_worker`, `test_report_baseline_counts_and_nulls`, `test_schema_accepts_additive_baseline_fields`, `test_schema_copies_identical`, and canonical `test_write_baseline_refused_on_partial_xdist_run`.
- [ ] **Step 2: Run tests; expected assertions fail.**
- [ ] **Step 3: Implement lifecycle and synchronized schema changes.**
- [ ] **Step 4: Run targeted tests and four gates; expected PASS.** Update the lane-owned handoff with current head and next step; the coordinator stores gate output separately in integration evidence.
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

- [ ] **Step 1:** Add `test_report_only_advisor_error_is_unknown` for an errored REST API advisor rule mapped to sharpit `SKIPPED`; assert its limitation is an unknown reason and report-only still exits 1 by default.
- [ ] **Step 2:** Add `test_partial_run_from_worker_selection_only` and `test_partial_run_from_controller_stop_only` so no single source of partial facts is omitted.
- [ ] **Step 3:** Add `test_baseline_bytes_stable_across_runtime_values` for timestamp/version omission and sorted stable JSON bytes.
- [ ] **Step 4:** Add `test_fixed_reason_null_on_complete_run` and `test_fixed_reason_partial_run_exact_string` for exact nullability and `partial run` contract.
- [ ] **Step 5:** Assert a baseline-listed finding with increased `observed` is `new` in both report and gate behavior; it must remain `dismissed: false`.

### Definition of the report additions

Schema and render tests pin baseline object keys (`path`, `sha256`, `existing`, `new`, `fixed`, `fixedReason`) and finding keys (`baselineState`, `observed`) with nulls emitted. Hash exact loaded baseline bytes, not a reserialized object, so path provenance and review diffs remain reproducible.

- [ ] **Step 1:** Assert baseline summary counts equal per-finding states, with vulnerability findings excluded from every count.
- [ ] **Step 2:** Assert a missing baseline emits `baseline: null`, `baselineState: null`, and `observed: null` in rendered output.
- [ ] **Step 3:** Assert schema validation accepts older reports without additive fields and new reports with them.

### Task 6 (council round 2): failing predicate, status tuple, errored rules, per-finding dismissals

**Files:** `src/sharpit/engine/testsession/gates.py`, `src/sharpit/engine/testsession/outcome.py`,
`src/sharpit/engine/collectors/restapi/service.py`, F's post-split pytest-plugin modules (F table), tests under
`tests/engine/testsession/` and `tests/pytest_plugin/`.

**Interfaces:**
- `gates.fails(dto: Mapping[str, Any]) -> bool` = `not dto["dismissed"] and dto.get("baselineState") != "existing"
  and dto["severity"] != "INFO"`; used by `pytest_runtest_makereport` (F's post-split module) and
  `outcome._failing_tests`. Nothing else decides whether a finding fails.
- `outcome.session_status(...) -> SessionStatus` where `class SessionStatus(NamedTuple): status: str;
  fail_reasons: list[str]; unknown_reasons: list[str]`; unknown reasons are computed even when `status == "fail"`.
  Every caller of `session_status` is updated; `exit_fails(...)` takes `unknown_reasons` from it.
- `restapi/service.py::_run`: an errored rule yields `RuleResult.skipped(rule)` (the existing constructor in
  `engine/advisors/rules.py`) plus an unknown reason; `RestApiService.summary` counts `SKIPPED`.
- Per-finding dismissals: if D1 is already merged when this lane starts, wire `DismissalStore.dismissed_pairs()` into
  the dismissed set the plugin loads (F's post-split module, not the stale `__init__.py:241`) and match
  `(f.rule_id, f.identity or f.target)`; if D1 merges after this lane, D1 does it. Either way the second lane to merge
  owns `test_per_finding_dismissal_reaches_gate`.

- [ ] **Step 1: Failing tests.** `test_fails_excludes_existing_and_info` (a baselined `existing` finding and an `INFO`
  finding do not fail; a `HIGH` new one does), `test_session_status_reports_unknown_reasons_when_fail`,
  `test_errored_rule_is_skipped_with_unknown_reason`, and, if D1 is merged, `test_per_finding_dismissal_reaches_gate`.
  Expected red: the assertions (no `fails`, `session_status` returns a 2-tuple or drops unknown reasons, errored rules
  are `FAILED`), never an import error.
- [ ] **Step 2: Implement** the predicate, `SessionStatus`, the errored-rule mapping and (if applicable) the dismissal
  wiring; update every caller found by `grep -rn "session_status\|_failing_tests" src tests`.
- [ ] **Step 3: Run** the four gates; `test_schema_copies_identical` already exists and is not a red.
- [ ] **Step 4: Commit** `feat: one failing predicate and unknown reasons alongside fail`.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/G1G2/` contains implementer-owned `handoff.md`, `findings.md`, `field-map.md` (`N/A — not a panel lane`), and `checklist.md`. Checklist follows spec §6.1 items 1–10 in order, mapped to owning tasks with evidence paths or `N/A` plus reason. Coordinator/reviewer alone creates `review.md`, `gate/<name>.log` for ruff-check, ruff-format, pyright, pytest, lowest-direct and no-sqlalchemy, and `live-verify.md` in integration; lane diff cannot touch these.

## Canonical lane conventions (C1–C8)

- Lane id is exactly `G1G2`; evidence folder is `.superpowers/sdd/0.4.0/lanes/G1G2/`.
- All lanes consume module names and signatures in F's consumer interface table.
- Golden fixture paths and `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` follow C3, with no flat panel files.
- A red is a defect-naming assertion, not import/collection failure. Spike tests assert desired behavior and are red on 0.3.0.
- Do not edit shared `tests/test_safety_matrix.py` or `tests/test_masking_corpus.py`; use `tests/safety/test_g1g2_safety.py` and `tests/masking/test_g1g2_masking.py`.
- PLAN.md Review Focus names are canonical; use `test_report_only_still_fails_on_unknown_reason_when_status_is_fail` and `test_write_baseline_refused_on_partial_xdist_run` verbatim.
- Dependencies are exactly `F, D1, G6`; no stale wave or P1–P3 names.
- §6.1 checklist follows its ten items in order, attributed to the owning task; non-panel items are `N/A` with reason.

| Spec §6.1 item | G1G2 task / evidence owner |
|---|---|
| 1 Golden parity | N/A — report-only/baseline lane, not a panel lane. |
| 2 Ported behavior tests | N/A — no BootUI panel behavior is ported. |
| 3 Safety and masking | N/A — no panel data source or new secret source. |
| 4 Gatekeeper | N/A — no new library import. |
| 5 Hot-path overhead | N/A — no hot-path listener or middleware change. |
| 6 MCP read-only surface | N/A — no MCP surface change. |
| 7 Svelte view | N/A — no panel view. |
| 8 Four gates | Task 5: run targeted tests and four gates; coordinator owns gate logs. |
| 9 Live check | N/A — no panel implementation; integration reviewer owns live verification. |
| 10 Handoff | Task 5: include current lane handoff with baseline/report evidence. |

## Definition of done

- [ ] Tasks 1–5 cover every §5.1–§5.2 rule, including xdist partial runs, unknown precedence, schema additions, and baseline stability.
- [ ] `tests/test_report_schema.py` confirms copies match and rendered reports validate.
- [ ] Lane evidence passes foundation `scripts/dev/lane_gate.py`; protected paths remain untouched.
