# T-swallowed-exceptions — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans. Best-effort lane 2; Task 0 is mandatory before implementation.

**Goal:** Detect broad application handlers that swallow exceptions during a test, gate them by
default, and flag the same pattern in statically inspected route handlers.

**Architecture:** A pytest adapter claims a `sys.monitoring` tool id for the test session and
records `RAISE`/`EXCEPTION_HANDLED` events from application files. A framework-free engine
module parses handler ASTs once per code object and emits per-test findings; session teardown
frees the tool id. The FastAPI advisor reuses the AST predicate over route handler modules
without calling user code.

**Tech Stack:** Python >=3.12, `sys.monitoring`, stdlib `ast`, pytest, existing test-session
gates and report-only/baseline machinery.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §§5.5 F1, 5.1–5.2,
10.2–10.3, 11.

## Header and ownership

- **Lane:** T-swallowed-exceptions (best effort 2; F1).
- **Worker profile:** L, judgement-heavy (monitoring lifecycle, AST handler semantics, gating).
- **Dependencies:** F and G1G2 merged; T-n-plus-one-message has no API dependency. Best-effort
  order follows §2.
- **May touch:** create `src/sharpit/engine/testsession/swallowed.py`;
  `src/sharpit/engine/testsession/gates.py` (`evaluate_test`, line 34), `facts.py`
  (`PhaseFacts`, `TestFacts`); create `src/sharpit/pytest_plugin/swallowed.py`; post-F
  `src/sharpit/pytest_plugin/session.py` extracted from existing `pytest_sessionstart`
  (`__init__.py:309`), per-test hooks (`:325`, `:428`) and `pytest_sessionfinish` (`:646`); if F
  does not extract this responsibility, Task 3 creates `session.py` and the plugin facade
  delegates the hooks to it; `src/sharpit/engine/collectors/restapi/rules.py` (`evaluate`, line 732)
  and advisor tests; create `tests/engine/testsession/test_swallowed.py`, modify
  `tests/engine/testsession/test_gates.py`, create
  `tests/pytest_plugin/test_plugin_swallowed.py`, modify rest-api rule tests; create
  `tests/engine/test_swallowed_overhead.py`; fixture app
  `tests/fixtures/apps/swallowed_exception/`; lane evidence folder.
- **Must not touch:** `engine/sqla.py` (SQLAlchemy lanes), G6 app/terminal modules,
  report/baseline schema unless G1G2 coordinates an additive finding field before branch; other
  lanes' modules, guard/masking/panel files, `scripts/dev/lane_gate.py`, import-boundary rules,
  overhead constants, complexity/sonar baselines, dependency lists or `uv.lock`.

## Global constraints

- Monitoring runs only during a pytest session; if another tool holds the id, report `attached:
  false` without crashing.
- Restrict observation to project/application files: exclude stdlib, site-packages and sharpit
  using the established application-frame rule.
- A candidate handler catches bare, `Exception`, or `BaseException`; exclude handlers that
  re-raise or call a logger/`warnings`.
- Markers, report-only and baselines apply; preserve `sharpit-report/1`, fingerprint semantics,
  and host exception behavior.
- Every test reproduces the spike fixture and names the expected 0.3.0 miss.

## Review Focus

1. **Raise/handled pairing and event ordering within one test:**
`test_raise_handled_pair_is_test_local`, `test_spike_f1_counts_swallowed_attribute_error` in
Task 2.
2. **Narrow catches, logging, warnings, re-raise, nested handlers:**
`test_ignores_narrow_or_observable_handlers`, `test_nested_handler_uses_handled_location`,
`test_handler_ast_cached_per_code_object` in Task 1.
3. **Non-app frames, tool-id contention, cleanup after failure:**
`test_application_file_filter`, `test_tool_id_conflict_reports_unattached`,
`test_monitoring_tool_freed_at_session_end` in Task 2.
4. **Gate relax/report-only/baseline interaction:** `test_allow_swallowed_marker`,
`test_swallowed_respects_report_only_and_baseline` in Task 3.
5. **Monitoring overhead:** `test_swallowed_monitoring_overhead_budget` in Task 4; no budget is
raised or marked slow.

---

### Task 0: Run required prediction gate

**Files:** None; save output to `.superpowers/sdd/0.4.0/lanes/T-swallowed-exceptions/predict.md`
.

