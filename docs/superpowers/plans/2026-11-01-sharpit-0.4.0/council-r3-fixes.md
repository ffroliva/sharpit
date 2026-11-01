# Plan fixes after plan-council round 3 (coordinator's reconciliation, final)

Round 3 verdicts: codex **approve with changes**, claude **approve with changes** (M1–M6), agy **approve with changes**.
Every reviewer said the changes need no further design round. Apply exactly these; verify every symbol against `src/`
and `tests/`. C1–C8 (round 1) and O1–O4 (round 2) stay in force unless amended here.

## R0 General rule (PLAN.md)

**Two lanes whose May-touch lists intersect never run at the same time.** Before starting a lane the coordinator
compares its May-touch list with every lane in flight; any overlap → wait. Known chains (serial in this order):
`A-traces → B-security-logs → D2` (`fastapi/capture.py`), `D2 → D3 → D4` (`engine/tools.py`, `tests/engine/test_tools.py`),
`T-swallowed-exceptions → D4` (`restapi/rules.py`), `A-postgresql → T-n-plus-one-message` (`engine/sqla.py`).

## R1 D1 / G1G2 split (no shared file)

- **F** pre-creates `DismissalStore.dismissed_pairs(self) -> set[tuple[str, str]]` returning `set()` (inert stub) in
  `engine/advisors/dismissals.py`.
- **D1** implements that method's body and the envelope (`/dismissed-findings`, `guard.py`, `panels.py`); it edits
  **no** `restapi/service.py`, `testsession/gates.py`, `advisors/report.py` or `tests/engine/testsession/test_gates.py`.
- **G1G2** owns every matching change: `restapi/service.py` (`_run`, `_scan`: `occurrences` carries `identity or
  target` so `apply_dismissals` can match pairs), `advisors/report.py::apply_dismissals` (real signature, matching
  `(rule_id, identity or target) in pairs`), `testsession/gates.py`, `outcome.py`, `finish.py`; and
  `test_per_finding_dismissal_reaches_gate`, written against a store whose `dismissed_pairs()` returns a fixed pair
  (independent of D1's implementation). Once D1 merges, the real store feeds it with no further wiring.
- The "whichever of D1 and G1G2 merges second" rule is **deleted** everywhere (PLAN, spec §2/§9, D1, G1G2).

## R2 Red replay that cannot be faked (F, lane_gate.py)

- Each task's red is a **red commit**: the failing tests plus the minimal stubs that make them import (a stub returns a
  wrong value, it never raises `NotImplementedError`), commit subject starting `test:`; `findings.md` and `handoff.md`
  record its SHA per red test.
- `lane_gate.py` replays each named red test **at its recorded red SHA** with `--junitxml`, using the integration
  worktree's environment, and requires a `<failure>` whose message starts with `AssertionError` (an `<error>`, a
  collection error or a pass refuses the merge); the same test must pass at the lane head. A review-finding red is
  replayed on the parent of its fix commit. The merge-base overlay is removed.
- Refusal tests: `test_lane_gate_refuses_fake_red`, `test_lane_gate_refuses_missing_red_test`,
  `test_lane_gate_refuses_error_as_red`.

## R3 F's minimum cut (exactly)

