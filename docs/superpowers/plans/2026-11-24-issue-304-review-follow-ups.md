# Issue #304: 0.9.0 review follow-ups

**Goal:** close the eight follow-ups from the 0.9.0 release reviews. None changes a public contract; one (Task 8) fixes
a wrong summary.

**Branches:** two pull requests, so the hot-path change is reviewed on its own.

- `refactor/304-follow-ups`: Tasks 1-5 and 8; Task 6's closing note.
- `refactor/304-sql-aggregate`: Task 7 (SQL listener hot path), after the first is merged.

**Method:** test-driven where behaviour changes or coverage is missing (Tasks 1, 8); a pure refactor (Tasks 2-5, 7)
keeps the named tests green, and each is checked by breaking the code it protects and seeing a named test fail.

**Revision 2** folds in the plan review: Task 1 asserts the transaction entry's `method`, not
an SQL Trace row; Task 2 rewrites one test, not five; Task 3 lists the test callers; Task 4 drops a test that could not
fail; Task 6 is closed without a helper; Task 7's proof is the branch tests and paired timings, not a corpus dump;
Task 8 targets the collection-time usage error.

## Seams under test

| Seam | What it catches | What it misses |
|---|---|---|
| Transaction entry `method` from a real SQLAlchemy `begin` and savepoint | A frame-depth change that points the method at a sharpit or SQLAlchemy frame | SQL Trace `callSite` (already covered by its own tests) |
| `ChangeStream.subscribe` awaited on a forward target | A forward that drops a signal once the `__dict__` clause goes | Nothing: the other four tests patch the stream they call and do not depend on the clause |
| Console route tests (`tests/engine/test_console_contract.py`) | A cached pattern that matches differently, method selection, first-match order | Speed, which has no test |
| `pytester` run with a collection-time `UsageError` from the marker | A sharpit summary printing `status: pass` after the run was aborted | Usage errors raised outside the marker |
| SQL Trace aggregate branch tests (`tests/engine/capture/test_sqltrace.py:277,414`, `test_sqltrace_reentry.py:90`) | A split that changes new-group, eviction, promotion or the evicted-meanwhile reentry | Timing (paired measurement and the budget test) |

## Tasks (first pull request)

### Task 1: pin the frame depth of the transaction method

Files: `src/sharpit/engine/capture/sqltrace.py:98` (`sys._getframe(6)`), used by `transactions._begin`
(`src/sharpit/engine/capture/transactions.py:387`), which writes the entry's `method`.

- New coverage: every transaction test sets `sql_trace_capture_call_site=False` today, so this test will not start
  red. It is a characterization test: a real SQLAlchemy `begin` and a savepoint from a test function, each asserting
  the entry's `method` is that test's `module:function:line`.
- It must bite: changing the depth from 6 to 8 locally makes it fail; the red output goes in the PR.
- A comment at the call names the six frames the fixed depth skips. The depth itself does not change.

### Task 2: drop the `"signal" in target.__dict__` clause

Files: `src/sharpit/engine/capture/streams.py:197`; `tests/engine/capture/test_activity.py:431-436`
(`test_fan_in_forwards_source_ticks`), the only test that patches `signal` on a forward target.

- That test awaits a real subscription on the target, with a timeout, instead of replacing `signal`; then the clause
  is removed. The four tests that patch the stream they signal directly (`test_exceptions.py:157,175`,
  `test_securitylogs.py:206`, `test_sqltrace.py:393`) stay as they are: they test failure isolation, which a
  subscription cannot inject.
- Check: removing the clause before rewriting the test makes it fail.

### Task 3: one `HOOK_EXCEPTION_HANDLERS`, public helpers

Files: `src/sharpit/fastapi/capture.py:84,260,632,648,654,670`, `src/sharpit/fastapi/capture_exceptions.py:30`;
test callers `tests/fastapi/test_binding_diagnostics.py:490,498`, `tests/fastapi/test_capture_without_pydantic_core.py:43,60,78`,
`tests/fastapi/test_exceptions_api.py:557`.

