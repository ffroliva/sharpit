# Issue #304: 0.9.0 review follow-ups

**Goal:** close the eight follow-ups from the 0.9.0 release reviews. None changes a public contract; one (Task 8) fixes
a wrong summary status.

**Branches:** two pull requests, so the hot-path change is reviewed on its own.

- `refactor/304-follow-ups`: Tasks 1-6 and 8.
- `refactor/304-sql-aggregate`: Task 7 (SQL listener hot path), after the first is merged.

**Method:** test-driven where behaviour changes or a test is missing (Tasks 1, 4, 8); a pure refactor (Tasks 2, 3, 5,
6, 7) keeps the existing tests green and adds none, and is checked by deleting the old code path and seeing the named
tests still pass.

## Seams under test

| Seam | What it catches | What it misses |
|---|---|---|
| `SqlTraceRecorder` row `callSite` from a statement run inside `transactions._begin` | A frame-depth change that points the call site at sharpit's own frame | Other entry paths (already tested) |
| `ChangeStream.subscribe` | A forward that drops a signal once the `__dict__` clause goes | Tests that still patch `signal` on an instance |
| `match_route` result | A cached pattern that matches differently | Nothing new; the cache is a speed change |
| `pytester` run with `--sharpit-require-reason` and a reasonless accepted finding | `status: pass` printed after the usage error | Other usage errors |
| SQL Trace report over the gate corpus, before and after | Any byte of output change from the aggregate split | Timing (the overhead budget test covers it) |

## Tasks (first pull request)

### Task 1: name the frame layout in `call_site`

File: `src/sharpit/engine/capture/sqltrace.py:98` (`sys._getframe(6)`).

- Red: a test runs a statement through the transaction path (`transactions._begin`) and asserts the row's call site is
  the test's own line, not a sharpit frame.
- Green: a comment that names the six frames the fixed depth skips, shared by the three paths. If the red shows the
  transaction path lands on a different depth, the depth is taken per path, not shared.

### Task 2: drop the `"signal" in target.__dict__` clause

Files: `src/sharpit/engine/capture/streams.py:197`; tests that patch `signal` on an instance:
`tests/engine/capture/test_activity.py:436`, `test_exceptions.py:157,175`, `test_securitylogs.py:206`,
`test_sqltrace.py:393`.

- The tests observe signals through `subscribe` (the public seam) instead of replacing `signal`; then the clause is
  removed. The five tests stay green; deleting the clause before rewriting them shows which tests depended on it.

### Task 3: one `HOOK_EXCEPTION_HANDLERS`, public helpers

Files: `src/sharpit/fastapi/capture.py:84,260,632,648,654,670`, `src/sharpit/fastapi/capture_exceptions.py:30`.

- Keep the constant in `capture_exceptions.py`, import it in `capture.py`. Rename `_record_logged`,
  `_validation_error`, `_endpoint_name`, `_record_exception`, `_route_template` to public names and drop the five
  `reportPrivateUsage` ignores. No behaviour change; `capture.py` is on the capture middleware hot path, so the
  overhead budget tests run unchanged.

### Task 4: compile each console route template once

File: `src/sharpit/engine/console/console.py:41` (`_compile`), `:56` (`match_route`).

- `_compile` gets `functools.cache` (templates are a fixed, small set). A test asserts `match_route` returns the same
  route and parameters for each console route as before (the existing route tests), plus one that the pattern object
  is reused. #260 needs no separate wiring for this.

### Task 5: one host-loop provider

Files: `src/sharpit/fastapi/routes/__init__.py:50` (`_RequestHostLoopProvider`), `src/sharpit/engine/tools.py:114`
(`_BoundHostLoopProvider`).

- The routes use the engine's provider (made public as `BoundHostLoopProvider`); the routes' class is deleted. The
  engine class returns `None` for a missing loop, the routes' never had one; the routes always pass a loop, so the
  type widens without a behaviour change. Pyright must stay clean.

### Task 6: one `_read` for MySQL and PostgreSQL

Files: `src/sharpit/engine/tools04/mysql.py:33`, `src/sharpit/engine/tools04/postgresql.py:33`.

- One helper in `tools04` takes the refresh coroutine function and the database name for the two messages; each
  module keeps its own tool declaration. The existing `tools04` tests stay green; the message texts are unchanged.

### Task 8: no `status: pass` after a reason usage error

Files: `src/sharpit/pytest_plugin/marker.py:53` (the `UsageError`), the summary writer in
`src/sharpit/pytest_plugin/terminal.py`.

- Red: a `pytester` run with `--sharpit-require-reason` and an accepted finding without a reason asserts the sharpit
  summary does not print `status: pass` (it prints the usage error state, or no summary).
- Green: the smallest change that makes the summary see the usage error, at the root cause once the red shows where the
  status comes from.

## Task 7 (second pull request): split `_update_aggregate`

File: `src/sharpit/engine/capture/sqltrace.py:391`. Hot path: the SQL listener's per-statement overhead budget applies,
and it is never raised.

- Before: dump the SQL Trace report over the gate corpus on `main` to a file outside the repo.
- Split the four-state branch (new group, eviction, move to end, the evicted-meanwhile race) into named steps under the
  same lock, without an extra dictionary lookup on the common path.
- After: the same dump, byte-identical; `tests/fastapi/test_sql_trace_overhead.py` green, run with `-n 0` on an idle
  machine. If the split costs measurable time on the hot path, it is dropped and the issue item closed with the
  measurement.

## Verification

- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`.
- `uv run pytest -q -n 4` on the touched test directories (`tests/engine/capture`, `tests/fastapi`,
  `tests/engine/console`, `tests/engine/tools04`, `tests/pytest_plugin`); CI runs the full suite.
- `tests/complexity_baseline.json` and `sonar-baseline.txt` only go down; the PR body lists each
  `finding → test → red output`.