**Interfaces:** Consumes approved spec §5.5 and F1 spike evidence. Produces a `/sharpit:predict`
decision before code because monitoring adds a new always-on-in-tests source; follow a NO-GO or
mitigation call before proceeding.

- [ ] **Step 1:** Run `/sharpit:predict` for test-session-only `sys.monitoring` events,
  broad-handler AST interpretation, and default gate impact; include the spike's
  `get_week_count` case.
- [ ] **Step 2:** Record verdict, confidence, personas, risks and mitigations in `predict.md`;
  expected output is a documented GO/CAUTION decision, not code.
- [ ] **Step 3:** If CAUTION, apply prescribed mitigations in later tasks; if NO-GO, stop and
  park the lane with rationale.

### Task 1: Reproduce F1 in a fixture app before implementation

**Files:** Create fixture app `tests/fixtures/apps/swallowed_exception/`; create
`tests/pytest_plugin/test_plugin_swallowed.py`.

**Interfaces:** No product interface yet. The fixture models `get_week_count`, exposes an
endpoint returning the incorrect zero count with HTTP 200, and runs under the existing
`--sharpit` plugin/report path.

- [ ] **Step 1:** Copy the minimal spike behavior: `Week.week_id` is missing and evaluated
  inside `try/except Exception: return 0`; add one clean and one planted test case.
- [ ] **Step 2:** Add `test_spike_f1_counts_swallowed_attribute_error`; assert current report
  `totals.exceptions == 0`, no `sharpit.swallowed-exception` finding, while the endpoint returns
  200 and `week_count == 0`. Use `--sharpit-app=fixture:app` for the advisor path so the test
  isolates the missing swallowed-exception signal.
- [ ] **Step 3:** Run the fixture against 0.3.0. Expected red is the regression assertion for
  the absent finding; collection, imports and upstream test assertions succeed.
- [ ] **Step 4:** Commit `test: reproduce swallowed application exception spike`.

### Task 2: Specify and test the AST handler predicate

**Files:** Create `src/sharpit/engine/testsession/swallowed.py` and
`tests/engine/testsession/test_swallowed.py`; create
`tests/engine/collectors/restapi/test_swallowed_rule.py` to exercise
`src/sharpit/engine/collectors/restapi/rules.py`.

**Interfaces:** `handler_swallows(source: str, handled_line: int) -> bool`; code-object helper
`handler_swallows_code(code: CodeType, handled_line: int) -> bool`. Parsed AST is cached per
code object. No pytest, FastAPI or SQLAlchemy imports in engine.

- [ ] **Step 1: Write failing tests** `test_detects_bare_and_broad_catches`,
  `test_ignores_narrow_catch`, `test_ignores_reraise`, `test_ignores_logger_and_warnings_calls`,
  `test_nested_handler_uses_handled_location`, `test_ast_cache_is_per_code_object`; static
  advisor cases `test_fastapi_err_rule_flags_swallowed_broad_handler` and
  `test_fastapi_err_rule_ignores_logged_handler`.
- [ ] **Step 2: Run tests on 0.3.0;** expected new predicate/rule assertions fail while imports
  and collection succeed.
- [ ] **Step 3: Implement cached AST analysis** using the `EXCEPTION_HANDLED` code location to
  select the handler; match only §5.5 conditions.
- [ ] **Step 4: Verify** static advisor scans declared route handler modules without invoking
  handlers; add new `FASTAPI-ERR-*` rule text marked new per §5.5.
- [ ] **Step 5: Commit** `feat: analyze broad exception handlers for swallowed errors`.

### Task 3: Capture swallowed exceptions with sys.monitoring

**Files:** Create `src/sharpit/pytest_plugin/swallowed.py`; modify
`src/sharpit/engine/testsession/facts.py` and the post-F plugin test-session hook module; extend
`tests/pytest_plugin/test_plugin_swallowed.py` from Task 1.

**Interfaces:** `MonitoringCapture.attach(sink: SwallowedSink, project_roots: Sequence[Path]) ->
CaptureStatus`; `detach() -> None`; status reports `attached: bool` and reason. Adapter
registers `RAISE` and `EXCEPTION_HANDLED` callbacks, pairs exception identity only within the
current test tag, and sends qualifying events to engine analysis. Add `PhaseFacts.swallowed:
list[SwallowedFact]` with handler file/line, type and safe target only; do not retain raw
locals.