- The constant stays in `capture_exceptions.py`; `capture.py` refers to it as `capture_exceptions.HOOK_EXCEPTION_HANDLERS`.
- `_record_logged`, `_validation_error`, `_endpoint_name`, `_record_exception` and `_route_template` lose the leading
  underscore; the five `reportPrivateUsage` ignores go. `capture.py` keeps calling them through the module attribute
  (`capture_exceptions.<name>`), so a test that patches the module attribute still intercepts the call.
- Definitions, internal references and test callers change in one commit. The capture middleware overhead budget tests
  run unchanged.

### Task 4: compile each console route template once

File: `src/sharpit/engine/console/console.py:41` (`_compile`), `:56` (`match_route`).

- `_compile` gets `functools.cache`. Its input is a route template from the console's own route table, never request
  data, so the cache is bounded by the table's size. `match_route` checks `route.method` before matching the path.
- No new test: `re.compile` already returns a cached object, so a pattern-identity test could not fail. The existing
  route tests cover parameter extraction, method selection and first-match order. #260 needs no separate wiring.

### Task 5: one host-loop provider

Files: `src/sharpit/fastapi/routes/__init__.py:50` (`_RequestHostLoopProvider`), `src/sharpit/engine/tools.py:114`
(`_BoundHostLoopProvider`).

- The routes use the engine's provider, made public as `BoundHostLoopProvider`; the routes' class is deleted. The
  port (`engine/spi.py:13`) already returns `AbstractEventLoop | None`, so no type changes.

### Task 6: the duplicated `_read` stays, with the reason

Files: `src/sharpit/engine/tools04/mysql.py:33`, `src/sharpit/engine/tools04/postgresql.py:33`.

- A shared helper would take six inputs (refresh coroutine, async-engine check, unavailable report, summary
  formatter, wait timeout, database name) to save about fifteen lines, and would couple two dialect modules that
  otherwise share nothing. The item is closed on the issue with that reason; no code changes.

### Task 8: no `status: pass` after a marker usage error

Files: `src/sharpit/pytest_plugin/__init__.py:181-185` (`pytest_collection_modifyitems` calls `budget_for`, which raises
the `UsageError` at `src/sharpit/pytest_plugin/marker.py:58`), the summary writer in `src/sharpit/pytest_plugin/terminal.py`.

- Red: extend `tests/pytest_plugin/test_plugin_swallowed.py:487` and parametrize it over two marker usage errors (a
  missing reason under `--sharpit-require-reason`, and an invalid `max_queries`). Each asserts the exit status
  `USAGE_ERROR`, the marker diagnostic, and that the sharpit summary does not print `status: pass`.
- Green: the summary writer sees the session's exit status; on a usage error it prints no gate status (the existing
  status vocabulary is unchanged).

## Task 7 (second pull request): split `_update_aggregate`

File: `src/sharpit/engine/capture/sqltrace.py:391`. Hot path: the SQL listener's per-statement overhead budget applies,
and it is never raised.

- Proof: the branch tests named in the seam table, plus a reentry test that evicts the group between the lookup and the
  promotion if `test_sqltrace_reentry.py` does not already cover that branch.
- Timing: paired base and head runs of `tests/fastapi/test_sql_trace_overhead.py` with `-n 0` on an idle machine,
  reported in the PR, in addition to the budget test.
- The split keeps the LRU branches under one lock and adds no dictionary lookup on the common path. If the function's
  complexity does not fall, or the paired timing regresses, the split is dropped and the item is closed with the
  measurement.

## Verification

- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`.
- `uv run pytest -q -n 4` on `tests/engine/capture`, `tests/fastapi`, `tests/engine/test_console_contract.py`,
  `tests/engine/test_tools04_host_loop.py`, `tests/engine/test_tools04_request_loop.py` and `tests/pytest_plugin`;
  CI runs the full suite.
- `tests/complexity_baseline.json` and `sonar-baseline.txt` only go down; the PR body lists each
  `finding → test → red output`.
