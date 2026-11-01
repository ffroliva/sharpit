# F — Foundation Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. One task at a time; this lane is first and behaviour-neutral.

**Goal:** Prepare the 0.4.0 integration branch with responsibility splits, inert panel stubs, shared hook points, fixtures, and a mechanical lane gate while preserving the exact current test behavior.

**Architecture:** Split the three oversized owners by responsibility, keeping compatibility imports and hook behavior unchanged. Pre-register new panel ids as unimplemented so registries, routes, MCP, CLI, and nav cannot expose them until an owning lane flips its flag. Add shared test/document infrastructure without enabling any feature.

**Tech Stack:** Python 3.12+, pytest/pytester, Starlette, Svelte 5/TypeScript; no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §§10.2–10.3, 10.6; panel contract §6.1; lane order §13.

## Header and ownership

- **Lane:** F (foundation; must merge before any fan-out).
- **Worker profile:** L, judgement-heavy (responsibility splits, import behavior, gate safety).
- **Dependencies:** — (PLAN.md canonical id `F`). All lanes that list F depend on this merge.
- **May touch:** `src/sharpit/fastapi/adapter.py` and new `fastapi/` responsibility modules; `src/sharpit/engine/tools.py` only for the responsibility split and discovery of `engine/tools04/<id_underscored>.py`; `src/sharpit/pytest_plugin/__init__.py` and new plugin modules; `engine/panels.py`, settings/registries, capture wiring, `engine/sqla.py` only for the inert connection-event slot; `ui/src/` navigation, per-panel flag modules, and placeholders; `tests/` for parity and stubs; `tests/engine/test_import_boundary.py` (foundation gatekeeper rows only); `AGENTS.md` where §10.2 requires; `pyproject.toml`, `uv.lock` (only `psycopg[binary]`); both testsession report schema copies; `tests/fixtures/bootui/2.2.0/`; `docs/reference/PARITY.md`; `scripts/dev/lane_gate.py`, its tests, and handoff template under `.superpowers/sdd/0.4.0/`; `examples/fastapi_sqla/` and `tests/test_example_app.py` for shared panel wiring.
- **Must not touch:** Later lane-owned feature implementation or panel modules; `sonar-baseline.txt`, overhead budget constants, existing behavior assertions except equivalent coverage; dependency lists except `psycopg[binary]` with synchronized lock entry. F may re-key moved-code entries in `tests/complexity_baseline.json` only when the per-finding total does not rise; lane_gate permits downstream edits only when every value decreases or an entry is removed.

## Global constraints

- Preserve public behavior exactly: full-suite result and observed behavior before/after F must match.
- `implemented=False` panels are absent from `/panels`, MCP `tools/list`, CLI, routes, and nav; their routes answer 404.
- Runtime dependencies remain exactly `starlette` and `packaging`; `psycopg[binary]` is the only test extra added in F. Any optional OpenTelemetry example provider is test-only and guarded so it is absent without its test extra.
- No module under `src/` may exceed 1000 lines. Keep engine framework-free and gatekeeper boundaries explicit.
- No new GET/MCP side effects; all new hooks and panel stubs remain inert.

## Review Focus

1. A split changes hook ordering or exception behavior: `test_foundation_suite_equivalence` asserts route registration, tool listing/dispatch, option resolution, report and exit behavior.
2. A parked panel appears through one surface: `test_unimplemented_panel_has_no_surface` checks API, MCP, CLI and nav, and 404s its path.
3. Compatibility re-exports break a direct import or monkeypatch target: add targeted compatibility import tests for adapter, tools and pytest plugin facades.
4. A downstream lane bypasses evidence or alters protected files: refusal tests named in Task 4.
5. Report schema copies drift: extend `tests/test_report_schema.py::test_schema_copies_identical` to the paired copies.

---

### Task 1: Split oversized owners without behavior change

**Files:** Modify `src/sharpit/fastapi/adapter.py` (currently 787 lines), `src/sharpit/engine/tools.py` (800), `src/sharpit/pytest_plugin/__init__.py` (737); create responsibility modules under the same packages; add targeted tests under `tests/fastapi/`, `tests/engine/`, and `tests/pytest_plugin/`.

**Interfaces:** Preserve existing exported names and imports. Extract definitions with their current signatures; compatibility facades re-export names relied on by callers/tests. Record moved ownership in module docstrings. Keep hook order and routes unchanged.

