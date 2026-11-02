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

- Review round 3 (R3-1, R3-2, golden minor): red `95e5769`, fix `a1fb3ad`.
- Review round 2 addendum (items 8-9): red `aaa97d8`, fix `53b0e86`.
- Review round 2 (`ponytail-review.md` + coordinator): red `c2e385d`, fix `4650305`; see §Review round 2 and §Superseded reds below.

- Review round 1 (`review.md`, CHANGES at `d37c6f2`): red `46ee247`, red-body restore `55eac19`, fix `4c3828b`; see `findings.md` §Review round 1. Settings: an unimplemented 0.4 id in `install(panels=...)` now raises the unknown-panel `ValueError` (as at base), and the message lists implemented panels only.

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

## Verification (at `a1fb3ad`, review round 3)

- Full suite: `uv run pytest -q -n 4` -> **3645 passed, 5 skipped, 0 failed** (base `7e5fc15`: 3491 passed, 5
  skipped). Both failures are overhead budgets (`test_capture_overhead.py::test_request_overhead_budget`,
  `test_sql_trace_overhead.py::test_statement_overhead_budget`), reported "within the noise" on a machine running ~65
  Python processes. Both pass in isolation, the middleware's per-request code is unchanged since round 1, and no
  `src/` file changed between `4650305` and `53b0e86`. Budgets not raised.
  The +149 are tests F added (Codex Task 1/O4; golden 6, extension slots 19, example 2, settings env-name rows 14;
  round 1: 7; round 2: +71 new, 9 superseded deleted; addendum: +6); skips unchanged. Log:
  `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\F-full-pytest6.log`.
- `uv run ruff check`: all checks passed; `uv run ruff format --check`: 407 files already formatted; `uv run pyright`:
  0 errors, 0 warnings.
- UI: `npm --prefix ui run check` clean; vitest 31 files, 258 tests passed (no `npm run build`).

## Consumer interface table (F1a, R4-R6)

Every row is checked against the code at the lane head; adapt calls to it, never the assertion.

