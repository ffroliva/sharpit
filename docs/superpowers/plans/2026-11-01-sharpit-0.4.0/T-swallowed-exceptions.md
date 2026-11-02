# T-swallowed-exceptions — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans. Best-effort lane 5 (PLAN.md); Task 0 is mandatory before implementation.

**Goal:** Detect broad application handlers that swallow exceptions during a test; fail the test
by default only when the swallowed exception is a programming error, record every other swallow
as a non-failing note, and flag the same pattern in statically inspected route handlers (spike F1).

**Architecture:** A pytest adapter claims a `sys.monitoring` tool id for the test session and
subscribes **only** to `EXCEPTION_HANDLED` with the global `sys.monitoring.set_events` (`RAISE`
is not used: it fires on every internal `StopIteration`). The callback returns immediately unless
a test is running (the `TEST` contextvar, `engine/capture/correlation.py:25`) and the **handler's**
code location (the callback's `code` and `instruction_offset`) is application code (the 0.2.0
rule, `engine/capture/frames.py:21::is_application_frame`); the exception may have been raised
anywhere, including a library. A framework-free engine module locates the handler from code and
offset, parses it with stdlib `ast` once per code object, and decides whether it swallows. The
gate classifies by exception type. Session teardown frees the tool id. The `rest-api` advisor
reuses the AST predicate over route handler modules without calling user code.

**Tech Stack:** Python >=3.12, `sys.monitoring`, stdlib `ast`, pytest, existing test-session
gates and G1G2's report-only/baseline machinery.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §5.5 F1 (r5), §5.1–5.2,
§10.2–10.3, §11.

## Header and ownership

- **Lane:** `T-swallowed-exceptions` (best effort 5; F1). Evidence folder
  `.superpowers/sdd/0.4.0/lanes/T-swallowed-exceptions/`.
- **Worker profile:** L, judgement-heavy (monitoring lifecycle, AST handler semantics, gating).
- **Depends on:** T-n-plus-one-message (PLAN.md). The T-* lanes are serial
  `G1G2 → T-n-plus-one-message → T-swallowed-exceptions → T-unbounded-read` because they share
  `engine/testsession/facts.py`, `engine/testsession/gates.py` and `pytest_plugin/marker.py`;
  this lane rebases onto T-n-plus-one-message's `PhaseFacts` additions and uses G1G2's
  `evaluate_test` signature. Consumes these rows of F's consumer interface table
  (`F-foundation.md`): `sharpit.pytest_plugin.session` (session lifecycle/hooks) and
  `sharpit.engine.testsession.gates.evaluate_test`; and G1G2's predicate
  `testsession/gates.py::fails(dto: Mapping[str, Any]) -> bool` (not dismissed, `baselineState !=
  "existing"`, `severity != "INFO"`), which is what keeps this lane's notes non-failing.
  **Ordering (R0):** this lane's May-touch list intersects D4's on
  `src/sharpit/engine/collectors/restapi/rules.py`, so the chain is serial
  `T-swallowed-exceptions → D4`: D4 does not start while this lane is in flight, and rebases onto
  its merge.
- **May touch:** create `src/sharpit/engine/testsession/swallowed.py`;
  `src/sharpit/engine/testsession/gates.py` (`evaluate_test` at `:34`, `Budget` at `:21`),
  `facts.py` (`PhaseFacts` at `:56`, `TestFacts` at `:87`); create
  `src/sharpit/pytest_plugin/swallowed.py`; `src/sharpit/pytest_plugin/session.py` (F's
  `sharpit.pytest_plugin.session` row; today's `pytest_sessionstart` `__init__.py:309`,
  `pytest_runtest_protocol` `:325`, `pytest_runtest_call` `:428`, `pytest_sessionfinish` `:646`)
  only to attach/detach the capture; `src/sharpit/pytest_plugin/marker.py`
  (`budget_for` at `:12`); `src/sharpit/engine/collectors/restapi/rules.py` (`evaluate` at `:731`)
  and its tests; create `tests/engine/testsession/test_swallowed.py`, modify
  `tests/engine/testsession/test_gates.py`, create `tests/pytest_plugin/test_plugin_swallowed.py`,
  create `tests/engine/restapi/test_swallowed_rule.py`; create
  `tests/engine/test_swallowed_overhead.py`; fixture app `tests/fixtures/apps/swallowed_exception/`;
  the implementer files in the lane evidence folder (C2).