- [ ] **Step 1: Add characterization tests and split-module stubs.** Add `test_foundation_suite_equivalence` coverage for route registration, tool listing/dispatch, pytest option resolution and session report/exit behavior. For each new module export, add an importable minimal stub with a deliberately wrong return value, then a test asserting the required value; the stub does not raise `NotImplementedError`.
- [ ] **Step 2: Commit the red.** Commit the failing assertions and importable stubs as `test: pin foundation split contracts`; record this red SHA per test in `findings.md` and `handoff.md`.
- [ ] **Step 3: Replay each named assertion at its recorded red SHA** with `--junitxml` in the integration worktree's environment; require a `<failure>` message beginning with `AssertionError`, reject `<error>`/collection errors/passes, and confirm the same test passes at lane HEAD.
- [ ] **Step 4: Split by responsibility.** Extract cohesive adapter install/routes, tool registration/dispatch, and pytest options/gate/report/summary units; keep compatibility imports.
- [ ] **Step 5: Verify parity.** Run the same four gates at the new head and compare test collected/pass/fail/skip counts and targeted assertions to the recorded base. Any delta blocks F.
- [ ] **Step 6: Commit** `refactor: split foundation modules without behavior change`.

### Task 2: Add inert panel registration and shared extension points

**Files:** Modify `src/sharpit/engine/panels.py`, `src/sharpit/settings.py`, advisor/capture/discovery registries, `src/sharpit/engine/sqla.py`, post-split adapter/plugin/tools modules, `ui/src/`; corresponding `tests/`; `tests/engine/test_import_boundary.py`; `AGENTS.md` only for §10.2 gatekeeper rows.

**Interfaces:** `Panel` gains `implemented: bool = True`. `install(models=...)` stores `tuple(models)` in `SharpitContext.models: tuple[object, ...]` without inspecting its elements. Add inert SQLAlchemy connection-event slot `add_connection_listener(event: Literal["begin", "commit", "rollback", "savepoint", "rollback_savepoint", "release_savepoint"], fn: Callable[..., None]) -> Callable[[], None]`, capture middleware 401/403 callback `Callable[[Scope, int], None]`, and span-processor wiring slot. Add inert `DismissalStore.dismissed_pairs(self) -> set[tuple[str, str]]` returning `set()` for D1 to implement. Add pytest options `--sharpit-report-only`, `--sharpit-baseline`, `--sharpit-write-baseline` (accepted, inert). Every §6.2 0.4 id gets its own Python and UI `implemented=False` flag module plus inert route/settings/advisor/capture/discovery registration; per-panel route modules are included only when implemented. UI flag modules live at `src/lib/panels04/<id_underscored>.ts`; no lane edits shared `nav.ts` lines.

**Foundation choices required by downstream lanes:** Create `ui/src/views/<Panel>.svelte` placeholders for every 0.4 panel, wire each through `ui/src/App.svelte`, `ui/src/lib/nav.ts`, and `ui/src/lib/types.ts`, and gate each on its per-panel `implemented` module. Later lanes replace only their own view and flip only their two flag files. In `tests/engine/test_import_boundary.py`, permit pytest/`_pytest` in every module below `sharpit/pytest_plugin/` and add `"opentelemetry": {"sharpit/engine/otel.py"}`. Add only `psycopg[binary]` to the test extra. `test_unimplemented_panel_has_no_surface` is the canonical absent-surface test. F may re-key moved-code entries in `tests/complexity_baseline.json` only with a per-finding total that does not rise; lane_gate permits downstream edits only when every value decreases or an entry is removed.

- [ ] **Step 1: Failing tests and stubs.** Add `test_unimplemented_panel_has_no_surface`, `test_panel_implemented_default_true`, `test_models_hook_stores_models_without_side_effects`, connection-slot and capture-hook tests, and option tests. Put importable wrong-value stubs in place first; no `NotImplementedError`.
- [ ] **Step 2: Commit the red.** Commit these assertion failures and stubs as `test: pin inert panel and extension contracts`; record each red test name and SHA in `findings.md` and `handoff.md`.
- [ ] **Step 3: Replay each named assertion at its recorded red SHA** with `--junitxml` in the integration worktree's environment; require a `<failure>` message beginning with `AssertionError`, reject `<error>`/collection errors/passes, and confirm the same test passes at lane HEAD.
- [ ] **Step 4: Implement inert registrations and extension slots.** New paths remain dormant until an owning lane sets its panel `implemented=True`.
- [ ] **Step 5: Wire `examples/fastapi_sqla` once for committed and best-effort panels.** Use `install(models=Base)`, provide the optional OpenTelemetry provider only behind its test extra, and add any example route a panel's live check requires; update `tests/test_example_app.py` accordingly.
- [ ] **Step 6: Run targeted tests and four gates.** Every unimplemented id remains absent from every surface.
- [ ] **Step 7: Commit** `feat: add inert 0.4 panel and extension stubs`.

