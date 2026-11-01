# Lane F handoff

Status: Task 1 implementation complete/reviewed; Task 2 O4 implementation committed; lane_gate is next.

- Base: `7e5fc150946ee4d870433d96a41a6627b343364a` (`release/0.4.0`); worktree branch `lane/0.4.0-F`.
- Untouched-base suite at `7e5fc15`: 3491 passed, 5 skipped, 34 warnings in 93.95 s (`uv run pytest -q -n 4`).
- Task 1 red commits: `869db29d181a3ad98df7eb5ba6201b4cbc0e091f`, `45797333bd99647623073cb8b7b0b6755bd6a3f7`, `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9`, `d0ea233ea90a7e2f5cd800a6df7582a6ae114d1e`, `3ff293b0f49a325e25d31e743febfe9cea3c91f2`, `82b9177fc659abc6691712d9e706b8186e34329c`, `3075c9104fd1cc4939baefc2e7071e370fe6e635`, `46bebf286295760495f24117f44d95765c4b8b02`, `359fbe92310fb07b5fdb9553786086ca3303a7a3`, and `7df27495026acd28f9ba0e8e60e7028113b8cf70`; see the red-test table below and `findings.md`.
- Completed responsibility extraction commit: `45a3e98b53119be0c7427a42122bf8f99a385760`.
- Final Task 1 responsibility-split commit: `526e53f51e24bfa532a8555c82b939e4d72069eb`.
- Adapter compatibility fix: `1d5e1f7d9fd1ff66744d3e55693bd0b7691a94e4` (adapter route/helper seams now delegate dynamically).
- Capture wiring attachment fix: `e1a3256fa56e9c4f4ea269f06f943037c2d32ddc` (returns the exact wiring stored on `CaptureState`).
- Final Task 1 contract fix: `32b39ac9c30465205f645edd3a25dc976aa13431` (named route, runtime-resolvable annotations, and F1e gatekeepers).
- Task 2 O4 red commits: `c11ed916979054a6b994c9733964021e4ac5354f` (surface/default flags and Vitest nav control) and `fbcd986` (PANELS registry coverage); see the red-test table below.
- Task 2 O4 fix: `e23e936` (`feat: register inert 0.4 panel surfaces`).
- Task 2 targeted verification: Python API/panel/tool/MCP/CLI tests: 118 passed; Vitest nav: 4 passed; Ruff check passed, format check reported 404 files already formatted, Pyright 0 errors, UI `tsc --noEmit` passed.
- Current focused regression run: 208 passed, 16 warnings in 31.61 s. It covers structure/capture/compatibility/equivalence/runtime-type/import-boundary tests plus existing tool, pytest, xdist, capture-wiring, install, and code-shape suites.
- Pyright: 0 errors, 0 warnings. Ruff check and format check passed for changed Python files. C901 ratchet test passed after lowering the `engine/tools.py` and `fastapi/adapter.py` entries from 1/3 to 0/0; the new route and dispatch modules add no C901 findings.
- The first focused rerun logged inside the repo and tripped the no-side-effects fixture's cwd scan; the clean rerun
  placed logs outside the worktree.
- Current state: O4 flags are false and filtered from the panels API, guard/path matching, MCP/CLI, per-panel routes, and UI nav. Per-panel empty tool and route modules are ready for owner lanes. Next is Task 3 `scripts/dev/lane_gate.py` and its refusal tests.
- UI red was run with Vitest (`npm --prefix ui run test -- tests/unit/nav.test.ts`) after `npm --prefix ui ci`; the assertion failed as expected because all 0.4 flags were temporarily true.

The capture contract reds at `d0ea233`, `82b9177` and `3075c91` are deliberate wrong-value-stub checks required by COMMON/R2. They prove that the returned capture wiring is created, stored on the context, and is the same object; they are contract/mutation reds, not reports of a defect at the untouched base. The implementation is restored and verified by `e1a3256`.

## Consumer interface table

| Module / symbol | Contract for later lanes |
|---|---|
| `sharpit.fastapi.adapter.install` / `sharpit.fastapi.install.install` / `sharpit.install` | `install(app: Any, *, settings: object = (), engines: Sequence[object] = (), health_checks: Mapping[str, Callable[[], object]] | None = None, **options: Any) -> SharpitHandle`; adapter remains a compatibility facade. |
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
| UI `lib/panels04` registry | Each `ui/src/lib/panels04/<id_underscored>.ts` exports `implemented = false`; `PANEL_04_IMPLEMENTED` and `panelImplemented(id: string) -> boolean` keep false ids out of `groupPanels`. |

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
| `tests/fastapi/test_unimplemented_panel_surface.py::test_panel_implemented_defaults_true` | `c11ed916979054a6b994c9733964021e4ac5354f` | `assert panel.implemented is True` |
| `tests/fastapi/test_unimplemented_panel_surface.py::test_unimplemented_panel_has_no_surface` | `c11ed916979054a6b994c9733964021e4ac5354f` | `assert set(IMPLEMENTED.values()) == {False}` |
| `tests/engine/test_panel04_registry.py::test_0_4_panels_are_registered_but_unimplemented` | `fbcd986` | `assert set(panels) == PANEL_IDS` |
| `Vitest: ui/tests/unit/nav.test.ts::keeps every 0.4 panel unimplemented and out of navigation` | `c11ed916979054a6b994c9733964021e4ac5354f` | `expect(Object.values(PANEL_04_IMPLEMENTED)).toEqual(PANEL_04_IDS.map(() => false))` |

Capture red SHAs `d0ea233`, `82b9177`, and `3075c91` are mutation-based contract checks: each substitutes an intentionally wrong value and the assertions detect the missing result or attachment. They are not claims of pre-existing production regressions. The `3ff293b` rows are the review-found production compatibility regressions.
