# Plan fixes after plan-council round 1 (coordinator's reconciliation, final)

Apply exactly these changes to the lane files you own. Do not reopen decisions. Verify every symbol you write against
`C:\development\github\sharpit-wt\0.4.0-spec\src` and `tests` (real names, real signatures, real line numbers).
The master `PLAN.md` and the spec are edited by the coordinator; read them (r5, after this round) for the canonical
lane ids, dependencies and test names.

## Cross-cutting conventions (every lane file)

- **C1 Lane ids and folders:** the lane id is exactly the PLAN.md id (`F`, `G0a`, `G0b`, `D1`, `G1G2`, `G3`, `G4`,
  `G6`, `A-data`, …, `T-unbounded-read`, `D2`, `D3`, `D4`). Evidence folder = `.superpowers/sdd/0.4.0/lanes/<lane id>/`.
- **C2 Evidence layout (one layout, all lanes):** written by the implementer in the lane worktree: `handoff.md`,
  `findings.md`, `field-map.md` (non-panel lanes write `N/A — not a panel lane`), `checklist.md` (spec §6.1's ten items
  in the spec's order, each with an evidence path or `N/A` + reason). Written by the **coordinator/reviewer in the
  integration worktree only** (never by the implementer): `review.md` and `gate/<name>.log` for `ruff-check`,
  `ruff-format`, `pyright`, `pytest`, `lowest-direct`, `no-sqlalchemy`, and `live-verify.md`. The lane's own diff may
  not touch any `review.md` or `gate/` path (lane_gate refuses it).
- **C3 Golden fixtures (one convention):** `tests/fixtures/bootui/2.2.0/<sharpit-id>/<name>.json` and
  `tests/fixtures/bootui/2.2.0/<sharpit-id>/nullable.json`; loader `tests/golden.py::assert_parity(sharpit_id: str,
  name: str, payload: Mapping[str, Any]) -> None` created by F. No flat `<panel>.json` files.
- **C4 Reds are assertions:** a red is the assertion that names the defect, never an `ImportError`/collection error.
  Spike tests (`test_spike_f<n>_*`) assert the **desired** finding, so they are red on 0.3.0.
- **C5 Shared test files:** no lane edits `tests/test_safety_matrix.py` or `tests/test_masking_corpus.py` directly;
  each lane adds its rows in its own file `tests/safety/test_<lane-id>_safety.py` / `tests/masking/test_<lane-id>_masking.py`
  (F creates both packages with a README and the shared helpers they import).
- **C6 Test names:** the PLAN.md Review Focus test names are canonical; the owning lane uses them verbatim.
- **C7 Dependencies:** a lane header's "Depends on" equals PLAN.md's column; remove stale ids (`P1`–`P3`, "Wave G").
- **C8 §6.1 table:** spec §6.1's ten items in its order (1 golden parity … 10 handoff), each mapped to the task that
  owns it; correct task numbers (the off-by-one in T-swallowed-exceptions and T-unbounded-read).

## F (F-foundation.md)

- F1a: a **table of every module, symbol and signature later lanes consume** (pytest_plugin split modules
  `options.py`, `apps.py`, `session.py`, `terminal.py`, `report_io.py` or the names you choose — choose and fix them;
  `fastapi/routes/<id>.py` per panel incl. `routes/sql_trace.py`; `tests/golden.py::assert_parity`;
  `CaptureState.transactions`; the 401/403 hook and the span slot in `fastapi/capture.py`; MCP stub modules;
  `install(models=)`). Every lane references this table.
- F1b: UI: F creates `ui/src/views/<Panel>.svelte` placeholders for every 0.4 panel and wires them in
  `ui/src/App.svelte`, `ui/src/lib/nav.ts`, `ui/src/lib/types.ts` behind `implemented`; lanes replace only their view.
- F1c: complexity ratchet: F may re-key `tests/complexity_baseline.json` entries for moved code with a per-finding
  total that does not rise (its own test proves it); `lane_gate.py` allows a downstream diff to that file **only**
  when every value decreases or an entry is removed.
- F1d: test extras: OTel SDK, a MySQL driver, **`psycopg[binary]`**.
- F1e: `tests/engine/test_import_boundary.py`: allow `pytest`/`_pytest` in every module under
  `sharpit/pytest_plugin/`; add `"opentelemetry": {"sharpit/engine/otel.py"}`.
- F1f: `lane_gate.py` CLI is `lane_gate.py <lane-id> [--worktree PATH] [--sha SHA] [--integration PATH]`, defaults
  resolved from the lane id (`C:\development\github\sharpit-wt\0.4.0-<lane-id>`, its HEAD, the cwd). Evidence per C2;
  refuses lane diffs touching `.superpowers/sdd/0.4.0/lanes/*/review.md` or `.../gate/`. Re-runs the four gates itself
  (already in the file).
- F1g: creates `tests/safety/` and `tests/masking/` packages (C5).
- F1h: `implemented=False` surface test is named `test_unimplemented_panel_has_no_surface` (C6).

## G1G2

- Baseline entries include `ruleId` (spec §5.2).
- Preserve `observed` and `baselineState` across xdist: `engine/testsession/facts.py::_finding_from` and
  `Finding.to_dto`.
- `outcome.py`: `session_status`/`finish` **always** compute unknown reasons (no early return on `fail`);
  `_failing_tests` and `_fail_reasons` exclude `baselineState == "existing"` findings; `fixed` is computed on the
  controller from merged findings, never per worker.
- Merge D1's per-finding dismissals (`DismissalStore` finding list, whatever D1 names it) into the dismissed set the
  plugin loads (`pytest_plugin/__init__.py:241` today).
- Map an errored advisor rule (`restapi/service.py:59-71`) to `SKIPPED` + an unknown reason.
- Depends on F, D1 and G6 (rebases onto G6's `SKIPPED` support). Canonical tests:
  `test_report_only_still_fails_on_unknown_reason_when_status_is_fail`, `test_write_baseline_refused_on_partial_xdist_run`.

## G6

- Depends on **F only**; runs beside D1; owns the no-app path and `SKIPPED`: may touch
  `engine/advisors/findings.py` (`AdvisorRun.status` gains `"SKIPPED"`), `engine/testsession/outcome.py`
  (`_advisor_summary` at :202-206, `_worst`, `_unknown_reasons`), both `report.schema.json` copies (enum gains
  `SKIPPED`; logged in spec §11).
- Autodetect: iterate `vars(mod).values()` only for `type(mod) is ModuleType` (never `getattr`, never PEP 562
  `__getattr__`); match with `type(v)` and an MRO check against `fastapi.FastAPI`/`starlette.applications.Starlette`
  taken from `sys.modules` only (never import them); dedupe by `id()`; drop apps mounted inside another candidate and
  sharpit's own sub-app; under xdist the chosen app (or candidates) is carried in the report and printed by the
  controller's terminal summary. Exact lines: `sharpit: using app <module>:<attr> (pass --sharpit-app to choose)`;
  `sharpit: several apps found (<m:a>, <m:a>); pass --sharpit-app module:attr`; no app:
  `sharpit: no application found; rest-api skipped (pass --sharpit-app module:attr)`. Tests assert each line in the
  terminal output: `test_autodetect_single_prints_choice`, `test_autodetect_ambiguous_uses_none`,
  `test_autodetect_never_imports`.
- F4: non-failing advisor findings are omitted from `gate counts:` unless `--sharpit-verbose`/`-vv`; the summary adds
  `sharpit: <N> advisor notes in <report path>`.

## G0 (split)

- **G0a goldens:** depends on F (F owns `tests/golden.py` and `ids.json`; G0a populates fixtures under C3 only).
- **G0b tiny-ledger-py:** independent, its own repo, a different worker account from G0a.
- Evidence per C2 for G0a (G0b's evidence lives in tiny-ledger-py and is reported, not gated).

## A-* lanes

- Depends on F only (drop D1). A-postgresql: add a fake-connection test where `in_transaction()` is True and
  `current_setting('transaction_read_only')` is `'off'` → `unavailableReason` (in SQLAlchemy 2, `in_transaction()` is
  True even under AUTOCOMMIT; the setting check is the real guard). Canonical tests:
  `test_read_only_wrapper_rejects_write`, `test_autocommit_engine_is_unavailable` (A-postgresql),
  `test_get_never_configures_mappers` (A-data).

## T-* lanes (spec §5.5 r5 decisions)

- Serial: `G1G2 → T-n-plus-one-message → T-swallowed-exceptions → T-unbounded-read` (they share `facts.py`, `gates.py`,
  `marker.py`); each uses G1G2's `evaluate_test` signature.
- T-n-plus-one-message: relationship identity from `SessionEvents.do_orm_execute` (`orm_execute_state.is_relationship_load`,
  `lazy_loaded_from`, `loader_strategy_path`), tagged via `update_execution_options` and read back in
  `before_cursor_execute`; `prop.direction` picks `selectinload` (collections) vs `joinedload` (many-to-one). Not
  `InstanceEvents.load`. F6 budget: a smaller workload with the same per-statement overhead ratio is allowed (logged).
  Why it depends on A-sqlalchemy-statistics: both extend the SQL recorder; say so in the header.
- T-swallowed-exceptions: subscribe **only to `EXCEPTION_HANDLED`** (global `sys.monitoring.set_events`; `RAISE` is not
  used), callback active only while a test runs (the test contextvar), filtered on the **handler's** code location being
  application code (the raise may be anywhere, e.g. in a library). Tool id: the first free of `sys.monitoring` ids 3 and
  4 (never 0 debugger, 1 coverage, 2 profiler, 5 optimizer); none free → source `attached: false`. **Gating:** fails
  the test by default only for programming-error types (`AttributeError`, `TypeError`, `NameError`, `ImportError`,
  `UnboundLocalError`); every other broad-handler swallow is a non-failing note. Red spike test asserts the T4 case
  (`AttributeError` swallowed) produces a failing finding.
- T-unbounded-read: requires `sharpit.install` (the capture middleware provides the route and the bound `limit`);
  without it the rule reports a limitation and does not fire. Counting is per statement via `InstanceEvents.load`
  (unchanged). The spike fixture app calls `install` in its conftest.

## B-* lanes

- `B-security-logs` runs before `D2` if both run (both edit `fastapi/capture.py`); say so in the header.

## D lanes

- D1: replace invented names with the real ones: `engine/advisors/report.py::apply_dismissals` (not
  `build_advisor_report`), `RestApiService._run` (not `RestApiCollector`), `_read_capped(request, cap)`,
  `security_headers("api")`; error strings verbatim: `"sharpit panel access denied"` (`guard.py:42`) and the real
  `read_only_reason` text (`panels.py:51-55`); drop the claim that `send_with_headers` appends CSP without checking
  (`adapter.py:135-142` already skips). Red is an assertion, not `ImportError` (C4).
- D2: overhead tests are `tests/fastapi/test_capture_overhead.py` and `tests/fastapi/test_sql_trace_overhead.py`;
  `HttpExchangeBuffer.report` gains `route: str | None = None` appended, its five parameters unchanged.
- D3: `sqla.sqlalchemy_module() is not None` (no `is_available`); keep `pools_report(ctx: SharpitContext)` (caller
  `adapter.py:431`).
- D4: depends on G1G2.