- [ ] **Step 1:** Add `test_raise_handled_pair_is_test_local`, `test_application_file_filter`,
  `test_tool_id_conflict_reports_unattached`, and `test_monitoring_tool_freed_at_session_end`
  against the capture API from Task 2.
- [ ] **Step 2:** Run targeted tests; expected missing API/status assertions fail; the Task 1
  spike regression remains independently red.
- [ ] **Step 3: Implement capture and lifecycle.** Claim with `sys.monitoring.use_tool_id`;
  conflict gives unattached status. Filter application frames, pair raised/handled events for
  the same test, cache AST by code object, detach and free tool at session finish even after
  hook errors.
- [ ] **Step 4: Verify** pairing, app-frame filter, tool-id conflict and cleanup; hook errors
  warn and never change test results or exception behavior.
- [ ] **Step 5: Commit** `feat: observe swallowed application exceptions in tests`.

### Task 4: Gate, marker, report-only and baseline behavior

**Files:** Modify `src/sharpit/engine/testsession/gates.py`, `facts.py`,
`src/sharpit/pytest_plugin/marker.py`; post-F plugin finish/report module; tests
`tests/engine/testsession/test_gates.py`, `tests/pytest_plugin/test_plugin_swallowed.py`.

**Interfaces:** Add rule id `sharpit.swallowed-exception`; extend `Budget` with
`allow_swallowed: bool = False`; `evaluate_test(...)` emits a HIGH `Finding` per qualifying
handler. Marker `@pytest.mark.sharpit(allow_swallowed=True)` relaxes it. Integrate through
existing report-only and baseline evaluation; no new schema field is required beyond `Finding`
DTO.

- [ ] **Step 1: Write failing tests** `test_swallowed_exception_fails_test_by_default`,
  `test_allow_swallowed_marker`, `test_bare_exception_handler_gates`, and Review Focus 4. Assert
  report includes the rule id, marker suppresses only gate failure, report-only records without
  failing, and baseline behavior applies.
- [ ] **Step 2: Run on 0.3.0;** expected rule and marker assertions fail; fixture's visible
  wrong result remains demonstrable.
- [ ] **Step 3: Implement** gate and marker semantics; keep messages sanitized and avoid source
  snippets/local values.
- [ ] **Step 4: Verify** default gate, explicit marker, report-only, baseline and xdist fact
  serialization.
- [ ] **Step 5: Commit** `feat: gate swallowed exception findings`.

### Task 5: Add a monitoring overhead budget

**Files:** Create `tests/engine/test_swallowed_overhead.py`; reuse `tests/overhead.py::paired`
and `check_budget`; see `docs/development/overhead-budgets.md`.

- [ ] **Step 1:** Add a paired representative workload with monitoring disabled/enabled; assert
  workload result and exception counts match; add `test_swallowed_monitoring_overhead_budget`
  with a threshold based on measured overhead plus normal harness margin.
- [ ] **Step 2:** Measure and record rounds/noise; never edit shared budget constants or
  skip/deselect the test.
- [ ] **Step 3:** Verify the budget is selected in normal test jobs and no finding appears
  without a qualifying handler.
- [ ] **Step 4: Commit** `test: budget swallowed-exception monitoring overhead`.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/T-swallowed-exceptions/` must contain `predict.md`, `handoff.md`,
`review.md` (fresh reviewer, distinct id, head SHA, last line `VERDICT: APPROVE`), `findings.md`
(each fixed row names red test/output or parked row has reason), `field-map.md` (`N/A — no panel
DTO change; map new finding to Finding DTO`), `checklist.md` with monitoring safety/budget
evidence and non-panel §6.1 items marked N/A, and `gate/` logs for four gates plus
lowest-direct/no-SQLAlchemy pinned to head SHA.

## Definition of done

- [ ] Task 0 prediction decision is recorded; NO-GO parks lane before implementation.
- [ ] Task 1 static predicate and advisor rule obey exact broad-catch/log/re-raise conditions.
- [ ] Task 2 reproduces F1 red on 0.3.0, uses monitoring only in test session and releases its
  tool id.
- [ ] Task 3 gates by default; marker, report-only and baseline semantics are covered.
- [ ] Task 4 overhead budget stays active and is not raised.
