# Lane F handoff

Status: the F minimum cut is complete except `scripts/dev/lane_gate.py`, which another agent is writing in a separate
worktree (with its tests and `.superpowers/sdd/0.4.0/handoff-template.md`); F's diff does not touch those three paths.
F-rest (`tests/safety/`, `tests/masking/`, test extras other than `psycopg[binary]`) is deferred, as R3 allows.

## How to resume

- Worktree `C:\development\github\sharpit-wt\0.4.0-F`, branch `lane/0.4.0-F`, base `7e5fc150946ee4d870433d96a41a6627b343364a`.
- On this machine `uv` fails to hardlink from its cache (os error 1142): prefix every `uv` command with
  `UV_LINK_MODE=copy`.
- Put pytest logs outside the worktree (`..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\`): `no_side_effects` scans
  the cwd. Freshly edited sources write new `.pyc` files during a parallel run, which can trip that scan once in an
  unrelated test (seen once on `test_vulns_api.py::test_get_report_not_scanned_without_network`; green on rerun).
- Next step: the coordinator merges `lane_gate.py` from its own worktree, then runs it on F.

## Done (commits)

- Task 1 splits and O4 flag files (Codex, up to `0cc440a`): see the red table below.
- The half-applied Codex patch to `tests/fastapi/test_unimplemented_panel_surface.py` (a `dict` subclass whose
  `values()` returned `(False,)` when empty so a red-body assertion could never fail) was **discarded** with
  `git checkout --`: it faked the assertion instead of fixing anything.
- (a) Golden loader + `ids.json`: red `746299e`, fix `eff6819`.
- (b) UI placeholders + App wiring: red `f4b55d6`, fix `c5b2740`.
- (c) `psycopg[binary]` + `uv.lock`: `f7202c4` (dependency only; adds psycopg 3.3.6, psycopg-binary 3.3.6, tzdata).
- (c) Settings, `install(models=)`, pytest options, `dismissed_pairs`, connection slot, 401/403 hook, capture slots,
  teardowns: red `55a6eac`, fix `31f5d9d`.
- (c) `examples/fastapi_sqla` wiring (O3): red `99c1cf8`, fix `ba095ef`.
- Review findings fixed (the full suite at `ba095ef` had 14 failures, both causes from Codex's Task 1/O4 commits,
  missed because no full suite ran after the base): the split dropped the `plugin.Counter` / `plugin.assess`
  monkeypatch seams (red = parent `ba095ef`, fix `65c5026`); `tests/test_safety_matrix.py::test_disabled_panel_denies_its_endpoints`
  parametrized over every `PANELS` row, so the 12 unimplemented 0.4 panels (404 by design) failed; scoped to implemented
  panels in `337d690` (their 404 stays covered by `test_unimplemented_panel_has_no_surface`; an owner's flag flip puts
  its panel back in the matrix automatically).
- Already done by Codex and verified, not redone: F1e import-boundary rows (`32b39ac`), `engine/tools04/<id>.py`
  discovery through `panels04.tool_definitions()` (`e23e936`).

## Decisions and deviations

- `install(models=Base)` (O3) passes a lone class, which `tuple(models)` cannot take. `install` stores
  `(models,)` for a class or any non-iterable, `tuple(models)` for other iterables, `()` for `None`; elements are never
  touched (`test_models_hook_stores_models_without_side_effects` records attribute access on the elements).
- Teardowns run inside `CaptureWiring.detach` (lifespan shutdown and `SharpitHandle.uninstall_capture()` both call it),
  newest first, popped so each runs once, a failure logged through `hook_failed("teardown", ...)`.
- The 401/403 hook failure is caught and logged (`hook_failed("security event", ...)`); the response is unchanged
  (`test_security_event_hook_failure_never_changes_the_response`).
- `add_connection_listener` listens class-level on `Engine` (like the existing statement listeners). shortcut: while
  SQLAlchemy is not imported it returns a no-op remover, so the caller re-attaches later, as `sqla.add` does. An event
  outside the six names raises `ValueError("unknown connection event '<name>'")`.
- Bool fail-safes for `transactions_enabled`/`transactions_recording` are `False` (as `sql_trace_*`); invalid ints fall
  back to the default with the usual warning.
- `session_status` is unchanged in F (F's plan does not change it): it still returns a 2-tuple. G1G2 introduces
  `SessionStatus` (council R6/r2). F-foundation.md's row is corrected to say so.
- The built UI under `src/sharpit/ui/static/` is not rebuilt (lanes never run `npm run build`): the UI build-drift CI
  job will differ until the coordinator rebuilds at integration (already true since the O4 nav change).
- Gate note for the lane_gate author: pytest's junit `<failure message>` drops the `AssertionError: ` prefix when the
  assertion text has no `'` (pytest strips it for rewritten asserts), e.g. `assert 0 == 2`. Several F reds (old and new)
  look like that. The gate should accept `message` starting with `AssertionError` **or** `assert `, or read the
  failure text.

## Verification (at `337d690`)

- Full suite: `uv run pytest -q -n 4` -> **3567 passed, 5 skipped, 0 failed** (base `7e5fc15`: 3491 passed, 5 skipped).
  The +76 are tests F added (Codex Task 1/O4 plus this session: golden 6, extension slots 19, example 2, settings
  env-name rows 14); skips unchanged. Log: `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\F-full-pytest2.log`.
- `uv run ruff check`: all checks passed; `uv run ruff format --check`: 407 files already formatted; `uv run pyright`:
  0 errors, 0 warnings.
- UI: `npm --prefix ui run check` clean; vitest 31 files, 258 tests passed (no `npm run build`).

## Consumer interface table (F1a, R4-R6)

Every row is checked against the code at the lane head; adapt calls to it, never the assertion.

| Module / symbol | Contract for later lanes |
|---|---|
| `sharpit.install` / `sharpit.fastapi.install.install` (models) | `install(app: Any, *, settings: object = (), engines: Sequence[object] = (), health_checks: Mapping[str, Callable[[], object]] \| None = None, models: Iterable[object] \| type \| None = None, **options: Any) -> SharpitHandle` (`src/sharpit/fastapi/install.py`); `fastapi.adapter.install` re-exports it. |
| `sharpit.engine.context.SharpitContext.models` | `models: tuple[object, ...] = ()` (`src/sharpit/engine/context.py`); `install` stores `tuple(models)`, or `(models,)` for a lone class such as `models=Base`; elements never inspected, mappers never configured. Consumer: A-data. |
| R5: `SqlTraceRecorder` construction | `sharpit.fastapi.install._configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring` (`src/sharpit/fastapi/install.py`) builds every recorder, assigns `ctx.capture.sql_trace = SqlTraceRecorder(...)` when `sql-trace` is enabled and `sql_trace_enabled`, then creates and attaches `CaptureWiring`. A-transactions and A-traces attach at this site. (D2's plan text `_configure_capture(ctx, settings) -> None` is stale.) |
| `sharpit.engine.capture.CaptureState.security_logs` | `security_logs: Any \| None = None` (`src/sharpit/engine/capture/__init__.py`). Consumer: B-security-logs. |
| `sharpit.engine.capture.CaptureState.transactions` | `transactions: object \| None = None`. Consumer: A-transactions. |
| `sharpit.engine.capture.CaptureState.teardowns` (R17) | `teardowns: list[Callable[[], None]]`, empty by default. `CaptureWiring.detach(ctx)` (run by lifespan shutdown and `SharpitHandle.uninstall_capture()`) pops and runs them newest first, each in its own `try`, a failure logged via `hook_failed("teardown", exc)`; the list ends empty. Consumers: A-transactions (listener removers), A-traces (processor disarm). |
| `sharpit.fastapi.capture.CaptureWiring.on_security_event` (R12) | `on_security_event: Callable[[Scope, int], None] \| None = None` (instance attribute, `src/sharpit/fastapi/capture.py`). Called from the `finally` of `CaptureMiddleware.__call__` **before** `REQUEST.reset(token)` when the sent status is 401 or 403, so `REQUEST.get()` names the request; read method/path from `scope["method"]`/`scope["path"]`; an exception is logged via `hook_failed("security event", exc)` and never changes the response. Only fires while the capture middleware is installed (any capture panel enabled and implemented). Consumer: B-security-logs. |
| `sharpit.fastapi.capture.CaptureWiring.span_processor` | `span_processor: object \| None = None` (instance attribute). Consumer: A-traces. |
| `sharpit.engine.sqla.add_connection_listener` (O1) | `add_connection_listener(event: ConnectionEvent, fn: Callable[..., None]) -> Callable[[], None]` (`src/sharpit/engine/sqla.py`); `ConnectionEvent = Literal["begin", "commit", "rollback", "savepoint", "rollback_savepoint", "release_savepoint"]`, `CONNECTION_EVENTS` the same tuple. Listens class-level on `sqlalchemy.engine.Engine`; returns an idempotent remover; a no-op remover while SQLAlchemy is not imported (retry later); unknown event → `ValueError("unknown connection event '<event>'")`. Consumer: A-transactions (never edits `sqla.py`). |
| `sharpit.engine.advisors.dismissals.DismissalStore.dismissed_pairs` (R1) | `dismissed_pairs(self) -> set[tuple[str, str]]` returns `set()`; D1 implements the body, G1G2 consumes it. |
| pytest options (inert) | `--sharpit-report-only` (`store_true`), `--sharpit-baseline PATH`, `--sharpit-write-baseline` (`store_true`), all `default=None`, registered in `sharpit.pytest_plugin.options.pytest_addoption`; `resolve()` / `PluginOptions` do not read them yet. G1G2 adds them to `PluginOptions`/`resolve`. |
| `sharpit.engine.testsession.outcome.session_status` (R6) | Real today: `session_status(merged: MergedFacts, *, allow_unknown: bool, max_unattributed: float, advisors_enabled: bool, fail_on: str) -> tuple[Status, list[str]]`; callers `testsession/finish.py:42` (`status, reasons = outcome.session_status(...)`), `tests/engine/testsession/test_outcome.py`, `tests/engine/testsession/tsfakes.py`. F does not change it; G1G2 changes it to return `SessionStatus(status, fail_reasons, unknown_reasons)` (NamedTuple) and updates those callers. |
| `sharpit.engine.testsession.finish.finish` | `finish(parts: Sequence[SessionFacts], missing: Sequence[str], *, options: GateOptions, version: str, now_ms: int, warnings: Sequence[str]) -> tuple[dict[str, Any], str, list[str]]`. |
| `tests.golden.assert_parity` (R9) | `assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` (`tests/golden.py`, import as `from golden import assert_parity`). Fixture order under `tests/fixtures/bootui/2.2.0/<sharpit_id>/`: `<name>.captured.json`, `captured.json`, `<name>.provisional.json`, `provisional.json` (provisional emits `golden.UnverifiedParityWarning`: merges, counted unverified); none → `AssertionError`. Every golden key must exist with the same JSON kind (int/float are one "number"); extra payload keys pass; golden `null` accepts anything; payload `null` for a non-null golden passes only if `nullable.json` (`{"<path>": "<non-empty reason>"}`, list items as `items[].key`) lists it. `golden.ROOT` is the fixture root (tests monkeypatch it). `golden.bootui_ids() -> dict[str, str]`. |
| `tests/fixtures/bootui/2.2.0/ids.json` | BootUI id → sharpit id for every sharpit panel (31 entries; `flyway`→`alembic`, `hibernate-statistics`→`sqlalchemy-statistics`, `spring-security`→`fastapi-security`, `spring`→`fastapi`, others identical). |
| UI placeholders (F1b) | `ui/src/views/{Data,Transactions,PostgreSql,MySql,Traces,Security,SecurityLogs,DatabaseAdvisor,Architecture,SqlalchemyStatistics,FastapiSecurity,Fastapi}.svelte`, props `{ panel: Panel }`; routed in `ui/src/App.svelte` as `current.id === '<id>' && panelImplemented('<id>')`. `ui/src/lib/types.ts` exports `Panel04Id = keyof typeof PANEL_04_IMPLEMENTED`. A lane replaces only its view file and flips its two flag files; `ui/tests/component/panels04.test.ts` keeps the wiring. |
| `examples/fastapi_sqla` (O3) | `examples.fastapi_sqla.app.Base` (`DeclarativeBase`) with `Owner` (`owners`) and `Pet` (`pets`), passed as `install(models=Base)`; `app.state.otel_provider` is an SDK `TracerProvider` (set as the global provider) only when `opentelemetry-sdk` is importable, else `None`; `otel_provider() -> object \| None`. No lane edits the example (O3). |
| `sharpit.fastapi.routes.build_routes` / adapter `_routes` | `build_routes(ctx: SharpitContext, host_app: Any) -> list[BaseRoute]`; adapter `_routes(ctx, host_app)` dynamically delegates to it, and install calls the adapter seam. It assembles ordered route groups from the `fastapi.routes` package behind the existing guard middleware. |
| Adapter helper seams used by routes | `_read_capped(request, cap)`, `_json_or_none(raw)`, `_page(request)`, `_toggle_value(raw)`, `available_reasons(ctx)`, and `log_events(...)` remain on the adapter facade; route handlers delegate through those attributes at call time so monkeypatches remain effective. |
| `sharpit.fastapi.route_registry.register_routes` | `register_routes(app: Any, routes: Iterable[Any]) -> None`; appends routes in input order. |
| `sharpit.fastapi.install._configure_capture` | `_configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring`; constructs the recorder slots and returns the attached wiring. |
| `sharpit.engine.tools` | Existing tool catalogue, types, MCP/CLI names and dispatch imports remain available as compatibility facade. |
| `sharpit.engine.tool_dispatch` | `ToolGate`, `tool_gate`, `call_tool`, `tool_info`, `cli_status`, and `cli_invoke` own dispatch and CLI behavior; dynamic facade lookup preserves `tools.TOOLS` and `tools.tool_gate` monkeypatches. |
| `sharpit.engine.tool_registry.catalogue` | `catalogue() -> Sequence[Tool]` returns the registered tools in contract order. |
| `sharpit.pytest_plugin.options.resolve` | Existing `resolve(config: Any) -> PluginOptions` remains the canonical option parser. |
| `sharpit.pytest_plugin.options.pytest_addoption` | Owns the existing CLI/ini option registration; plugin facade re-exports the hook. |
| `sharpit.pytest_plugin.session.resolve_options` | Compatibility seam delegating to `options.resolve`; `pytest_sessionfinish(session, exitstatus)` owns session finalization. |
| `sharpit.pytest_plugin.session.pytest_runtest_makereport` | Owns the existing finding and gate hook; plugin facade re-exports it. |
| `sharpit.pytest_plugin.apps` | `_load_app(spec: str) -> tuple[str, object]`, `_model_of(app: object) -> ApiModel`, `_run_advisors(state, *, load_app=None)`; plugin facade passes its re-exported loader so monkeypatches stay effective. |
| `sharpit.pytest_plugin.report_io.write_report` | `write_report(state, session, exitstatus) -> None` owns report serialization and exit status; plugin keeps `_write_report` compatibility alias. |
| `sharpit.pytest_plugin.terminal.pytest_terminal_summary` | Existing pytest terminal summary hook moved intact; dynamically resolves plugin helper seams. |
| `sharpit.pytest_plugin.__init__` | Existing pytest hook names remain importable for plugin registration. |
| `sharpit.engine.panels.Panel.implemented` | `bool = True`; existing panels default true, while each 0.4 panel row reads its own `panels04/<id_underscored>.py::IMPLEMENTED`. False rows are omitted from `panels_report` and `panel_for_api_path`. |
| `sharpit.engine.panels04.IMPLEMENTED` / `PANEL_04_IDS` | `IMPLEMENTED: dict[str, bool]` maps sharpit ids to their local flags; `PANEL_04_IDS: tuple[str, ...]` lists the 12 ids. |
| `sharpit.engine.panels04.tool_definitions` | `tool_definitions() -> tuple[tuple[Any, ...], dict[str, str]]`; gathers `TOOLS` and `COMMANDS` only from implemented panel modules. |
| `sharpit.engine.tools04.<id>.TOOLS` / `COMMANDS` | Each per-panel module exports `TOOLS = ()` and `COMMANDS = {}` for its owning lane to fill. |
| `sharpit.fastapi.routes.<id>.build_routes` | `build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]`; empty per-panel route modules are called only when the corresponding `Panel.implemented` is true. |
| `sharpit.engine.advisors.registry.AdvisorSpec.implemented` | `bool = True`; the four pre-registered advisors (`database-advisor`, `security`, `architecture`, `fastapi`) read their `panels04` flags; `advisor_for()` ignores false specs. Rule ownership/fingerprints remain empty until the owner lane fills them. |
| `sharpit.fastapi.capture.CAPTURE_PANELS` | Contains `transactions` and `security-logs` in addition to legacy capture panels; middleware attaches only when both the settings flag and `Panel.implemented` are true. |
| `sharpit.engine.sqla.DISCOVERY_PANELS` | Contains `postgresql`, `mysql`, `database-advisor`, and `sqlalchemy-statistics`; engine discovery attaches only when both the settings flag and `Panel.implemented` are true. |
| UI `lib/panels04` registry | Each `ui/src/lib/panels04/<id_underscored>.ts` exports `implemented = false`; `PANEL_04_IMPLEMENTED` and `panelImplemented(id: string) -> boolean` keep false ids out of `groupPanels`. |

## Pre-created settings fields (R4; all in `src/sharpit/settings.py`, `SharpitSettings`)

Every field below reads env `SHARPIT_<FIELD UPPER>` (env beats the `install()` kwarg); an invalid value takes the
fail-safe and adds an `Ignoring invalid ...` warning. Parsers are module functions in `settings.py`.

| Field | Type | Default | Parser (fail-safe) | Env var | Consuming lane |
|---|---|---|---|---|---|
| `security_logs_max_logs` | `int` | `500` | `_int` (>0; default) | `SHARPIT_SECURITY_LOGS_MAX_LOGS` | B-security-logs (clamps 1..10000 itself) |
| `postgresql_max_sessions` | `int` | `100` | `_postgresql_limit` (1..2147483646; default) | `SHARPIT_POSTGRESQL_MAX_SESSIONS` | A-postgresql |
| `postgresql_max_statements` | `int` | `100` | `_postgresql_limit` | `SHARPIT_POSTGRESQL_MAX_STATEMENTS` | A-postgresql |
| `postgresql_max_indexes` | `int` | `500` | `_postgresql_limit` | `SHARPIT_POSTGRESQL_MAX_INDEXES` | A-postgresql |
| `postgresql_max_tables` | `int` | `200` | `_postgresql_limit` | `SHARPIT_POSTGRESQL_MAX_TABLES` | A-postgresql |
| `postgresql_max_vacuum_tables` | `int` | `200` | `_postgresql_limit` | `SHARPIT_POSTGRESQL_MAX_VACUUM_TABLES` | A-postgresql |
| `postgresql_max_replicas` | `int` | `10` | `_postgresql_limit` | `SHARPIT_POSTGRESQL_MAX_REPLICAS` | A-postgresql |
| `postgresql_max_settings` | `int` | `40` | `_postgresql_limit` | `SHARPIT_POSTGRESQL_MAX_SETTINGS` | A-postgresql |
| `transactions_enabled` | `bool` | `True` | `_bool` (`False`) | `SHARPIT_TRANSACTIONS_ENABLED` | A-transactions |
| `transactions_recording` | `bool` | `True` | `_bool` (`False`) | `SHARPIT_TRANSACTIONS_RECORDING` | A-transactions |
| `transactions_max_entries` | `int` | `200` | `_int` (default) | `SHARPIT_TRANSACTIONS_MAX_ENTRIES` | A-transactions |
| `transactions_slow_transaction_threshold_millis` | `int` | `200` | `_int` (default) | `SHARPIT_TRANSACTIONS_SLOW_TRANSACTION_THRESHOLD_MILLIS` | A-transactions |
| `transactions_connection_hold_threshold_millis` | `int` | `500` | `_int` (default) | `SHARPIT_TRANSACTIONS_CONNECTION_HOLD_THRESHOLD_MILLIS` | A-transactions |
| `activity_unbounded_read_factor` | `int` | `2` | `_min_two_int` (below 2 → 2; invalid → default) | `SHARPIT_ACTIVITY_UNBOUNDED_READ_FACTOR` | T-unbounded-read |

Existing fields lanes read but F did not add: `sql_trace_n_plus_one_threshold: int = 5` (`_min_two_int`,
A-sqlalchemy-statistics), `activity_n_plus_one_threshold: int = 5`, `read_only: bool = False`, per-panel
`panels[<id>].enabled/read_only` (`SHARPIT_PANELS_<ID>_ENABLED/_READ_ONLY`, every 0.4 id already present).

## Red-test replay table

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/test_foundation_split_contracts.py::test_route_registration_preserves_order` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert app.routes == [first, second]` |
| `tests/test_foundation_split_contracts.py::test_tool_catalogue_matches_registered_tools` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert [tool.name for tool in catalog] == [tool.name for tool in TOOLS]` |
| `tests/test_foundation_split_contracts.py::test_plugin_session_options_match_resolver` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert actual == expected` |
| `tests/test_foundation_split_compat.py::test_capture_configuration_contract_is_owned_by_install_module` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert get_type_hints(_configure_capture)["return"] is CaptureWiring` |
| `tests/test_foundation_split_compat.py::test_tool_dispatch_import_is_cycle_free` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert result.returncode == 0, result.stderr` |
| `tests/engine/test_tools.py::test_call_tool_uses_facade_catalogue` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert result == {"facade": True}` |
| `tests/engine/test_tools.py::test_call_tool_uses_facade_tool_gate` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert calls == [expected.name]` |
| `tests/pytest_plugin/test_plugin_apps.py::test_plugin_loader_facade_remains_monkeypatchable` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert state.sink.facts.advisor_runs[0].status != "UNKNOWN"` |
| `tests/test_foundation_structure.py::test_install_facade_reexports_install_module_implementation` | `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9` | `assert adapter.install is install_module.install` |
| `tests/test_foundation_structure.py::test_adapter_install_uses_route_builder_module` | `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9` | `assert called == [True]` |
| `tests/test_foundation_structure.py::test_option_registration_is_owned_by_options_module` | `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9` | `assert plugin.pytest_addoption is options.pytest_addoption` |
| `tests/test_foundation_structure.py::test_gate_hook_is_owned_by_session_module` | `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9` | `assert plugin.pytest_runtest_makereport is session.pytest_runtest_makereport` |
| `tests/test_foundation_capture_setup.py::test_configure_capture_attaches_wiring` | `d0ea233ea90a7e2f5cd800a6df7582a6ae114d1e` | `assert isinstance(wiring, CaptureWiring)` |
| `tests/test_foundation_structure.py::test_install_uses_adapter_route_compatibility_target` | `3ff293b0f49a325e25d31e743febfe9cea3c91f2` | `assert calls == [True]` |
| `tests/test_foundation_structure.py::test_installed_routes_use_adapter_read_capped_compatibility_target` | `3ff293b0f49a325e25d31e743febfe9cea3c91f2` | `assert response.status_code == 413` |
| `tests/test_foundation_capture_setup.py::test_configure_capture_stores_wiring_on_context` | `82b9177fc659abc6691712d9e706b8186e34329c` | `assert ctx.capture.wiring is not None` |
| `tests/test_foundation_capture_setup.py::test_configure_capture_stores_returned_wiring` | `3075c9104fd1cc4939baefc2e7071e370fe6e635` | `assert ctx.capture.wiring is wiring` |
| `tests/test_foundation_structure.py::test_http_probe_route_name_is_preserved` | `46bebf286295760495f24117f44d95765c4b8b02` | `assert str(path) == "/sharpit/api/http-probe"` |
| `tests/engine/test_import_boundary.py::test_pytest_gatekeeper_allows_every_plugin_submodule` | `359fbe92310fb07b5fdb9553786086ca3303a7a3` | `assert violations == ["sharpit/engine/rogue.py imports pytest: only ['sharpit/pytest_plugin'] may import pytest"]` |
| `tests/test_foundation_runtime_types.py::test_install_return_type_resolves_at_runtime` | `359fbe92310fb07b5fdb9553786086ca3303a7a3` | `assert hints.get("return") is SharpitHandle` |
| `tests/test_foundation_runtime_types.py::test_tool_call_types_resolve_at_runtime` | `359fbe92310fb07b5fdb9553786086ca3303a7a3` | `assert hints.get("call") is CallContext` |
| `tests/test_foundation_runtime_types.py::test_tool_gate_context_and_via_types_resolve_at_runtime` | `359fbe92310fb07b5fdb9553786086ca3303a7a3` | `assert hints.get("ctx") is SharpitContext` |
| `tests/engine/test_import_boundary.py::test_opentelemetry_stays_behind_engine_otel_gatekeeper` | `7df27495026acd28f9ba0e8e60e7028113b8cf70` | `assert violations == [...]` (`sharpit/engine/tools.py imports opentelemetry.trace`) |
| `tests/engine/advisors/test_registry.py::test_0_4_advisor_specs_are_registered_and_gated` | `acbccbb` | `assert all(by_id[advisor_id].implemented is IMPLEMENTED[advisor_id] for advisor_id in advisor_ids)` |
| `tests/fastapi/test_capture_hooks.py::test_unimplemented_security_logs_does_not_add_capture_middleware` | `acbccbb` | `assert wiring.middleware_added is False` |
| `tests/fastapi/test_capture_hooks.py::test_unimplemented_database_panels_do_not_enable_discovery` | `acbccbb` | `assert calls[0] == (False, False)` |
| `tests/fastapi/test_unimplemented_panel_surface.py::test_panel_implemented_defaults_true` | `c11ed916979054a6b994c9733964021e4ac5354f` | `assert panel.implemented is True` |
| `tests/fastapi/test_unimplemented_panel_surface.py::test_unimplemented_panel_has_no_surface` | `c11ed916979054a6b994c9733964021e4ac5354f` | `assert set(IMPLEMENTED.values()) == {False}` |
| `tests/engine/test_panel04_registry.py::test_0_4_panels_are_registered_but_unimplemented` | `fbcd986` | `assert set(panels) == PANEL_IDS` |
| `Vitest: ui/tests/unit/nav.test.ts::keeps every 0.4 panel unimplemented and out of navigation` | `c11ed916979054a6b994c9733964021e4ac5354f` | `expect(Object.values(PANEL_04_IMPLEMENTED)).toEqual(PANEL_04_IDS.map(() => false))` |
| `tests/test_golden.py::test_golden_id_mapping_covers_panel_ids` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert set(ids.values()) == {panel.id for panel in PANELS}` |
| `tests/test_golden.py::test_golden_loader_reads_nullable_reasons` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert no_reason is not None` |
| `tests/test_golden.py::test_provisional_fixture_is_not_counted_as_parity` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert [w.category for w in provisional] == [UnverifiedParityWarning]` |
| `tests/test_golden.py::test_golden_loader_rejects_missing_key_and_wrong_type` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert missing is not None` |
| `tests/test_golden.py::test_golden_loader_prefers_named_capture` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert named is not None` |
| `tests/test_golden.py::test_golden_loader_requires_a_fixture` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert absent is not None` |
| `Vitest: ui/tests/component/panels04.test.ts::renders the <id> placeholder with its panel title` (12 ids) | `f4b55d64cbb63494a7d35c59e96660c208a5244b` | `expect(h.target.textContent).toContain('<View> title')` (empty stub view) |
| `Vitest: ui/tests/component/panels04.test.ts::routes every 0.4 placeholder in App.svelte only behind its implemented flag` | `f4b55d64cbb63494a7d35c59e96660c208a5244b` | `expect(app, view).toContain("import Data from './views/Data.svelte';")` |
| `tests/test_foundation_extension_slots.py::test_0_4_settings_defaults` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert {name: getattr(s, name, None) for name in SETTINGS_0_4} == SETTINGS_0_4` |
| `tests/test_foundation_extension_slots.py::test_0_4_settings_env_parsers` (7 params) | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(s, field, None) == expected` |
| `tests/test_foundation_extension_slots.py::test_models_hook_stores_models_without_side_effects` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert len(models) == 2` |
| `tests/test_foundation_extension_slots.py::test_models_hook_accepts_a_lone_declarative_base` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(handle.context, "models", None) == (Base,)` |
| `tests/test_foundation_extension_slots.py::test_dismissed_pairs_is_inert_empty_set` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert store.dismissed_pairs() == set()` |
| `tests/test_foundation_extension_slots.py::test_capture_slots_default_inert` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(state, "security_logs", "missing") is None` |
| `tests/test_foundation_extension_slots.py::test_security_event_hook_sees_request_id` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert seen == [("GET", "/s401", 401, True), ("GET", "/s403", 403, True)]` |
| `tests/test_foundation_extension_slots.py::test_uninstall_runs_teardowns_in_reverse_even_if_one_fails` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert ran == ["third", "second", "first"]` |
| `tests/test_foundation_extension_slots.py::test_connection_listener_slot_attaches_and_removes` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert calls == ["begin"]` |
| `tests/test_foundation_extension_slots.py::test_connection_listener_slot_rejects_unknown_event` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert message == "unknown connection event 'execute'"` |
| `tests/test_foundation_extension_slots.py::test_report_only_options_are_accepted_and_inert` (2 params) | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert with_options.ret == plain.ret` (usage error 4 before the options exist) |
| `tests/test_example_app.py::test_sqla_sample_passes_its_models_to_install` | `99c1cf8fa8f28b67a2f806b554c314b88aa23315` | `assert app.state.sharpit.context.models == (Base,)` |
| `tests/test_example_app.py::test_sqla_sample_otel_provider_only_with_the_sdk` | `99c1cf8fa8f28b67a2f806b554c314b88aa23315` | `assert (provider is not None) == bool(has_sdk)` |
| `tests/pytest_plugin/test_plugin_gates.py::test_plugin_hook_raises_session_continues[terminal_summary-False-False]` (review finding: split broke the `plugin.Counter` seam) | `ba095efd548889bea12df614b3e2935ddda3eff9` (parent of fix `65c50263c029481a489885a7562b47bc9bb8e8e9`) | `assert 'pass' == 'unknown'` |
| `tests/pytest_plugin/test_plugin_gates.py::test_plugin_hook_raises_session_continues[worker_advisors-True-True]` (review finding: split broke the `plugin.assess` seam) | `ba095efd548889bea12df614b3e2935ddda3eff9` (parent of fix `65c50263c029481a489885a7562b47bc9bb8e8e9`) | `assert 'pass' == 'unknown'` |

Capture red SHAs `d0ea233`, `82b9177`, and `3075c91` are mutation-based contract checks (wrong-value stubs),
not pre-existing defects. The `3ff293b` and `ba095ef` rows are review-found compatibility regressions.