| Module / symbol | Contract for later lanes |
|---|---|
| `sharpit.install` / `sharpit.fastapi.install.install` (models) | `install(app: Any, *, settings: object = (), engines: Sequence[object] = (), health_checks: Mapping[str, Callable[[], object]] \| None = None, models: Iterable[object] \| type \| None = None, **options: Any) -> SharpitHandle` (`src/sharpit/fastapi/install.py`); `fastapi.adapter.install` re-exports it. |
| `sharpit.engine.context.SharpitContext.models` | `models: tuple[object, ...] = ()` (`src/sharpit/engine/context.py`); `install` stores `tuple(models)`, or `(models,)` for a lone class such as `models=Base`; a `str`, `bytes` or `Mapping` raises `TypeError("models must be a model class or an iterable of models, not <type>")`; elements never inspected, mappers never configured. Consumer: A-data. |
| R5: `SqlTraceRecorder` construction | `sharpit.fastapi.install._configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring` (`src/sharpit/fastapi/install.py`) builds every recorder, assigns `ctx.capture.sql_trace = SqlTraceRecorder(...)` when `sql-trace` is enabled and `sql_trace_enabled`, then creates and attaches `CaptureWiring`. A-transactions and A-traces attach at this site. (D2's plan text `_configure_capture(ctx, settings) -> None` is stale.) |
| `sharpit.engine.capture.CaptureState.security_logs` | `security_logs: Any \| None = None` (`src/sharpit/engine/capture/__init__.py`). Consumer: B-security-logs. |
| `sharpit.engine.capture.CaptureState.transactions` | `transactions: object \| None = None`. Consumer: A-transactions. |
| `sharpit.engine.capture.CaptureState.attachers` / `.teardowns` (R17, round 2) | `attachers: list[Callable[[], Callable[[], None] | None]]` and `teardowns: list[Callable[[], None]]`, both empty by default. The wiring runs every attacher not yet armed at install (`attach_at_install`), at each lifespan startup (`on_startup`) and on the first request: a returned remover arms it and goes to `teardowns`; `None` (e.g. SQLAlchemy not imported) leaves it for the next chance; an exception is logged via `hook_failed("attacher", exc)`. `CaptureWiring.detach` (lifespan shutdown, `SharpitHandle.uninstall_capture()`) pops and runs `teardowns` newest first, each in its own `try`, then disarms every attacher, so the next startup re-arms them. Lanes register an attacher (A-transactions: `lambda: sqla.add_connection_listener(...)`; A-traces: its processor arm/disarm) instead of appending removers directly. |
| `sharpit.fastapi.capture.CaptureWiring.on_security_event` (R12) | `on_security_event: Callable[[Scope, int], None] \| None = None` (instance attribute, `src/sharpit/fastapi/capture.py`). Called from the `finally` of `CaptureMiddleware.__call__` **before** `REQUEST.reset(token)` when the sent status is 401 or 403, so `REQUEST.get()` names the request; read method/path from `scope["method"]`/`scope["path"]`; an exception is logged via `hook_failed("security event", exc)` and never changes the response. Only fires while the capture middleware is installed (any capture panel enabled and implemented). Consumer: B-security-logs. |
| `sharpit.fastapi.capture.CaptureWiring.span_processor` | `span_processor: object \| None = None` (instance attribute). Consumer: A-traces. |
| `sharpit.engine.sqla.add_connection_listener` (O1) | `add_connection_listener(event: ConnectionEvent, fn: Callable[..., None]) -> Callable[[], None] | None` (`src/sharpit/engine/sqla.py`); `ConnectionEvent = Literal["begin", "commit", "rollback", "savepoint", "rollback_savepoint", "release_savepoint"]`, `CONNECTION_EVENTS` the same tuple. Listens class-level on `sqlalchemy.engine.Engine` and returns an idempotent remover, or **`None` while SQLAlchemy is not imported**; unknown event → `ValueError("unknown connection event '<event>'")`. Call it from a `CaptureState.attachers` entry (next row) so it is retried and re-armed. Consumer: A-transactions (never edits `sqla.py`). |
| `sharpit.engine.advisors.dismissals.DismissalStore.dismissed_pairs` (R1) | `dismissed_pairs(self) -> set[tuple[str, str]]` returns `set()`; D1 implements the body, G1G2 consumes it. |
| pytest options (inert) | `--sharpit-report-only` (`store_true`), `--sharpit-baseline PATH`, `--sharpit-write-baseline` (`store_true`), all `default=None`, help `(reserved for 0.4.0; currently has no effect)`, registered in `sharpit.pytest_plugin.options.pytest_addoption`; `resolve()` / `PluginOptions` do not read them. G1G2 adds them to `PluginOptions`/`resolve` and writes the real help. |
| `sharpit.engine.testsession.outcome.session_status` (R6) | Real today: `session_status(merged: MergedFacts, *, allow_unknown: bool, max_unattributed: float, advisors_enabled: bool, fail_on: str) -> tuple[Status, list[str]]`; callers `testsession/finish.py:42` (`status, reasons = outcome.session_status(...)`), `tests/engine/testsession/test_outcome.py`, `tests/engine/testsession/tsfakes.py`. F does not change it; G1G2 changes it to return `SessionStatus(status, fail_reasons, unknown_reasons)` (NamedTuple) and updates those callers. |
| `sharpit.engine.testsession.finish.finish` | `finish(parts: Sequence[SessionFacts], missing: Sequence[str], *, options: GateOptions, version: str, now_ms: int, warnings: Sequence[str]) -> tuple[dict[str, Any], str, list[str]]`. |
| `tests.golden.assert_parity` (R9, round 2) | `assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` (`tests/golden.py`, import as `from golden import assert_parity`). Fixture order under `tests/fixtures/bootui/2.2.0/<sharpit_id>/`: `<name>.captured.json`, `<name>.provisional.json`, `captured.json`, `provisional.json` (provisional emits `golden.UnverifiedParityWarning`: merges, counted unverified); none → `AssertionError`. Every golden key must exist with a compatible JSON kind (int/float are one "number"); extra payload keys pass; a golden list keeps **one item per distinct shape** and a payload item passes if it matches **any** of them; at a path (`items[].key`) payload `null` passes when any golden item is `null` there or `nullable.json` (`{"<path>": "<non-empty reason>"}`) lists it, and any type some golden item has there is accepted; golden `null` accepts anything. `golden.ROOT` is the fixture root (tests monkeypatch it). `golden.bootui_ids() -> dict[str, str]`. |
| `tests/surface.py` (round 2) | Shared expectations for count/list-pinned tests: `BASE_PANEL_IDS` (19), `BASE_MCP_TOOL_NAMES` (18), `BASE_CLI_COMMANDS` (24) pinned literally; `lane_tools()`, `lane_commands()` (from `panels04.tool_definitions()`), `expected_panel_ids()`, `expected_mcp_tool_names()`, `expected_cli_commands()`, `lane_route_paths(ctx, host_app)` add whatever the implemented flags contribute. A lane flipping its flag needs no edit to the shared tests; it adds its own positive tests. |
| `tests/fixtures/bootui/2.2.0/ids.json` | BootUI id → sharpit id for every sharpit panel (31 entries; `flyway`→`alembic`, `hibernate-statistics`→`sqlalchemy-statistics`, `spring-security`→`fastapi-security`, `spring`→`fastapi`, others identical). |
| UI placeholders (F1b) | `ui/src/views/{Data,Transactions,PostgreSql,MySql,Traces,Security,SecurityLogs,DatabaseAdvisor,Architecture,SqlalchemyStatistics,FastapiSecurity,Fastapi}.svelte`, props `{ panel: Panel }`; routed in `ui/src/App.svelte` as `current.id === '<id>' && panelImplemented('<id>')`. `ui/src/lib/types.ts` exports `Panel04Id = keyof typeof PANEL_04_IMPLEMENTED`. A lane replaces only its view file and flips its two flag files; `ui/tests/component/panels04.test.ts` keeps the wiring. |
| `examples/fastapi_sqla` (O3) | `examples.fastapi_sqla.app.Base` (`DeclarativeBase`) with `Owner` (`owners`) and `Pet` (`pets`), passed as `install(models=Base)`; `app.state.otel_provider` is an SDK `TracerProvider` (set as the global provider) only when `opentelemetry-sdk` is importable, else `None`; `otel_provider() -> object \| None`. No lane edits the example (O3). |
| `sharpit.fastapi.routes.build_routes` / adapter `_routes` | `build_routes(ctx: SharpitContext, host_app: Any) -> list[BaseRoute]`; adapter `_routes(ctx, host_app)` dynamically delegates to it, and install calls the adapter seam. It assembles ordered route groups from the `fastapi.routes` package behind the existing guard middleware. |
| Adapter helper seams used by routes | `_read_capped(request, cap)`, `_json_or_none(raw)`, `_page(request)`, `_toggle_value(raw)`, `available_reasons(ctx)`, and `log_events(...)` remain on the adapter facade; route handlers delegate through those attributes at call time so monkeypatches remain effective. |
| `sharpit.fastapi.install._configure_capture` | `_configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring`; constructs the recorder slots and returns the attached wiring. |
| `sharpit.engine.tools` | Existing tool catalogue, types, MCP/CLI names and dispatch imports remain available as compatibility facade. |
| `sharpit.engine.tool_dispatch` | `ToolGate`, `tool_gate`, `call_tool`, `tool_info`, `cli_status`, and `cli_invoke` own dispatch and CLI behavior; dynamic facade lookup preserves `tools.TOOLS` and `tools.tool_gate` monkeypatches. |
| `sharpit.pytest_plugin.options.resolve` | Existing `resolve(config: Any) -> PluginOptions` remains the canonical option parser. |
| `sharpit.pytest_plugin.options.pytest_addoption` | Owns the existing CLI/ini option registration; plugin facade re-exports the hook. |
| `sharpit.pytest_plugin.session.pytest_runtest_makereport` | Owns the existing finding and gate hook; plugin facade re-exports it. |
| `sharpit.pytest_plugin.apps` | `_load_app(spec: str) -> tuple[str, object]`, `_model_of(app: object) -> ApiModel`, `_run_advisors(state, *, load_app=None)`; plugin facade passes its re-exported loader so monkeypatches stay effective. |
| `sharpit.pytest_plugin.report_io.write_report` | `write_report(state, session, exitstatus) -> None` owns report serialization and exit status; plugin keeps `_write_report` compatibility alias. |
| `sharpit.pytest_plugin.terminal.pytest_terminal_summary` | Existing pytest terminal summary hook moved intact; dynamically resolves plugin helper seams. |
| `sharpit.pytest_plugin.__init__` | Existing pytest hook names remain importable for plugin registration. |
| `sharpit.engine.panels.Panel.implemented` | read-only **property** = `panel_is_implemented(self.id)`, evaluated at call time; `sharpit.engine.panels.panel_is_implemented` is `sharpit.engine.panels04.module_implemented` (`IMPLEMENTED.get(panel_id, True)`, the one helper). False rows are omitted from `panels_report`, `panel_for_api_path`, routes, settings kwargs/env (an unimplemented id is an unknown panel) and capture/discovery. Tests flip a flag with `monkeypatch.setitem(sharpit.engine.panels04.IMPLEMENTED, id, value)`. |
| `sharpit.engine.panels04.IMPLEMENTED` / `PANEL_04_IDS` | `IMPLEMENTED: dict[str, bool]` maps sharpit ids to their local flags; `PANEL_04_IDS: tuple[str, ...]` lists the 12 ids. |
| `sharpit.engine.panels04.tool_definitions` | `tool_definitions() -> tuple[tuple[Any, ...], dict[str, str]]`; gathers `TOOLS` and `COMMANDS` only from implemented panel modules. |
| `sharpit.engine.tools04.<id>.TOOLS` / `COMMANDS` | Each per-panel module exports `TOOLS = ()` and `COMMANDS = {}` for its owning lane to fill. |
| `sharpit.engine.tools.merge_lane_tools` | `merge_lane_tools(base_tools, base_commands, lane_tools, lane_commands) -> tuple[tuple[Tool, ...], dict[str, str]]`, called at import to build `TOOLS`/`COMMANDS`; raises `ValueError` when a lane tool name repeats an existing one or a lane `COMMANDS` key (tool name → CLI command path, as `_BASE_COMMANDS`) shadows an existing one. |
| `sharpit.fastapi.routes.<id>.build_routes` | `build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]`; empty per-panel route modules are called only when the corresponding `Panel.implemented` is true. |
| `sharpit.fastapi.routes.sql_trace` / `sharpit.engine.tools04.sql_trace` | Per-panel modules for the existing, implemented `sql-trace` panel (A-sqltrace-insights fills them; never edit the shared loops): `build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]` returning `[]`, and `TOOLS = ()`, `COMMANDS = {}`. Discovery visits `sharpit.engine.panels04.MODULE_PANEL_IDS = (*PANEL_04_IDS, "sql-trace")`, gated by `module_implemented(panel_id) -> bool` (0.4 flag, `True` for `sql-trace`), in both `fastapi/routes/__init__.py::_panel_04_routes` and `panels04.tool_definitions()`; tools are appended after the base catalogue. |
| `sharpit.engine.advisors.registry.AdvisorSpec.implemented` | read-only property = `module_implemented(self.id)`; the four pre-registered advisors (`database-advisor`, `security`, `architecture`, `fastapi`) follow their `panels04` flag; `advisor_for()` ignores false specs. Rule ownership/fingerprints stay empty until the owner lane fills them. |
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
| `tests/test_foundation_split_compat.py::test_capture_configuration_contract_is_owned_by_install_module` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert get_type_hints(_configure_capture)["return"] is CaptureWiring` |
| `tests/test_foundation_split_compat.py::test_tool_dispatch_import_is_cycle_free` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert result.returncode == 0, result.stderr` |
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
| `tests/engine/advisors/test_registry.py::test_0_4_advisor_specs_are_registered_and_gated` | `acbccbbdea8ce6798151a1a61b534c6fdf1a9ffb` | `assert all(by_id[advisor_id].implemented is IMPLEMENTED[advisor_id] for advisor_id in advisor_ids)` |
| `tests/fastapi/test_unimplemented_panel_surface.py::test_panel_implemented_defaults_true` | `c11ed911b56c9460d64ad3253809cf729f6622b7` | `assert panel.implemented is True` |
| `tests/engine/test_panel04_registry.py::test_0_4_panels_are_registered_but_unimplemented` | `fbcd986f5ae7cdaf4b501afe1a5a9cd60cbbd700` | `assert set(panels) == PANEL_IDS` |
| `tests/test_golden.py::test_golden_id_mapping_covers_panel_ids` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert set(ids.values()) == {panel.id for panel in PANELS}` |
| `tests/test_golden.py::test_golden_loader_reads_nullable_reasons` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert no_reason is not None` |
| `tests/test_golden.py::test_provisional_fixture_is_not_counted_as_parity` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert [w.category for w in provisional] == [UnverifiedParityWarning]` |
| `tests/test_golden.py::test_golden_loader_rejects_missing_key_and_wrong_type` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert missing is not None` |
| `tests/test_golden.py::test_golden_loader_prefers_named_capture` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert named is not None` |
| `tests/test_golden.py::test_golden_loader_requires_a_fixture` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert absent is not None` |
| `tests/test_foundation_extension_slots.py::test_0_4_settings_defaults` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert {name: getattr(s, name, None) for name in SETTINGS_0_4} == SETTINGS_0_4` |
| `tests/test_foundation_extension_slots.py::test_0_4_settings_env_parsers` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(s, field, None) == expected` |
| `tests/test_foundation_extension_slots.py::test_models_hook_stores_models_without_side_effects` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert len(models) == 2` |
| `tests/test_foundation_extension_slots.py::test_models_hook_accepts_a_lone_declarative_base` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(handle.context, "models", None) == (Base,)` |
| `tests/test_foundation_extension_slots.py::test_dismissed_pairs_is_inert_empty_set` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert store.dismissed_pairs() == set()` |
| `tests/test_foundation_extension_slots.py::test_capture_slots_default_inert` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(state, "security_logs", "missing") is None` |
| `tests/test_foundation_extension_slots.py::test_security_event_hook_sees_request_id` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert seen == [("GET", "/s401", 401, True), ("GET", "/s403", 403, True)]` |
| `tests/test_foundation_extension_slots.py::test_uninstall_runs_teardowns_in_reverse_even_if_one_fails` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert ran == ["third", "second", "first"]` |
| `tests/test_foundation_extension_slots.py::test_connection_listener_slot_attaches_and_removes` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert calls == ["begin"]` |
| `tests/test_foundation_extension_slots.py::test_connection_listener_slot_rejects_unknown_event` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert message == "unknown connection event 'execute'"` |
| `tests/test_foundation_extension_slots.py::test_report_only_options_are_accepted_and_inert` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert with_options.ret == plain.ret` (usage error 4 before the options exist) |
| `tests/test_example_app.py::test_sqla_sample_passes_its_models_to_install` | `99c1cf8fa8f28b67a2f806b554c314b88aa23315` | `assert app.state.sharpit.context.models == (Base,)` |
| `tests/test_example_app.py::test_sqla_sample_otel_provider_only_with_the_sdk` | `99c1cf8fa8f28b67a2f806b554c314b88aa23315` | `assert (provider is not None) == bool(has_sdk)` |
| `tests/test_foundation_review_fixes.py::test_models_hook_rejects_a_string` | `46ee2477daa57bc7c826c780074dcd7e1ffb09f3` | `assert message == f"models must be a model class or an iterable of models, not {type(models).__name__}"` |
| `tests/test_foundation_round2.py::test_panel_surface_follows_its_flag[flag-true-postgresql]` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert (panel_id in listed) is implemented` |
| `tests/test_foundation_round2.py::test_panel_surface_follows_its_flag[flag-true-transactions]` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert (panel_id in listed) is implemented` |
| `tests/test_foundation_round2.py::test_panel_settings_follow_the_flag[flag-true]` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert error is None` |
| `tests/test_foundation_round2.py::test_panel_env_for_an_unimplemented_panel_is_ignored[flag-false]` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert warned is implemented` |
| `tests/test_foundation_round2.py::test_lane_attacher_survives_lifespan_restart` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert calls == [1, 1]` |
| `tests/test_foundation_round2.py::test_connection_listener_says_when_sqlalchemy_is_not_imported` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert sqla.add_connection_listener("begin", lambda *_: None) is None` |
| `tests/test_foundation_round2.py::test_lane_attacher_retries_after_a_late_sqlalchemy_import` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert calls == [1]` |
| `tests/test_foundation_round2.py::test_reserved_options_help_promises_no_behaviour` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert f"--sharpit-report-only {reserved}" in out` |
| `tests/test_foundation_round2.py::test_golden_loader_prefers_named_provisional_over_shared_capture` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert error is None` |
| `tests/test_foundation_round2.py::test_lane_tool_colliding_with_a_base_tool_is_refused` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert _merge_error((clash,), {}) == f"lane tool name(s) collide with existing tools: {clash.name}"` |
| `tests/test_surface_follows_flags.py::test_every_shared_count_follows_a_flag_flip` | `aaa97d8e2d4af2d5394097c1967a1bfa6ea1ba0b` | `assert panel_ids == surface.expected_panel_ids()` |
| `tests/test_golden_shapes.py::test_payload_item_matches_any_golden_shape` | `aaa97d8e2d4af2d5394097c1967a1bfa6ea1ba0b` | `assert _error({"items": [{"kind": "b", "y": "t"}, {"kind": "a", "x": 2}]}) is None` |
| `tests/test_golden_shapes.py::test_null_allowed_where_any_golden_item_is_null` | `aaa97d8e2d4af2d5394097c1967a1bfa6ea1ba0b` | `assert _error({"items": [{"v": None, "w": 3}]}) is None` |
| `tests/test_golden_shapes.py::test_any_golden_type_at_a_path_is_accepted` | `aaa97d8e2d4af2d5394097c1967a1bfa6ea1ba0b` | `assert _error({"items": [{"v": "t", "w": 3}]}) is None` |
| `tests/test_foundation_round3.py::test_sql_trace_route_module_is_mounted` | `95e5769a1c469cb92e75c34c38425d81011fd728` | `assert client.get("/sharpit/api/sql-trace/insights-probe").text == "probe"` |
| `tests/test_foundation_round3.py::test_golden_list_without_shape_information_warns` | `95e5769a1c469cb92e75c34c38425d81011fd728` | `assert messages == ["data/data: golden list items has no shape information; its items are unchecked"]` |

## Review round 2 (ponytail-review.md + coordinator): finding → test → red SHA → fix

| Finding | Test | Red SHA | Fix |
|---|---|---|---|
| 1 flag-flip-fragile tests | `test_panel_surface_follows_its_flag`, `test_panel_settings_follow_the_flag` (red); `test_panel_tools_follow_its_flag`, `test_capture_middleware_follows_the_panel_flag`, `test_engine_discovery_follows_the_panel_flag` (pass on arrival) | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305`: `Panel.implemented` and `AdvisorSpec.implemented` are properties reading `panels04.IMPLEMENTED` at call time |
| 2 one-shot teardowns / silent no-op listener | `test_lane_attacher_survives_lifespan_restart`, `test_lane_attacher_retries_after_a_late_sqlalchemy_import`, `test_connection_listener_says_when_sqlalchemy_is_not_imported` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305`: `CaptureState.attachers`, re-run at install/startup/first request; `add_connection_listener` returns `None` without SQLAlchemy |
| 3 inert options' help promised behaviour | `test_reserved_options_help_promises_no_behaviour` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305` |
| 4 golden order | `test_golden_loader_prefers_named_provisional_over_shared_capture` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305` |
| 5 lane tool collisions; reversed COMMANDS example | `test_lane_tool_colliding_with_a_base_tool_is_refused` (red); `test_sql_trace_modules_are_discovered` (replacement) | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305`: `tools.merge_lane_tools` raises at import |
| 6 half-applied `max_results` fallback | `tests/engine/test_tools.py::test_call_tool_uses_the_given_tool_gate` (replacement double; no behaviour red) | — | `4650305` |
| 7 env for an unimplemented id warned | `test_panel_env_for_an_unimplemented_panel_is_ignored` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305` |
| lean | deleted `engine/tool_registry.py`, `fastapi/route_registry.py`, `session.resolve_options`, their 3 tests; one `panel_is_implemented` (= `panels04.module_implemented`) | — | `4650305` |

## Review round 2 addendum (coordinator items 8-9): finding → test → red SHA → fix

| Finding | Test | Red SHA | Fix |
|---|---|---|---|
| 8 count-pinned shared tests break on a flag flip | `tests/test_surface_follows_flags.py::test_every_shared_count_follows_a_flag_flip` (flag `data` on, planted tool/command/route; panels, MCP list, MCP `toolCount`, CLI `toolCount`/commands and routes all follow) | `aaa97d8e2d4af2d5394097c1967a1bfa6ea1ba0b` | `53b0e86`: `tests/surface.py` (base pinned literally + flag-derived extras) used by `test_mcp.py::test_tools_list_has_no_action_tool`, `test_tools.py::test_catalogue_names_panels_actions_and_schemas`, `test_install.py::test_panels_platform_fastapi_and_ids` / `::test_mvp_panels_stay_available`, `test_mcp_api.py::test_mcp_server_status_shape`, `test_cli_api.py::test_cli_status_shape_matches_contract`, `test_safety_matrix.py::test_get_route_table_is_complete`, `test_foundation_suite_equivalence.py` |
| 9 golden lists keep one item per distinct shape | `tests/test_golden_shapes.py::test_payload_item_matches_any_golden_shape`, `::test_null_allowed_where_any_golden_item_is_null`, `::test_any_golden_type_at_a_path_is_accepted` (red); `::test_payload_item_matching_no_golden_shape_is_rejected`, `::test_a_type_no_golden_item_has_is_rejected` (controls) | `aaa97d8e2d4af2d5394097c1967a1bfa6ea1ba0b` | `53b0e86` |

## Review round 3: finding → test → red SHA → fix

| Finding | Test | Red SHA | Fix |
|---|---|---|---|
| R3-1 sql-trace route module mounting unproven | `tests/test_foundation_round3.py::test_sql_trace_route_module_is_mounted` (red against a stub loop that skips `sql-trace`) | `95e5769a1c469cb92e75c34c38425d81011fd728` | `a1fb3ad` |
| R3-2 `# noqa: C901` in `tests/golden.py` | none: `_compare` split into `_compare` / `_compare_object` / `_compare_list` with a `_Check` record; ruff C901 passes, `tests/complexity_baseline.json` unchanged | — | `a1fb3ad` |
| minor: empty or null-only golden list accepted anything silently | `tests/test_foundation_round3.py::test_golden_list_without_shape_information_warns` (both cases) | `95e5769a1c469cb92e75c34c38425d81011fd728` | `a1fb3ad`: compares nothing for that list and emits `UnverifiedParityWarning` naming the path |

## Superseded reds (test deleted; its row left the red table)

| Test | Red SHA (historical) | Why |
|---|---|---|
| test_foundation_split_contracts.py::test_route_registration_preserves_order | was 869db29 | deleted with `fastapi/route_registry.py` (lean: the wrapper only re-stated `app.routes.extend`) |
| test_foundation_split_contracts.py::test_tool_catalogue_matches_registered_tools | was 869db29 | deleted with `engine/tool_registry.py` (lean: `catalogue()` returned `tools.TOOLS`) |
| test_foundation_split_contracts.py::test_plugin_session_options_match_resolver | was 869db29 | deleted with the pure alias `session.resolve_options` (the plugin facade re-exports `options.resolve`) |
| engine/test_tools.py::test_call_tool_uses_facade_tool_gate | was 4579733 | replaced by `tests/engine/test_tools.py::test_call_tool_uses_the_given_tool_gate` (the double now has `max_results`, so production reads `gate.max_results` only) |
| fastapi/test_capture_hooks.py::test_unimplemented_security_logs_does_not_add_capture_middleware | was acbccbb | replaced by `tests/test_foundation_round2.py::test_capture_middleware_follows_the_panel_flag` (flag set both ways) |
| fastapi/test_capture_hooks.py::test_unimplemented_database_panels_do_not_enable_discovery | was acbccbb | replaced by `tests/test_foundation_round2.py::test_engine_discovery_follows_the_panel_flag` (flag set both ways) |
| fastapi/test_unimplemented_panel_surface.py::test_unimplemented_panel_has_no_surface | was c11ed91 | replaced by `tests/test_foundation_round2.py::test_panel_surface_follows_its_flag` and `::test_panel_tools_follow_its_flag` (the old body read today's flags and asserted a tautology) |
| test_foundation_review_fixes.py::test_sql_trace_route_and_tool_modules_are_discovered | was 46ee247 | replaced by `tests/test_foundation_round2.py::test_sql_trace_modules_are_discovered` (COMMANDS maps tool name -> CLI path, as `_BASE_COMMANDS`); route mounting is covered by `test_panel_surface_follows_its_flag`'s per-panel route loop |
| test_foundation_review_fixes.py::test_unknown_panel_message_lists_only_implemented_panels | was 46ee247 | replaced by `tests/test_foundation_round2.py::test_panel_settings_follow_the_flag` (flag set both ways, no hard-coded panel list) |


## UI reds (manual replay; not pytest node ids)

Replay: `git checkout <sha> -- ui && npm --prefix ui run test -- <file>` in a scratch copy, then restore.

| Vitest test | Red SHA | Observed red output |
|---|---|---|
| `ui/tests/unit/nav.test.ts::keeps every 0.4 panel unimplemented and out of navigation` | `c11ed911b56c9460d64ad3253809cf729f6622b7` | `expect(Object.values(PANEL_04_IMPLEMENTED)).toEqual(PANEL_04_IDS.map(() => false))` |
| `ui/tests/component/panels04.test.ts::renders the <id> placeholder with its panel title` | `f4b55d64cbb63494a7d35c59e96660c208a5244b` | `expect(h.target.textContent).toContain('<View> title')` (empty stub view) |
| `ui/tests/component/panels04.test.ts::routes every 0.4 placeholder in App.svelte only behind its implemented flag` | `f4b55d64cbb63494a7d35c59e96660c208a5244b` | `expect(app, view).toContain("import Data from './views/Data.svelte';")` |

## Not a red (no replayable red; kept out of the red table)

- `tests/pytest_plugin/test_plugin_gates.py::test_plugin_hook_raises_session_continues[terminal_summary-False-False]` and `[worker_advisors-True-True]`: existing base tests (not lane-added) that caught the Task 1 split dropping the `plugin.Counter` / `plugin.assess` seams; they failed at `ba095ef` and pass since `65c5026`. The gate only accepts lane-added or lane-changed tests as reds, so they are listed here, not in the red table.
- `tests/engine/test_tools.py::test_call_tool_uses_facade_catalogue` (recorded at `45797333bd99647623073cb8b7b0b6755bd6a3f7`): at that SHA it fails with `RpcError`, not an `AssertionError`, so it is a characterisation test of the tools facade seam, not a red. It passes at head and stays as a characterisation test.
- `tests/test_safety_matrix.py::test_disabled_panel_denies_its_endpoints` (scoped in `337d690`): a test-scope correction, not a defect red. The 12 unimplemented 0.4 panels answer 404 by design and are covered by `test_unimplemented_panel_has_no_surface`. In `4c3828b`, three safety-matrix/capture inputs that disable "every panel" now pass only implemented ids, because an unimplemented id is now an unknown panel (review finding 3).
- `tests/fastapi/test_capture_hooks.py::test_unimplemented_security_logs_does_not_add_capture_middleware` and `::test_unimplemented_database_panels_do_not_enable_discovery`: Codex added `skipif` decorators after their red commit `acbccbb`, and the gate requires the red body unchanged. The change only skipped the tests once an owner flips a flag, so `55eac19` restores the red version byte-for-byte (`git checkout acbccbb -- tests/fastapi/test_capture_hooks.py`). An owner lane that flips `security-logs`/`transactions` or a database panel replaces the matching test with its own positive test.
- Review minors 4 and 5: controls that pass on arrival, so no red. `tests/test_foundation_review_fixes.py::test_planted_tool_in_an_unimplemented_panel_stays_absent` and `::test_report_only_options_leave_the_sharpit_report_unchanged` (`4c3828b`).

## Open minors

- Review 6: `src/sharpit/ui/static` is not rebuilt (lanes never run `npm run build`); the CI `ui-drift` job fails until the coordinator rebuilds once at integration.
- Review 7 (for lane_gate): pytest's junit failure message has the `AssertionError: ` prefix only when the assertion text contains a `'` (pytest strips it otherwise, e.g. `c11ed91`'s `assert {True} == {False}`).