### Task 3: Add BootUI golden infrastructure and synchronized schemas

**Files:** Create `tests/fixtures/bootui/2.2.0/ids.json`, golden loader helper under `tests/`, `.superpowers/sdd/0.4.0/handoff-template.md`; modify `src/sharpit/engine/testsession/report.schema.json` and `docs/reference/report.schema.json`; tests under `tests/`.

**Interfaces:** `ids.json` maps BootUI ids to sharpit ids per §6.2. `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` reads `<sharpit-id>/captured.json` (or `<name>.captured.json` for a multi-endpoint panel), else `<sharpit-id>/provisional.json` marked unverified, plus adjacent `nullable.json`. G0a's worker writes captured fixtures; on coordinator request a different worker writes provisional fixtures. Panel lanes own only nullable fixtures. Schema files stay byte-identical.

- [ ] **Step 1: Failing tests and importable stubs.** `test_golden_id_mapping_covers_panel_ids`, `test_golden_loader_reads_nullable_reasons`, `test_provisional_fixture_is_not_counted_as_parity`; use wrong-value stubs, never `NotImplementedError`. `tests/test_report_schema.py::test_schema_copies_identical` already exists and is a green control, not a red.
- [ ] **Step 2: Commit the red** as `test: pin BootUI golden loader contract`; record each red test name and SHA in `findings.md` and `handoff.md`.
- [ ] **Step 3: Replay named assertions at their recorded red SHA** with `--junitxml` in the integration worktree's environment; require a `<failure>` message beginning with `AssertionError`, reject `<error>`/collection errors/passes, and confirm the same tests pass at lane HEAD.
- [ ] **Step 4: Implement mapping, loader, template and paired schema update.**
- [ ] **Step 5: Run fixture/schema tests; expect id mapping and nullability to load, provisional fixture marked unverified, copies byte-equal.**
- [ ] **Step 6: Commit** `test: add BootUI 2.2 golden and handoff infrastructure`.

### Task 4: Implement the downstream mechanical lane gate

**Files:** Create `scripts/dev/lane_gate.py`, `tests/scripts/test_lane_gate.py`, `.superpowers/sdd/0.4.0/lanes/README.md` (evidence layout).

**Interfaces:** CLI `lane_gate.py <lane-id> [--worktree PATH] [--sha SHA] [--integration PATH] [--accept-unverified]`; defaults resolve lane worktree as `C:\development\github\sharpit-wt\0.4.0-<lane-id>`, SHA as its HEAD, integration as cwd. `main(argv: Sequence[str] | None = None) -> int`. Validate reviewer verdict and matching head SHA; all findings fixed with red-test name or parked with reason; field map; current handoff; §6.1 checklist/evidence paths; forbidden-diff paths. **Re-run the four gates itself** at the lane head (`uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest -q -n auto`, each with a timeout); coordinator writes all six gate logs, pinned to the SHA, in integration at `.superpowers/sdd/0.4.0/lanes/<lane-id>/gate/<name>.log`. For A-postgresql require `gate/leased-pg.log` in the integration worktree with the lane head SHA on line 1 and `test_read_only_wrapper_rejects_write` plus `test_autocommit_engine_is_unavailable` marked `PASSED`; missing or skipped results refuse unless `--accept-unverified` is passed, which writes `unverified` to the ledger line. Lane diffs may not touch any `review.md` or `gate/` path. `--no-rerun` exists for refusal tests only and is refused when the lane id is not a test fixture. Coordinator executes the integration copy (§10.3).

