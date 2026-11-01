# Lane F handoff

Status: Task 1 implementation complete; fresh review pending before Task 2.

- Base: `7e5fc150946ee4d870433d96a41a6627b343364a` (`release/0.4.0`); worktree branch `lane/0.4.0-F`.
- Untouched-base suite at `7e5fc15`: 3491 passed, 5 skipped, 34 warnings in 93.95 s (`uv run pytest -q -n 4`).
- Task 1 red commits: `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` and `45797333bd99647623073cb8b7b0b6755bd6a3f7`; all named reds and assertion messages are in `findings.md`.
- Follow-up implementation focused run: 180 passed, 16 warnings in 35.39 s, including new facade/import and end-to-end report/exit coverage plus the existing tool, pytest, xdist, capture-wiring, and install suites.
- Ruff check and format check passed for all changed Python files.
- The first focused rerun logged inside the repo and tripped the no-side-effects fixture's cwd scan; the clean rerun
  placed logs outside the worktree.
- Current state: ready for the fresh Task 1 review; Task 2 has not started.

## Consumer interface table

| Module / symbol | Contract for later lanes |
|---|---|
| `sharpit.fastapi.adapter` / `sharpit.install` | Existing `install(app, *, settings=(), engines=(), health_checks=None, **options) -> SharpitHandle` contract and adapter compatibility imports remain available. |
| `sharpit.fastapi.route_registry.register_routes` | `register_routes(app: Any, routes: Iterable[Any]) -> None`; appends routes in input order. |
| `sharpit.fastapi.install._configure_capture` | `_configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring`; constructs the recorder slots and returns the attached wiring. |
| `sharpit.engine.tools` | Existing tool catalogue, types, MCP/CLI names and dispatch imports remain available as compatibility facade. |
| `sharpit.engine.tool_dispatch` | `ToolGate`, `tool_gate`, `call_tool`, `tool_info`, `cli_status`, and `cli_invoke` own dispatch and CLI behavior; dynamic facade lookup preserves `tools.TOOLS` and `tools.tool_gate` monkeypatches. |
| `sharpit.engine.tool_registry.catalogue` | `catalogue() -> Sequence[Tool]` returns the registered tools in contract order. |
| `sharpit.pytest_plugin.options.resolve` | Existing `resolve(config: Any) -> PluginOptions` remains the canonical option parser. |
| `sharpit.pytest_plugin.session.resolve_options` | Compatibility seam delegating to `options.resolve`; `pytest_sessionfinish(session, exitstatus)` owns session finalization. |
| `sharpit.pytest_plugin.apps` | `_load_app(spec: str) -> tuple[str, object]`, `_model_of(app: object) -> ApiModel`, `_run_advisors(state, *, load_app=None)`; plugin facade passes its re-exported loader so monkeypatches stay effective. |
| `sharpit.pytest_plugin.report_io.write_report` | `write_report(state, session, exitstatus) -> None` owns report serialization and exit status; plugin keeps `_write_report` compatibility alias. |
| `sharpit.pytest_plugin.terminal.pytest_terminal_summary` | Existing pytest terminal summary hook moved intact; dynamically resolves plugin helper seams. |
| `sharpit.pytest_plugin.__init__` | Existing pytest hook names remain importable for plugin registration. |