- **Must not touch:** `engine/sqla.py` (O1: A-postgresql), `engine/tools.py` (R3), `ui/src/lib/nav.ts` (O4), G6's `pytest_plugin/apps.py` and
  `pytest_plugin/terminal.py` (the notes line is G6's, not this lane's), `README.md`,
  `skills/sharpit/SKILL.md`, `examples/`, `tests/test_example_app.py` (O3: user-facing text goes to
  the lane folder's `docs.md`),
  report/baseline schema (the finding is a `Finding` DTO row; no schema change), other lanes'
  modules, guard/masking/panel files, `scripts/dev/lane_gate.py`, import-boundary rules, existing
  overhead constants, complexity/sonar baselines, dependency lists or `uv.lock`,
  `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (C5), any `review.md` or `gate/`
  path.

## Global constraints

- Monitoring runs only during a pytest session, and the callback does work only while a test
  runs. Tool id: the first free of ids **3 and 4** (`sys.monitoring.get_tool(id) is None`, then
  `use_tool_id`); never 0 (debugger), 1 (coverage), 2 (profiler), 5 (optimizer). None free → the
  source reports `attached: false` with a reason (a limitation, not a crash).
- Events: `EXCEPTION_HANDLED` only, global `set_events`; `RAISE` is never subscribed.
- Filter on the **handler's** code location being application code (not stdlib, not
  site-packages, not sharpit); the raise location is irrelevant.
- A candidate handler catches bare, `Exception`, or `BaseException`, and its body neither
  re-raises nor calls a logger/`warnings`.
- **Gating:** fails the test by default only for programming-error types (`AttributeError`,
  `TypeError`, `NameError`, `ImportError`, `UnboundLocalError`, matched with `isinstance`, so
  `ModuleNotFoundError` counts as `ImportError`); every other swallow is a non-failing note: a
  `Finding` with severity `INFO`, which G1G2's `fails()` excludes. Marker
  `sharpit(allow_swallowed=True)` relaxes; report-only and baselines apply.
- Preserve `sharpit-report/1`, fingerprint semantics, and host exception behaviour.
- A red is the assertion that names the defect (C4); the spike test asserts the **desired**
  failing finding, so it is red on 0.3.0.
- Each task's red is a **red commit** (R2): subject starts `test:`, holding the failing tests plus the
  minimal stubs that make them import; a stub returns a wrong value (`False`, an empty list, no
  finding), it never raises `NotImplementedError`. Its SHA per red test goes into `findings.md` and
  `handoff.md`; `lane_gate.py` replays each test at that SHA with `--junitxml` (needs a `<failure>`
  starting `AssertionError`) and again at the lane head (must pass). The "Run on the base" /
  "Run; expected ... fail" steps below mean this red commit; a review-finding red is replayed on the
  parent of its fix commit.

## Review Focus

1. **Spike F1 reproduced (canonical, PLAN.md Review Focus 7):**
   `test_spike_f1_swallowed_attribute_error_fails` in Task 1 (the T4 `AttributeError` swallowed
   by `except Exception: return 0` produces a **failing** `sharpit.swallowed-exception` finding).
2. **Green 0.3.0 suites stay green (canonical, PLAN.md Review Focus 8):**
   `test_non_programming_error_swallow_is_a_note` in Task 4 (a broad handler swallowing a
   `ValueError` is a note, the test passes).
3. **Narrow catches, logging, warnings, re-raise, nested handlers:**
   `test_ignores_narrow_catch`, `test_ignores_reraise`, `test_ignores_logger_and_warnings_calls`,
   `test_nested_handler_uses_handled_location`, `test_ast_cache_is_per_code_object` in Task 2.
4. **Handler-location filter, out-of-test events, tool-id contention, cleanup after failure:**
   `test_library_raise_app_handler_is_seen`, `test_library_handler_is_ignored`,
   `test_event_outside_a_test_is_ignored`, `test_tool_id_conflict_reports_unattached`,
   `test_monitoring_tool_freed_at_session_end` in Task 3.
5. **Gate relax/report-only/baseline interaction:** `test_allow_swallowed_marker`,
   `test_swallowed_respects_report_only_and_baseline` in Task 4.
6. **Monitoring overhead:** `test_swallowed_monitoring_overhead_budget` in Task 5; no budget is
   raised or marked slow.

---

### Task 0: Run the required prediction gate

**Files:** None in `src/`; save output to
`.superpowers/sdd/0.4.0/lanes/T-swallowed-exceptions/predict.md`.

**Interfaces:** Consumes spec §5.5 F1 (r5) and the spike evidence. Produces a `/sharpit:predict`
decision before code because monitoring adds a new always-on-in-tests source; follow a NO-GO or
mitigation call before proceeding.

- [ ] **Step 1:** Run `/sharpit:predict` for test-session-only `EXCEPTION_HANDLED` monitoring,
  broad-handler AST interpretation, and the type-based default gate; include the spike's
  `get_week_count` case.
- [ ] **Step 2:** Record verdict, confidence, personas, risks and mitigations in `predict.md`.
- [ ] **Step 3:** If CAUTION, apply the mitigations in later tasks; if NO-GO, stop and park the
  lane with rationale.

### Task 1: Reproduce F1 in a fixture app before implementation

**Files:** Create fixture app `tests/fixtures/apps/swallowed_exception/`; create
`tests/pytest_plugin/test_plugin_swallowed.py`.

**Interfaces:** No product interface yet. The fixture models `get_week_count`, exposes an
endpoint returning the incorrect zero count with HTTP 200, and runs under the existing
`--sharpit` plugin/report path.

- [ ] **Step 1:** Copy the minimal spike behaviour: `Week.week_id` is missing and evaluated inside
  `try/except Exception: return 0` (an `AttributeError`, spike T4); add one clean test and one
  test that hits the planted handler.
- [ ] **Step 2:** Add the pytester test `test_spike_f1_swallowed_attribute_error_fails`; assert
  the **desired** outcome: the report has a `sharpit.swallowed-exception` finding for the planted
  test, and that test's outcome is failed (one condition per assert). Use
  `--sharpit-app=fixture:app` so app discovery does not obscure the result.
- [ ] **Step 3:** Run on the base. Expected red: the assertion on the finding fails (0.3.0
  records no such finding; the endpoint returns 200 with `week_count == 0`); collection and
  imports succeed. Quote the red in `findings.md`.
- [ ] **Step 4:** Commit `test: reproduce swallowed application exception spike` (this is the red
  commit, R2); record its SHA for `test_spike_f1_swallowed_attribute_error_fails` in `findings.md`
  and `handoff.md`.

### Task 2: Specify and test the AST handler predicate

**Files:** Create `src/sharpit/engine/testsession/swallowed.py` and
`tests/engine/testsession/test_swallowed.py`; create `tests/engine/restapi/test_swallowed_rule.py`
to exercise `src/sharpit/engine/collectors/restapi/rules.py`.

**Interfaces:** `handler_swallows(source: str, handled_line: int) -> bool`; code-object helper
`handler_swallows_code(code: CodeType, offset: int) -> bool` (line from `code.co_positions()` at
the offset). Parsed AST is cached per code object. `PROGRAMMING_ERRORS = (AttributeError,
TypeError, NameError, ImportError, UnboundLocalError)`; `is_programming_error(exc: BaseException)
-> bool`. No pytest, FastAPI or SQLAlchemy imports in the engine.

- [ ] **Step 1: Write failing tests** `test_detects_bare_and_broad_catches`,
  `test_ignores_narrow_catch`, `test_ignores_reraise`, `test_ignores_logger_and_warnings_calls`,
  `test_nested_handler_uses_handled_location`, `test_ast_cache_is_per_code_object`,
  `test_programming_error_types`; static advisor cases
  `test_fastapi_err_rule_flags_swallowed_broad_handler` and
  `test_fastapi_err_rule_ignores_logged_handler`.
- [ ] **Step 2: Commit the red** (`test: swallowed-handler predicate reds`, stubs return the
  wrong value) and run it; expected predicate/rule assertions fail, never an `ImportError` or
  `NotImplementedError` (C4, R2).
- [ ] **Step 3: Implement cached AST analysis** selecting the handler from the
  `EXCEPTION_HANDLED` code location; match only the §5.5 conditions.
- [ ] **Step 4: Verify** the static advisor scans route handler modules without invoking
  handlers; new `FASTAPI-ERR-*` rule text marked N (new) per §5.5.
- [ ] **Step 5: Commit** `feat: analyze broad exception handlers for swallowed errors`.

### Task 3: Capture swallowed exceptions with sys.monitoring

**Files:** Create `src/sharpit/pytest_plugin/swallowed.py`; modify
`src/sharpit/engine/testsession/facts.py` and the post-F session hook module; extend
`tests/pytest_plugin/test_plugin_swallowed.py`.

**Interfaces:** `TOOL_IDS = (3, 4)`; `MonitoringCapture.attach(sink: SwallowedSink) ->
CaptureStatus` (claims the first free id, `set_events(id, EXCEPTION_HANDLED)`, registers one
callback) and `detach() -> None` (`set_events(id, 0)`, `register_callback(id, …, None)`,
`free_tool_id`); `CaptureStatus` reports `attached: bool` and a reason. Callback
`(code, instruction_offset, exception)`: return at once when `TEST.get() is None` or the code's
file is not application code; otherwise ask the engine predicate and send a qualifying event.
Add `PhaseFacts.swallowed: list[SwallowedFact]` (handler file/line, exception type name,
`programming_error: bool`; never raw locals or the message), serialised for xdist.

- [ ] **Step 1:** Add `test_library_raise_app_handler_is_seen`, `test_library_handler_is_ignored`,
  `test_event_outside_a_test_is_ignored`, `test_tool_id_conflict_reports_unattached` (ids 3 and 4
  both claimed → `attached: false`, no crash), `test_monitoring_tool_freed_at_session_end`
  (also after a hook error), `test_raise_is_not_subscribed` (`sys.monitoring.get_events(id)`
  equals `EXCEPTION_HANDLED` only).
- [ ] **Step 2:** Commit the red (`test: monitoring capture reds`, wrong-value stubs) and run;
  expected status/event assertions fail; the Task 1 spike stays red.
- [ ] **Step 3: Implement capture and lifecycle**; hook errors warn once and never change test
  results or exception behaviour.
- [ ] **Step 4: Verify** the filter, contention and cleanup tests green.
- [ ] **Step 5: Commit** `feat: observe swallowed application exceptions in tests`.

### Task 4: Gate, marker, report-only and baseline behaviour

**Files:** Modify `src/sharpit/engine/testsession/gates.py`, `facts.py`,
`src/sharpit/pytest_plugin/marker.py`; the post-F finish/report module; tests
`tests/engine/testsession/test_gates.py`, `tests/pytest_plugin/test_plugin_swallowed.py`.

**Interfaces:** Rule id `sharpit.swallowed-exception`; `Budget` (`gates.py:21`) gains
`allow_swallowed: bool = False` (and `marker.budget_for` reads it, as `allow_n_plus_one` today).
`gates.py::_finding` (`:27`, which hard-codes `"HIGH"` today) gains a keyword `severity: Severity =
"HIGH"` (`Severity` from `engine/advisors/rules.py:12`; the fingerprint ignores severity, so
existing fingerprints are unchanged). `evaluate_test` keeps the signature G1G2 leaves it with (no
new parameter) and emits, per qualifying handler, a `HIGH` `Finding` when `programming_error` is
true and the marker does not relax it; otherwise a `Finding` with severity `INFO` (a note).
Whether a finding fails the test is decided only by G1G2's `fails()` (it excludes `INFO`); this
lane adds no note count or terminal line. Report-only and baselines apply through G1G2's
machinery; no new schema field beyond the `Finding` DTO.

- [ ] **Step 1: Write failing tests** `test_swallowed_attribute_error_fails_test_by_default`,
  `test_non_programming_error_swallow_is_a_note` (canonical; a `ValueError` swallowed → test
  passes; the finding is present with `severity == "INFO"`; `fails(dto)` is false),
  `test_allow_swallowed_marker`,
  `test_bare_exception_handler_gates`, `test_swallowed_respects_report_only_and_baseline`.
- [ ] **Step 2: Commit the red** (`test: swallowed-exception gate reds`, wrong-value stubs) and run;
  expected rule and marker assertions fail.
- [ ] **Step 3: Implement** gate and marker semantics; messages sanitised, no source snippets or
  local values.
- [ ] **Step 4: Verify** default gate, `INFO` note, explicit marker, report-only, baseline, xdist
  fact serialisation, and `test_spike_f1_swallowed_attribute_error_fails` green.
- [ ] **Step 5: Commit** `feat: gate swallowed exception findings`.

### Task 5: Add a monitoring overhead budget

**Files:** Create `tests/engine/test_swallowed_overhead.py`; reuse `tests/overhead.py::paired`
(`:65`) and `check_budget` (`:38`); see `docs/development/overhead-budgets.md`.

- [ ] **Step 1:** A paired workload with monitoring off/on that raises and handles exceptions in
  library and application code; assert workload result and event counts match; add
  `test_swallowed_monitoring_overhead_budget` with a threshold from the measured overhead plus the
  normal margin (a new constant in the new file); prove it bites (temporary sleep in the callback).
- [ ] **Step 2:** Measure and record rounds/noise in `handoff.md` and `checklist.md` item 5; never
  edit shared budget constants or skip/deselect the test.
- [ ] **Step 3:** Verify the budget runs in normal test jobs and no finding appears without a
  qualifying handler.
- [ ] **Step 4: Commit** `test: budget swallowed-exception monitoring overhead`.

## §6.1 → task (spec order; non-panel lane, `checklist.md` adds the evidence paths)

| Item | Task |
|---|---|
| 1 golden parity, `nullable.json`, field map | `N/A`: not a panel lane |
| 2 `# ported:` citations | `N/A`: no BootUI behaviour ported (spike tests cite `# spike: F1 T4`) |
| 3 safety (`no_side_effects`, masking) | 3–4 (no locals or messages retained; no GET/MCP surface) |
| 4 gatekeeper | 2–3 (`sys.monitoring`/`ast` are stdlib; no `pytest` outside `pytest_plugin/`; boundary test green) |
| 5 overhead budget | 5 |
| 6 MCP read-only | `N/A`: no MCP tool |
| 7 Svelte view | `N/A`: no UI |
| 8 four gates + lowest-direct + no-SQLAlchemy | 4–5 (gated logs: coordinator) |
| 9 live check | `N/A`: test-session feature; the pytester spike test is the end-to-end check |
| 10 handoff current | every commit |

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/T-swallowed-exceptions/`)

- **Implementer, in the lane worktree:** `predict.md` (Task 0), `handoff.md` (last green command,
  next step, open findings, measured overhead), `findings.md` (`finding → test → red output`, each
  row `fixed` + red-test name or `parked` + reason; the F1 red quoted), `field-map.md` (`N/A — not a
  panel lane`), `checklist.md` (the ten §6.1 items above in order, each with an evidence path or
  `N/A` + reason).
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`,
  reviewer id ≠ implementer id, head SHA), `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path.

## Definition of done

- [ ] Task 0 prediction decision is recorded; NO-GO parks the lane before implementation.
- [ ] Task 1 reproduces F1 red on the base for the right reason.
- [ ] Task 2 static predicate and advisor rule obey the exact broad-catch/log/re-raise conditions.
- [ ] Task 3 uses `EXCEPTION_HANDLED` only, only while a test runs, filters on the handler's
  location, claims id 3 or 4 and releases it.
- [ ] Task 4 fails by default only for programming-error types; other swallows are `INFO`
  findings that `fails()` excludes; marker, report-only and baseline semantics are covered.
- [ ] Task 5 overhead budget stays active and is not raised.