- [ ] **Step 1: Failing refusal tests and importable stubs.** With a minimal valid fixture, assert exact refusal and nonzero exit for `test_lane_gate_refuses_missing_verdict`, `test_lane_gate_refuses_wrong_reviewer_or_sha`, `test_lane_gate_refuses_unresolved_finding`, `test_lane_gate_refuses_missing_field_map_handoff_or_checklist`, `test_lane_gate_refuses_protected_diff`, `test_lane_gate_refuses_gate_log_for_other_sha`, `test_lane_gate_refuses_when_rerun_gate_fails` (a fixture lane whose ruff check fails), `test_lane_gate_no_rerun_refused_for_real_lane`, `test_lane_gate_refuses_complexity_baseline_increase`, `test_lane_gate_refuses_fake_red`, `test_lane_gate_refuses_missing_red_test`, and `test_lane_gate_refuses_error_as_red`; controls include `test_lane_gate_accepts_complete_evidence` and `test_lane_gate_allows_only_decreasing_complexity_baseline`. Stubs return incorrect values and do not raise `NotImplementedError`.
- [ ] **Step 2: Commit the red** as `test: pin lane gate refusal contracts`; record each red test name and SHA in `findings.md` and `handoff.md`.
- [ ] **Step 3: Replay named assertions at their recorded red SHA** with `--junitxml` in the integration worktree's environment; require a `<failure>` message beginning with `AssertionError`, reject `<error>`/collection errors/passes, and confirm the same tests pass at lane HEAD.
- [ ] **Step 4: Implement deterministic evidence and diff checks.** Refuse gate script, sonar baseline, pre-existing import-boundary rules, overhead constants, `uv.lock` and dependency-list changes downstream; allow downstream complexity-baseline edits only when every value decreases or an entry is removed. Allow only F-authored import-boundary rows in F’s own diff.
- [ ] **Step 5: Run gate tests; expect every refusal and valid control to pass.**
- [ ] **Step 6: Commit** `feat: add mechanical 0.4 lane merge gate`.

### Task 5: Apply the F time box and write handoff

- [ ] **Step 1:** At T0 + 2 h, if F is not merged, cut to minimum required by committed lanes: splits, `implemented`, lane gate. Record every cut in handoff (§10.6).
- [ ] **Step 2:** Write `.superpowers/sdd/0.4.0/lanes/F/handoff.md` with base/head SHA, parity evidence, touched files, next step and open findings.
- [ ] **Step 3: Commit** `docs: record foundation lane handoff`.

### Foundation file map and guardrails

| Concern | Owner after split | Compatibility requirement |
|---|---|---|
| FastAPI install/route wiring | `sharpit/fastapi/adapter.py` facade; install/capture setup in `sharpit/fastapi/install.py`; `sharpit/fastapi/routes/<id>.py` per panel | `sharpit.install(models: Iterable[object] | None = None, ...) -> SharpitHandle`; preserve current parameters and imports |
| MCP/CLI tool definitions | Keep `sharpit/engine/tools.py` compatibility facade and per-panel discovery under `sharpit/engine/tools04/<id_underscored>.py`, every module created by F with `TOOLS = ()` | tool names, schemas, ordering and dispatch results stay stable; empty `TOOLS = ()` is the discovery contract |
| pytest options and session flow | `sharpit/pytest_plugin/options.py`, `apps.py`, `session.py`, `terminal.py`, `report_io.py`; `__init__.py` remains compatibility facade | preserve hook registration and current defaults; later lanes use the owning module listed here |
| Future panel exposure | `engine/panels.py` plus each surface’s existing registry | false means absent everywhere, including direct route paths |

#### Foundation consumer interface table (all lanes use this table for module names)

