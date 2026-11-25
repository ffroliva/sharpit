# Issue #260, slice 1: console contract defects

`src/sharpit/engine/console/` has no production caller. Its behaviour differs from
`docs/superpowers/plans/2026-11-22-sharpit-0.9.0/f0-console-contract.md` (the contract) in the points below. They are
fixed before any route is wired through it. No route, adapter, setting or guard rule changes. Rows 1 and 4 are the
defects named on #260; the other seven are adjacent differences in the same two files and belong to this slice.

## Scope

| # | Difference | Contract | Code at `00e5a67a` |
|---|---|---|---|
| 1 | An exhausted event source raises `RuntimeError` | as `fastapi/sse.py`: the stream closes with a `retry: 1000` frame | `types.py`, `stream_frames` |
| 2 | An error in the source's `aclose` escapes | as `fastapi/sse.py`: suppressed | `types.py`, `stream_frames` |
| 3 | `frame_sse` splits with `splitlines()` | as `fastapi/sse.py`: `split("\n")` | `types.py`, `frame_sse` |
| 4 | A known path with another method answers 404 | 405 with `Allow` | `console.py`, `match_route` and `_handle` |
| 5 | `HEAD` on a `GET` route answers 404 | status and headers of `GET` with its `Content-Length`, empty body | `console.py`, `_handle` |
| 6 | `HEAD` on a stream route answers 404 | 405, `Allow: GET`, handler not run | `console.py`, `_handle` |
| 7 | `AdvisorViolationError` answers 500 | `exc.status` with `{"error": exc.message}` | `console.py`, `Console.handle` |
| 8 | Security headers are added to a response that sets its own CSP | added only without a CSP | `console.py`, `_response_headers` |
| 9 | Core JSON answers have spaces, ASCII escapes and no `Content-Type` | as `error()` of the FastAPI adapter: compact UTF-8, `application/json` | `console.py`, `_json` |

Out of scope, with their owner: `IdleTracker.mark_active()` and the audit hook of multiplexed tool calls (both need the
wiring slice), `handle_asgi`/`handle_wsgi`, the move of the stream functions to `engine/console/sse.py`, the differential gate, the `werkzeug` boundary, every Flask part.

The contract departs from the FastAPI adapter of today in these points. They are listed so that the differential gate
does not report them as defects:

| Request | FastAPI adapter today | Contract or core | Disposition |
|---|---|---|---|
| `HEAD` on a stream route | 200, handler started | 405, `Allow: GET` | Contract departure, kept (row 6) |
| `/api/overview/` (trailing slash) | 307 to the path without it | 404 | Wiring slice: decided with the differential gate |
| `DELETE /api/dismissed-rules/` (empty `:path`) | 400 `Invalid rule id ''` | 404, or 405 when another template matches (`.+`) | Wiring slice: decided with the differential gate |
| `GET /api/data/repositories/` (empty `:path`) | 404, empty body | 404 JSON | Wiring slice: decided with the differential gate |
| Another method on a path with separate `GET` and `POST` routes (`/api/dismissed-findings`, `/api/code-paths/probes`) | `Allow` of the first partial match only | every method of the path | Contract departure, kept |
| `POST` or `DELETE` on a stream path | `Allow: GET, HEAD` | `Allow: GET` | Contract departure, kept (row 6) |
| Order of `Allow` | not fixed | fixed: `GET`, `HEAD`, `POST`, `DELETE` | Contract departure, kept; the gate compares it as a set |
| Bare mount 307 | absolute `Location`, `Content-Length: 0` | path-only `Location` | Wiring slice: decided with the differential gate |
| `HEAD` on a file response | headers of `GET`, no body | the core returns `file` unchanged | Wiring slice: the adapter keeps the `GET` headers and sends no file body |

## Safety

- The guard chain runs first and is unchanged: a denied request is answered by the guard, never by 404, 405 or `HEAD`
  handling. A test sends a wrong method and a `HEAD` that the guard refuses and expects the guard's answer.
- A handler runs only for its own method, and the `GET` handler for `HEAD` (a read). That every `GET` route is a
  read rests on the contract's `ROUTES` test (wiring slice).
- An unmarked stream route fails closed: when the `GET` handler of a `HEAD` returns a stream, the stream is closed (its
  slot released) and the answer is 405 with `Allow: GET`. If its close hook raises, the slot is already released and the
  answer is the masked 500.