Task 1 splits; O4 flag files + `test_unimplemented_panel_has_no_surface`; `lane_gate.py` with its tests (R2, R7);
the golden loader (R9); UI placeholders/wiring; `install(models=...)` → `SharpitContext.models: tuple[object, ...]`
(stored as `tuple(models)`, elements never inspected); **every pre-created settings field** (R4); the three inert pytest
options; `psycopg[binary]`; the import-boundary changes; the `dismissed_pairs()` stub (R1); **an explicit task step
wiring `examples/fastapi_sqla`** (O3: `install(models=Base)`, the optional OTel provider behind the test extra, any
route a panel's live check needs); **MCP stub discovery**: `engine/tools.py` reads per-panel tool modules
`engine/tools04/<id_underscored>.py` (each exporting `TOOLS = ()` until its lane fills it), so no lane edits `tools.py`.
Deferred to F-rest: only the `tests/safety/` and `tests/masking/` packages and test extras other than `psycopg[binary]`.

## R4–R6 F's interface table

- **R4** one row per pre-created settings field: name, type, default, parser, env var (`SHARPIT_…`), consuming lane —
  enumerated from every lane file (at least `security_logs_max_logs`, `postgresql_max_*`,
  `activity_unbounded_read_factor`). No summary row.
- **R5** the exact post-split module and function that constructs `SqlTraceRecorder`.
- **R6** `session_status(...) -> SessionStatus` (NamedTuple `status, fail_reasons, unknown_reasons`), callers
  `outcome.py` and `testsession/finish.py:42`; remove the 2-tuple wording. `test_schema_copies_identical` exists
  already: it is not a red in F (`:71`) or G1G2 (`:93`).

## R7 Leased-database check (lane_gate.py)

For lane `A-postgresql` the gate requires `gate/leased-pg.log` in the integration worktree: the head SHA on line 1,
and `test_read_only_wrapper_rejects_write` and `test_autocommit_engine_is_unavailable` marked `PASSED`. Missing or
skipped → the gate exits 0 only with `--accept-unverified`, which writes `unverified` to the ledger line.

## R8 G1G2 Task 6 (rewrite the errored-rule part)

`_evaluate` already skips errored rules (`service.py:61-63`) and a `PARTIAL` scan already becomes `UNKNOWN`. The real
hole: `AdvisorRun.of` (`advisors/findings.py:70-71`) returns `FAILED` with `reason=None` and drops the limitations when
any finding fails, and `outcome._unknown_reasons` reads only `UNKNOWN` runs, so a failing-and-incomplete run exits 0
under report-only. Fix: `AdvisorRun.of` keeps the incompleteness reason/limitations on a `FAILED` run, and
`_unknown_reasons` emits it. Red: `test_failed_run_with_incomplete_scan_has_unknown_reason`. Delete
`RestApiService.summary` and the `RuleResult.skipped` mapping from the plan (`RuleResult` is the panel DTO).
G1G2's dependency line is `F, G6` everywhere; May-touch adds `testsession/finish.py`.

## R9 Golden paths (O2, final)

F's loader text (Task 3 and the file map) says: reads `<sharpit-id>/captured.json` (or `<name>.captured.json`), else
`provisional.json` (marked unverified), plus `nullable.json`. **G0a's worker** writes `captured.json` and, on the
coordinator's request, `provisional.json` (from BootUI's DTO sources; never the panel lane's worker). Panel lanes own
only `nullable.json`. A-postgresql's May-touch and Task 5 use `postgresql/nullable.json` only.

## R10–R16 per-lane

- **R10 A-postgresql Task 6:** flip `src/sharpit/engine/panels04/postgresql.py` and `ui/src/lib/panels04/postgresql.ts`,
  never `nav.ts`.
- **R11 PLAN Step 5:** add "merge every merged lane's `docs.md` into README / `skills/sharpit/SKILL.md` in one commit";
  dependencies per R0.
- **R12 B-security-logs:** call `on_security_event` **before** `REQUEST.reset(token)` in `CaptureMiddleware.__call__`.
- **R13 D4:** use the real signatures of `advisors/report.py::apply_dismissals` and `restapi/service.py::_run`.
- **R14 G6:** `_worst` ranks `FAILED > UNKNOWN > SKIPPED > PASSED` across workers.
- **R15 A-data:** `models` is `tuple[object, ...]` (R3); the lane inspects elements, F does not.
- **R16 G3:** its header names `src/sharpit/report/__main__.py`.
- **R17 F:** `CaptureState.teardowns: list[Callable[[], None]]`; `uninstall_capture()` runs them in reverse, each guarded;
  A-transactions and A-traces register their removers there.