| Module / symbol | Signature or contract consumed by later lanes |
|---|---|
| `sharpit.fastapi.routes.<id>` (each panel id, including `sql_trace`) | Per-panel route module, included only when `Panel.implemented` is true; a lane replaces only its own view and route module. |
| `sharpit.pytest_plugin.options` | `PluginOptions` dataclass and existing `resolve(config: Any) -> PluginOptions`; G1G2 and G6 add options here. |
| `sharpit.pytest_plugin.apps` | G6 owns `autodetect_apps() -> tuple[tuple[str, object], ...]` and `select_app(explicit: str | None, candidates: Sequence[tuple[str, object]]) -> tuple[str, object] | None`. |
| `sharpit.pytest_plugin.session` | Session lifecycle/hooks; G1G2 owns baseline/report gate integration. |
| `sharpit.pytest_plugin.terminal` | G6 owns quiet advisor-note behavior and the notes count line. |
| `sharpit.pytest_plugin.report_io` | Report/JUnit writing; G1G2 preserves output while changing report-only exit semantics. |
| `sharpit.engine.tools` discovery | Read per-panel modules at `sharpit/engine/tools04/<id_underscored>.py`, each exporting `TOOLS = ()` until its lane fills it (F creates one per §6.2 0.4 id); no panel lane edits `engine/tools.py` after F; D1 → D2 → D3 → D4 edit it serially (R0). |
| `sharpit.engine.capture.CaptureState.transactions` | `transactions: object | None = None`; A-transactions supplies its implementation without engine-to-adapter imports. |
| `sharpit.fastapi.capture.CaptureWiring.on_security_event` | Inert `Callable[[Scope, int], None] | None` callback slot, invoked for 401/403 exchanges from the `finally` of `CaptureMiddleware.__call__` **before** `REQUEST.reset(token)` (so `REQUEST.get()` still names the request); test `test_security_event_hook_sees_request_id`; B-security-logs attaches its bounded audit recorder here. |
| `sharpit.fastapi.capture.CaptureWiring.span_processor` | Inert `object | None` slot for one lazily re-armed SDK processor; A-traces consumes it. |
| `sharpit.install` / `SharpitContext.models` | Existing `install(app: Any, *, settings: object = (), engines: Sequence[object] = (), health_checks: Mapping[str, Callable[[], object]] | None = None, models: Iterable[object] | None = None, **options: Any) -> SharpitHandle`; store `tuple(models)` (or `()` when omitted) as `SharpitContext.models: tuple[object, ...]`; F does not inspect elements or configure mappers; A-data consumes it. |
| `tests.golden.assert_parity` | `assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None`; reads captured or provisional fixture plus `nullable.json` as described in Task 3. |
| `scripts/dev/lane_gate.py` | `lane_gate.py <lane-id> [--worktree PATH] [--sha SHA] [--integration PATH]`; evidence follows C2; reviewer-owned artifacts cannot be changed by lane diffs. |
| `sharpit.engine.advisors.findings.Finding.to_dto` | Existing `to_dto(self) -> dict[str, Any]`; G1G2 adds `observed` and `baselineState`, retaining current DTO keys. |
| `sharpit.engine.testsession.facts._finding_from` | Existing `_finding_from(dto: dict[str, Any]) -> Finding`; G1G2 preserves `observed` and `baselineState` when restoring worker facts. |
| `sharpit.engine.testsession.gates.evaluate_test` | Existing `evaluate_test(facts: TestFacts, budget: Budget, n_plus_one_threshold: int, dismissed: Collection[str]) -> list[Finding]`; G1G2 adds baseline input compatibly. |
| `sharpit.engine.testsession.report.render` | Existing `render(merged: MergedFacts, status: str, reasons: list[str], *, gates: dict[str, Any], version: str, now_ms: int, advisors_enabled: bool) -> dict[str, Any]`; G1G2 adds baseline report keys. |
| `sharpit.engine.testsession.outcome.session_status` / `testsession.finish.finish` | `session_status(merged, *, allow_unknown, max_unattributed, advisors_enabled, fail_on) -> SessionStatus`, where `SessionStatus` is `NamedTuple(status, fail_reasons, unknown_reasons)`; `finish(parts, missing, *, options, version, now_ms, warnings) -> tuple[dict[str, Any], str, list[str]]`. G1G2 computes unknown reasons even when status is fail. |
| `sharpit.engine.testsession.outcome._advisor_summary`, `_worst`, `_unknown_reasons` | Existing helpers; G6 adds `SKIPPED` semantics and no-app behavior. |
| `sharpit.engine.testsession.outcome._failing_tests`, `_fail_reasons` | Existing `_failing_tests(merged: MergedFacts) -> int`, `_fail_reasons(merged, summaries, fail_on) -> list[str]`; G1G2 excludes findings with `baselineState == "existing"`. |
| `sharpit.engine.advisors.report.apply_dismissals` | `apply_dismissals(report: Mapping[str, Any], dismissed: Collection[str], occurrences: Mapping[str, Sequence[tuple[str, str, str]]] | None = None, dismissed_pairs: Collection[tuple[str, str]] = ()) -> dict[str, Any]`; occurrence tuples are `(fingerprint, message, identity_or_target)`; G1G2 matches `(rule_id, identity_or_target)` against pairs. |
| `sharpit.engine.collectors.restapi.service._evaluate`, `_run`, `_scan`, `assess` | Existing `_evaluate(model: ApiModel, masker: Masker) -> _Evaluation`, module-level `_run(done: _Evaluation, dismissed: Collection[str], fail_on: Severity, app: str | None, dismissed_pairs: Collection[tuple[str, str]] = ()) -> AdvisorRun`, `RestApiService._scan(self) -> _Scan` records occurrences `(fingerprint, message, identity_or_target)`, and `assess(model, masker, *, fail_on=..., app=None, dismissed=(), dismissed_pairs=()) -> AdvisorRun`; G1G2 matches pairs. |
| `sharpit.engine.capture.exchanges.HttpExchangeBuffer.report` | Existing five parameters `(q, method, status_class, offset, limit)`; D2 appends `route: str | None = None` as sixth. |
| `sharpit.engine.headers.security_headers`, `sharpit.engine.panels.read_only_reason`, `sharpit.engine.guard` | Existing `security_headers(kind: Literal["api", "shell", "asset"]) -> list[tuple[str, str]]`, called as `security_headers("api")`; `read_only_reason(panel_id: str, global_read_only: bool) -> str` returns `sharpit is read-only via SHARPIT_READ_ONLY=true` globally or `Panel is read-only via SHARPIT_PANELS_<ID>_READ_ONLY=true`; guard panel-denial body is exactly `sharpit panel access denied`. |
| `sharpit.fastapi.adapter._read_capped`, nested `send_with_headers` | Existing `_read_capped(request: Request, cap: int) -> bytes | None`; nested `send_with_headers(message: Message) -> None` already skips CSP when response already has it. |
| `sharpit.engine.sqla.sqlalchemy_module`, `sharpit.engine.collectors.pools.pools_report` | Existing `sqlalchemy_module() -> Any | None`; `pools_report(ctx: SharpitContext) -> dict[str, Any]`. |
| `sharpit.engine.sqla.add_connection_listener` | `add_connection_listener(event: Literal["begin", "commit", "rollback", "savepoint", "rollback_savepoint", "release_savepoint"], fn: Callable[..., None]) -> Callable[[], None]`; returns a remover; A-transactions registers here and never edits `sqla.py`. |
| `SharpitSettings.security_logs_max_logs` (`settings.py`) | `int = 500`; `_int`; `SHARPIT_SECURITY_LOGS_MAX_LOGS`; B-security-logs. |
| `SharpitSettings.postgresql_max_sessions` (`settings.py`) | `int = 100`; `_postgresql_limit` (1..2147483646); `SHARPIT_POSTGRESQL_MAX_SESSIONS`; A-postgresql. |
| `SharpitSettings.postgresql_max_statements` (`settings.py`) | `int = 100`; `_postgresql_limit` (1..2147483646); `SHARPIT_POSTGRESQL_MAX_STATEMENTS`; A-postgresql. |
| `SharpitSettings.postgresql_max_indexes` (`settings.py`) | `int = 500`; `_postgresql_limit` (1..2147483646); `SHARPIT_POSTGRESQL_MAX_INDEXES`; A-postgresql. |
| `SharpitSettings.postgresql_max_tables` (`settings.py`) | `int = 200`; `_postgresql_limit` (1..2147483646); `SHARPIT_POSTGRESQL_MAX_TABLES`; A-postgresql. |
| `SharpitSettings.postgresql_max_vacuum_tables` (`settings.py`) | `int = 200`; `_postgresql_limit` (1..2147483646); `SHARPIT_POSTGRESQL_MAX_VACUUM_TABLES`; A-postgresql. |
| `SharpitSettings.postgresql_max_replicas` (`settings.py`) | `int = 10`; `_postgresql_limit` (1..2147483646); `SHARPIT_POSTGRESQL_MAX_REPLICAS`; A-postgresql. |
| `SharpitSettings.postgresql_max_settings` (`settings.py`) | `int = 40`; `_postgresql_limit` (1..2147483646); `SHARPIT_POSTGRESQL_MAX_SETTINGS`; A-postgresql. |
| `SharpitSettings.transactions_enabled` (`settings.py`) | `bool = True`; `_bool`; `SHARPIT_TRANSACTIONS_ENABLED`; A-transactions. |
| `SharpitSettings.transactions_recording` (`settings.py`) | `bool = True`; `_bool`; `SHARPIT_TRANSACTIONS_RECORDING`; A-transactions. |
| `SharpitSettings.transactions_max_entries` (`settings.py`) | `int = 200`; `_int`; `SHARPIT_TRANSACTIONS_MAX_ENTRIES`; A-transactions. |
| `SharpitSettings.transactions_slow_transaction_threshold_millis` (`settings.py`) | `int = 200`; `_int`; `SHARPIT_TRANSACTIONS_SLOW_TRANSACTION_THRESHOLD_MILLIS`; A-transactions. |
| `SharpitSettings.transactions_connection_hold_threshold_millis` (`settings.py`) | `int = 500`; `_int`; `SHARPIT_TRANSACTIONS_CONNECTION_HOLD_THRESHOLD_MILLIS`; A-transactions. |
| `SharpitSettings.activity_unbounded_read_factor` (`settings.py`) | `int = 2`; `_min_two_int`; `SHARPIT_ACTIVITY_UNBOUNDED_READ_FACTOR`; T-unbounded-read. |
| `sharpit.engine.capture.CaptureState.security_logs` | `security_logs: Any | None = None`. |
| 401/403 capture hook | `Callable[[Scope, int], None]`; consumer reads method/path from `scope["method"]` and `scope["path"]`. |
| `sharpit.fastapi.install._configure_capture` | Post-split construction point `def _configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring`; it constructs `SqlTraceRecorder` and assigns `ctx.capture.sql_trace`; A-transactions and A-traces attach at this site. |
| `sharpit.pytest_plugin.apps` | `_load_app` and `_run_advisors` live here; autodetection API name is `autodetect_apps()`. |
| implemented flag files | F creates `src/sharpit/engine/panels04/<id_underscored>.py` (`IMPLEMENTED = False`) and `ui/src/lib/panels04/<id_underscored>.ts` (`implemented = false`); each panel lane flips only its own two files. |

