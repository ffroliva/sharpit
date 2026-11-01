# Lane F handoff

Status: Task 1 implementation complete; fresh review pending before Task 2.

- Base: `7e5fc150946ee4d870433d96a41a6627b343364a` (`release/0.4.0`); worktree branch `lane/0.4.0-F`.
- Untouched-base suite at `7e5fc15`: 3491 passed, 5 skipped, 34 warnings in 93.95 s (`uv run pytest -q -n 4`).
- Task 1 red commits: `869db29d181a3ad98df7eb5ba6201b4cbc0e091f`, `45797333bd99647623073cb8b7b0b6755bd6a3f7`, `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9`, and `d0ea233ea90a7e2f5cd800a6df7582a6ae114d1e`; node IDs/assertions are in `findings.md`.
- Completed responsibility extraction commit: `45a3e98b53119be0c7427a42122bf8f99a385760`.
- Current focused regression run: 193 passed, 16 warnings in 45.02 s. It covers new structure/capture/compatibility/equivalence tests plus existing tool, pytest, xdist, capture-wiring, install, and code-shape suites.
- Pyright: 0 errors, 0 warnings. Ruff check and format check passed for changed Python files. C901 ratchet test passed after lowering the `engine/tools.py` and `fastapi/adapter.py` entries from 1/3 to 0/0; the new route and dispatch modules add no C901 findings.
- The first focused rerun logged inside the repo and tripped the no-side-effects fixture's cwd scan; the clean rerun
  placed logs outside the worktree.
- Current state: ready for the fresh Task 1 review; Task 2 has not started.

## Consumer interface table

| Module / symbol | Contract for later lanes |
|---|---|
| `sharpit.fastapi.adapter.install` / `sharpit.fastapi.install.install` / `sharpit.install` | `install(app: Any, *, settings: object = (), engines: Sequence[object] = (), health_checks: Mapping[str, Callable[[], object]] | None = None, **options: Any) -> SharpitHandle`; adapter remains a compatibility facade. |
| `sharpit.fastapi.routes.build_routes` / adapter `_routes` | `build_routes(ctx: SharpitContext, host_app: Any) -> list[BaseRoute]`; adapter `_routes` re-exports it. It assembles route groups from the `fastapi.routes` package, and install mounts them behind the existing guard middleware. |
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
