# Issue #260, slice 1: console contract defects

`src/sharpit/engine/console/` has no production caller. Its behaviour differs from
`docs/superpowers/plans/2026-11-22-sharpit-0.9.0/f0-console-contract.md` (the contract) in the points below. They are
fixed before any route is wired through it. No route, adapter, setting or guard rule changes.

## Scope

| # | Difference | Contract | Code at `00e5a67a` |
|---|---|---|---|
| 1 | An exhausted event source raises `RuntimeError` | the stream closes with a `retry: 1000` frame | `types.py`, `stream_frames` |
| 2 | An error in the source's `aclose` escapes | as `fastapi/sse.py`: suppressed | `types.py`, `stream_frames` |
| 3 | `frame_sse` splits with `splitlines()` | as `fastapi/sse.py`: `split("\n")` | `types.py`, `frame_sse` |
| 4 | A known path with another method answers 404 | 405 with `Allow` | `console.py`, `match_route` and `_handle` |
| 5 | `HEAD` on a `GET` route answers 404 | status and headers of `GET`, empty body | `console.py`, `_handle` |
| 6 | `HEAD` on a stream route answers 404 | 405, `Allow: GET`, handler not run | `console.py`, `_handle` |
| 7 | `AdvisorViolationError` answers 500 | `exc.status` with `{"error": exc.message}` | `console.py`, `Console.handle` |
| 8 | Security headers are added to a response that sets its own CSP | added only without a CSP | `console.py`, `_response_headers` |

Out of scope, with their owner: `IdleTracker.mark_active()` and the audit hook of multiplexed tool calls (both need the
wiring slice), the differential gate, the `werkzeug` boundary, every Flask part.

## Safety

- The guard chain runs first and is unchanged: a denied request is answered by the guard, never by 404, 405 or `HEAD`
  handling. A test sends a wrong method and a `HEAD` that the guard refuses and expects the guard's answer.
- A handler runs only for its own method, and the `GET` handler for `HEAD` (a read). `HEAD` never reaches an action.
- 405 names methods only, after the guard, and 404 keeps its body.
- `AdvisorViolationError.message` reaches the body as the FastAPI routes return it today; nothing new is echoed.

## Tasks

Each test is seen red for its assertion (`scripts/dev/red_check.py`) before the fix, one condition per assert. A crash is
not a red: where the defect raises, the test catches it and asserts on the collected frames.

- [ ] **Task 1, streams** (`tests/engine/test_console_streams.py`): an exhausted source yields its frames and then
      `b"retry: 1000\n\n"`; a source whose `aclose` raises still ends; data with a trailing newline and with a vertical
      tab gives the same bytes as `fastapi/sse.py`. Change `stream_frames` and `frame_sse` only.
- [ ] **Task 2, methods** (`tests/engine/test_console_contract.py`): `POST` to a `GET` route gives 405, body
      `{"error": "Method Not Allowed"}` and the exact `Allow` (`GET, HEAD`); `Allow` lists every method of a path with
      several; an unknown path stays 404; `HEAD` gives the `GET` status and headers with an empty body; `HEAD` on a
      stream route gives 405 with `Allow: GET` and does not call the handler; the guard's answer wins over each.
      `RouteSpec` has no mark for a stream route, so it gains `stream: bool = False`; the refusal reads that field and
      therefore acquires no slot.
- [ ] **Task 3, errors and headers** (`tests/engine/test_console_contract.py`): `AdvisorViolationError` gives its status
      and message; another exception stays a masked log line and 500; a response with its own CSP keeps exactly its own
      headers, one without gets all of them.
- [ ] Each fix is removed in turn and a named test fails.

## Verification

- [ ] `uv run --extra test pytest -q -n 4 tests/engine/test_console_contract.py tests/engine/test_console_streams.py
      tests/engine/test_import_boundary.py tests/test_code_shape.py tests/test_agent_workflow.py tests/docs`
- [ ] `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`.
- [ ] The complexity baseline does not rise.
- [ ] `git diff --stat origin/main...HEAD` lists only the console package, its tests and this plan.