- [ ] **Step 1:** Verify all newly created panel routes are mounted only through their per-panel route module and the `implemented` check; no shared route list is owned by a later lane.
- [ ] **Step 2:** Verify panel configuration defaults are inert: disabled panels neither activate nor create collectors/listeners, and a request to their path is a 404.
- [ ] **Step 3:** Verify `sharpit.install(models: Iterable[object] | None = None, ...)` stores `tuple(models)` on `SharpitContext.models` without inspecting elements or configuring mappers during install.
- [ ] **Step 4:** Verify `--sharpit-report-only`, `--sharpit-baseline`, and `--sharpit-write-baseline` are accepted by pytest but do not change reports or exit behavior before G1G2 merges.

### Lane-gate refusal contract

Each refusal test builds a temporary git/lane fixture and asserts both nonzero exit and a stable refusal reason. The positive control uses the same fixture with all required evidence and an allowed diff.

- [ ] **Step 1:** `test_lane_gate_refuses_missing_verdict` and `test_lane_gate_refuses_wrong_reviewer_or_sha` cover absent approval, same reviewer id, wrong head SHA, and missing SHA.
- [ ] **Step 2:** `test_lane_gate_refuses_unresolved_finding` covers findings without disposition, fixed without a red-test name, and parked without a reason.
- [ ] **Step 3:** `test_lane_gate_refuses_missing_field_map_handoff_or_checklist` covers each missing required artifact and each missing §6.1 evidence path.
- [ ] **Step 4:** `test_lane_gate_refuses_protected_diff` covers the protected file list one path at a time; `test_lane_gate_refuses_gate_log_for_other_sha` covers stale logs.
- [ ] **Step 5:** `test_lane_gate_accepts_complete_evidence` proves a well-formed lane with matching head-SHA logs is accepted.