- `HEAD` resolves the first matching `GET` route, as a `GET` would, and then reads its `stream` mark. It never goes on to
  a later template: `/api/exceptions/stream` precedes `/api/exceptions/{id}` and must not reach the detail handler.
- `Allow` follows the same rule: `HEAD` is listed only when the first matching `GET` route is not a stream.
- 405 names methods only, after the guard, and 404 keeps its body. Only a route's own body response is emptied for `HEAD`: a denial, 404, 405, 400 or 500
  keeps the core's error response, body included, and the adapter sends no body for `HEAD`. The stream 405 is the only
  answer that exists for `HEAD` alone.
- The contract gives exception mapping to the adapter boundary. `Console.handle` maps `BadRequest` and 500 today, and row
  7 joins them there; the wiring slice owns the transfer.
- `AdvisorViolationError.message` reaches the body as the FastAPI routes return it today; nothing new is echoed.

## Tasks

Each test is seen red for its assertion (`scripts/dev/red_check.py`) before the fix, one condition per assert. A crash is
not a red: where the defect raises, the test catches it and asserts that no exception was observed. The defaulted
`stream` field is added in its own commit, without dispatch behavior, so that the stream test fails on its assertion.
Guard precedence, the 404 of an unknown path and the masked 500 hold today: they are preservation tests, green before and
after, and each is shown to bite by removing its control.

- [ ] **Task 1, streams** (`tests/engine/test_console_streams.py`): an exhausted source yields its frames and then
      `b"retry: 1000\n\n"`; a source whose `aclose` raises after a timed-out stream lets no
      exception reach the reader; data with a trailing newline and with a vertical tab gives the same bytes as `fastapi/sse.py`. Change `stream_frames` and `frame_sse` only.
- [ ] **Task 2, methods** (`tests/engine/test_console_contract.py`): `POST` to a `GET` route gives 405, body
      `{"error": "Method Not Allowed"}` and the exact `Allow` (`GET, HEAD`); `Allow` lists every method of a path with
      several, in the fixed order; an unknown path stays 404; with a stream route before a parameterized sibling, `HEAD` on the stream path
      gives 405, `Allow: GET` and zero calls of either handler; `HEAD` gives the `GET` status and headers
      with an empty body and the `Content-Length` of a non-empty `GET` body, a length set by the handler is kept, 204 and 304 get none, and a
      file response keeps `file`; a `HEAD` whose handler raises gives the core's error response; an unmarked stream route gives
      405 after a handler that records an acquired slot and a close hook that ran, with `slots.count == 0`, and 500 when the
      hook raises; `POST` and `DELETE` on a marked stream path give 405 with the exact `Allow: GET`; `HEAD` on a stream route gives 405 with `Allow: GET` and does not call the handler; the guard's answer (status, body
      and headers, without `Allow`) wins over each.
      `RouteSpec` has no mark for a stream route, so it gains `stream: bool = False`; the refusal reads that field and
      therefore acquires no slot. The contract's `RouteSpec` listing gains the field in the same commit. Emptying the body
      is a helper of its own. The status or `Allow` assertion comes first; the zero-call tests hold today and are
      preservation tests.
- [ ] **Task 3, errors and headers** (`tests/engine/test_console_contract.py`): `AdvisorViolationError` gives its status
      and message; another exception stays a masked log line and 500; a response with its own CSP keeps exactly its own
      headers, one without gets all of them; 404, 405, 400, 500 and a denial are compact JSON (the static fallback keeps its bytes) with
      `Content-Type: application/json`, and a non-ASCII message is UTF-8. `test_response_headers_keeps_other_headers_when_csp_set` expects the
      opposite and is replaced.
- [ ] Each fix is removed in turn and a named test fails.

## Verification

- [ ] `uv run --extra test pytest -q -n 4 tests/engine/test_console_contract.py tests/engine/test_console_streams.py
      tests/engine/test_import_boundary.py tests/test_code_shape.py tests/test_agent_workflow.py tests/docs`
- [ ] `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`.
- [ ] The complexity baseline does not rise; method selection is a function of its own, so `_handle` does not rise above 5 (C901).
- [ ] `git diff --stat origin/main...HEAD` lists only the console package, its tests, the contract's
      `RouteSpec` listing and this plan.
