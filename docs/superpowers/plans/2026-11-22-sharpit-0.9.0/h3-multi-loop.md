# Request-scoped host event loop provider

**Goal:** Run host-bound MCP and CLI tool work on the event loop servicing the request that invoked the tool, including on a process with multiple loops.

**Architecture:** `engine/tools04/hostloop.py` consumes a framework-free `HostLoopProvider` protocol. Each invocation carries its provider in `CallContext`; the FastAPI adapter binds the current ASGI request loop, while WSGI supplies no loop. The selected loop is validated immediately before submission. A tool never falls back to another request's loop and never creates a private loop for host work. When the invocation has no live loop, each tool keeps its behaviour from before this change: the pentest scan refuses with its 503 unavailable error; the MySQL, PostgreSQL and Database advisor tools keep their existing no-loop path (`asyncio.run` on a fresh loop, or the `ASYNC_FROM_CLI` report for an async engine).

**Predict verdict:** GO, 8/10.

## Global Constraints

- **Framework-free engine.** `engine/` never imports `fastapi` or `starlette` (a `TYPE_CHECKING` block is allowed).
- **No side effects on reads; actions only behind BootUI's gates.**
- **Every error found** becomes a regression test seen red first.
- The command-line client and tools preserve the import boundary; runtime dependencies remain unchanged.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| High | A tool receives the stale process-wide captured loop | Pass a request-scoped provider through the call context; assert loop identity using two live loops |
| High | Provider loop closes between selection and submission | Validate at selection and convert scheduling failure to unavailable; never fall back |
| High | WSGI has no event loop | Provider returns `None`; each tool keeps its no-loop behaviour (pentest 503, database tools' existing fallback) |
| Medium | CLI and MCP paths bind different request contexts | Exercise CLI action calls with `via="cli"` |

### Task 1: Request-scoped loop provider and regression tests

**Files:** `src/sharpit/engine/tools.py`, `src/sharpit/engine/tools04/hostloop.py`, the FastAPI routes that serve the MCP and CLI tool calls (`src/sharpit/fastapi/routes/`), `tests/engine/`, `tests/fastapi/`. There is no Flask console yet (Track F3): the WSGI case is proved in the engine with a provider that returns `None`, and the Flask adapter supplies that provider when F3 is built.

**Interfaces:** Produces `HostLoopProvider` protocol (`current_loop() -> AbstractEventLoop | None`) in the engine and an optional provider field on the tool call context. FastAPI supplies the current request loop; WSGI supplies an unavailable provider. Tools resolve the provider from the invocation, never shared capture state.

- [ ] **Step 1:** Add tests `test_each_tool_uses_the_loop_serving_its_request`, `test_closed_request_loop_does_not_fall_back_to_another_loop`, `test_wsgi_without_request_loop_returns_unavailable`, and `test_cli_database_actions_use_cli_request_loop`.
- [ ] **Step 2:** Run `uv run python scripts/dev/red_check.py <node ids>` and confirm the two-loop assertion identifies the wrong loop.
- [ ] **Step 3:** Commit regression tests as `test: cover request-scoped host loop selection`.
- [ ] **Step 4:** Add the provider protocol and bind it to each tool invocation at the adapter boundary; keep engine imports framework-free.
- [ ] **Step 5:** Preserve existing single-loop tests without edits; run the specified targeted verification matrix.
- [ ] **Step 6:** Commit as `fix: route host tools to request event loop, closes #287`.

## Definition of done

- [ ] All steps checked.
- [ ] `ruff check`, `ruff format --check`, and `pyright` pass before each commit.
- [ ] Two-loop test proves each tool runs on its invoking request's loop.
- [ ] WSGI test proves no loop is fabricated and the action remains unavailable.
- [ ] All specified regression tests pass with `-n 4`.