### Council round 2 additions

**Red replay in `lane_gate.py` (R2):** each task's failing test plus minimal importable stub is committed first as a
`test:` commit; stubs return the wrong value and never raise `NotImplementedError`. `findings.md` and `handoff.md`
record that red SHA per test. For every named red, the gate runs that exact test at the recorded SHA with `--junitxml`
in the integration worktree's environment, requires a `<failure>` beginning with `AssertionError`, then requires the
same test to pass at lane HEAD. An `<error>`, collection error or pass refuses the merge. A review-finding red is
replayed on the parent of its fix commit. The merge-base overlay is removed. Task 4 refusal tests include
`test_lane_gate_refuses_fake_red`, `test_lane_gate_refuses_missing_red_test`, and `test_lane_gate_refuses_error_as_red`.

**Minimum cut at T0 + 2 h (spec §10.6), exactly:** Task 1 (the three splits), the O4 per-panel flag files with
`test_unimplemented_panel_has_no_surface`, Task 4 (`lane_gate.py` with its tests, R2 red replay included), Task 3's golden
loader, UI placeholders/wiring, `install(models=...)`, every pre-created settings field, the three inert pytest options,
`psycopg[binary]`, the import-boundary changes, `DismissalStore.dismissed_pairs()` stub, and Task 2's explicit example
wiring step. **Deferred to lane `F-rest`** (best effort, any worker, files of its own):
the `tests/safety/` and `tests/masking/` packages and test extras other than `psycopg[binary]` (F itself creates every
`engine/tools04/<id_underscored>.py`). `engine/tools.py` discovers each future `engine/tools04/<id_underscored>.py` module with
`TOOLS = ()` until its lane supplies real tools; no lane edits `engine/tools.py`. A lane
that needs a deferred piece before F-rest merges creates its own file for it, never a shared one. Record the cut in
F's `handoff.md`.

