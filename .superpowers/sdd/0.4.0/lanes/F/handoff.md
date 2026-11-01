# Lane F handoff

Status: Task 1 complete; Task 2 is next.

- Base: `7e5fc150946ee4d870433d96a41a6627b343364a` (`release/0.4.0`); worktree branch `lane/0.4.0-F`.
- Red commit: `869db29d181a3ad98df7eb5ba6201b4cbc0e091f`, `test: pin foundation split contracts`.
- Red tests and assertion messages are recorded in `findings.md`.
- Task 1 refactor is green: focused run passed (127 passed, 3 warnings) across the new contracts and existing tool,
  pytest option/report, and FastAPI install tests. Ruff check and format check passed for changed Python files.
- The first focused rerun logged inside the repo and tripped the no-side-effects fixture's cwd scan; the clean rerun
  placed logs outside the worktree.
- Next: Task 2 O4 flags and absent-surface test, then lane gate, goldens, UI, and remaining minimum-cut interfaces in plan order.

## Consumer interface table

| Module / symbol | Contract for later lanes |
|---|---|
| `sharpit.fastapi.adapter` / `sharpit.install` | Existing `install(app, *, settings=(), engines=(), health_checks=None, **options) -> SharpitHandle` contract and adapter compatibility imports remain available. |
| `sharpit.fastapi.route_registry.register_routes` | `register_routes(app: Any, routes: Iterable[Any]) -> None`; appends routes in input order. |
| `sharpit.engine.tools` | Existing tool catalogue, types, MCP/CLI names and dispatch imports remain available as compatibility facade. |
| `sharpit.engine.tool_dispatch` | `ToolGate`, `tool_gate`, `call_tool`, `tool_info`, `cli_status`, and `cli_invoke` own dispatch and CLI behavior. |
| `sharpit.engine.tool_registry.catalogue` | `catalogue() -> Sequence[Tool]` returns the registered tools in contract order. |
| `sharpit.pytest_plugin.options.resolve` | Existing `resolve(config: Any) -> PluginOptions` remains the canonical option parser. |
| `sharpit.pytest_plugin.session.resolve_options` | Compatibility seam delegating to `options.resolve`. |
| `sharpit.pytest_plugin.apps` | `_load_app(spec: str) -> tuple[str, object]`, `_model_of(app: object) -> ApiModel`, `_run_advisors(state)`; plugin facade re-exports these names. |
| `sharpit.pytest_plugin.__init__` | Existing pytest hook names remain importable for plugin registration. |