**Capture teardown (council round 3, R17):** `CaptureState.teardowns: list[Callable[[], None]]`, empty by default;
`uninstall_capture()` runs every entry once (in reverse order, each in its own `try`, a failure logged and the rest still
run) and clears the list. Lanes that attach listeners or processors (A-transactions' connection-listener removers,
A-traces' processor disarm) append their remover here at attach time; nothing else tears them down.
Test: `test_uninstall_runs_teardowns_in_reverse_even_if_one_fails`.

**Red integrity (council round 4):** for each recorded red SHA, `lane_gate.py` also requires that the red SHA is an
ancestor of the lane head and that the red test's function body is byte-identical between the red SHA and the head
(only implementation files may change after the red commit); the reviewer confirms each red assertion names the
recorded finding. Refusal test: `test_lane_gate_refuses_red_test_changed_after_red_commit`.

## Lane evidence checklist

At completion `.superpowers/sdd/0.4.0/lanes/F/` holds implementer-owned `handoff.md`, `findings.md`, `field-map.md` (`N/A — not a panel lane`) and `checklist.md`. The checklist follows spec §6.1's ten items in order, mapped to their owning task, with evidence paths or `N/A` plus reason. Coordinator/reviewer creates `review.md`, `gate/<name>.log` for ruff-check, ruff-format, pyright, pytest, lowest-direct and no-sqlalchemy, and `live-verify.md` in the integration worktree; the F diff never touches those paths.

## Definition of done

- [ ] Tasks 1–5 complete; suite behavior/counts identical before and after F.
- [ ] Every future panel remains absent until its owner flips `implemented=True`.
- [ ] Lane gate refuses each malformed/protected case and accepts complete evidence.
- [ ] Handoff is current and downstream lanes can consume the infrastructure.

## Canonical lane conventions (C1–C8)

- Lane id is `F`; evidence path is `.superpowers/sdd/0.4.0/lanes/F/`.
- Implementer writes `handoff.md`, `findings.md`, `field-map.md` (`N/A — not a panel lane`), and `checklist.md`. Coordinator/reviewer alone writes `review.md`, `gate/<name>.log` for ruff-check, ruff-format, pyright, pytest, lowest-direct, no-sqlalchemy, and `live-verify.md`, in the integration worktree. The lane diff cannot touch reviewer-owned paths.
- Goldens use `<sharpit-id>/captured.json` (or `<name>.captured.json`), else `provisional.json` marked unverified, plus adjacent `nullable.json`; loader is `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None`.
- Reds are defect-naming assertions, never import/collection failures. Spike tests assert desired behavior and are red on 0.3.0.
- F-rest owns the deferred `tests/safety/` and `tests/masking/` packages; F does not create them. No lane edits the shared `tests/test_safety_matrix.py` or `tests/test_masking_corpus.py` directly.
- Use PLAN.md review-focus names verbatim. This lane's canonical test is `test_unimplemented_panel_has_no_surface`.
- Dependencies are exactly PLAN.md's `—`; no P1–P3 or “Wave G” identifiers.
- F's `checklist.md` follows spec §6.1 items 1–10 in order, mapped to F's owning task; non-panel items use `N/A` with a reason.

| Spec §6.1 item | F task / evidence owner |
|---|---|
| 1 Golden parity | Task 3: loader, id map, schema synchronization; no panel parity claim. |
| 2 Ported behavior tests | N/A — foundation parity tests are not BootUI panel behavior ports. |
| 3 Safety and masking | Task 2: inert panel registration and shared test hooks. |
| 4 Gatekeeper | Task 2: import-boundary rules and engine gatekeeper row. |
| 5 Hot-path overhead | N/A — F creates inert slots and adds no active hot-path behavior. |
| 6 MCP read-only surface | Task 2: inert MCP stubs and implemented filtering. |
| 7 Svelte view | Task 2: `implemented`-gated placeholders and nav wiring. |
| 8 Four gates | Task 4: lane_gate acceptance/refusal checks; coordinator owns gate logs. |
| 9 Live check | N/A — no panel implementation in F; integration reviewer owns live verification. |
| 10 Handoff | Task 5: current F handoff. |
