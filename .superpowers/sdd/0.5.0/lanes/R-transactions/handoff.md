# R-transactions handoff

Implementer: Claude subagent (claude-opus-5-5)

Status: DONE. Branch `lane/0.5.0-R-transactions`, worktree `C:\development\github\sharpit-wt\0.5.0-R-transactions`.

## Commits

| SHA | Commit |
|---|---|
| 4378fea | merge: lane/0.4.0-A-transactions (666a0ab) onto release/0.5.0 |
| 333a91a | test: nested unnamed savepoints and an all-open ring (red) |
| aca8e8a | fix: bound the transactions ring and key savepoints by depth |
| 1b8f5eb | test: transactions review round 2 minors (red) |
| 625ca64 | fix: transactions review round 2 minors |
| df651a9 | test: transactions report golden parity (red) |
| c94811f | fix: transactions isolation reports UNKNOWN for golden parity |
| 43f00a0 | feat: transactions panel enabled (must-cover names, inactive 404 test) |
| 14f874c | chore: rebuild the committed UI bundle for the transactions view |
| 35a700b | refactor: keep transactions attach under the complexity ratchet |

Red SHAs, assertions and dispositions: `findings.md`.

## Task 0: merge mapping

`git merge lane/0.4.0-A-transactions` (666a0ab), not a cherry-pick. Conflicts:

- `src/sharpit/engine/sqla.py` (deleted by F5b, modified by the lane): the lane's hunk (`handle_error` added to the
  `ConnectionEvent` Literal and to `CONNECTION_EVENTS`) moved into `src/sharpit/engine/sqla/events.py`; the stale
  "never edits this module" docstring sentence fixed there (review finding 8). `sqla.py` removed.
- `src/sharpit/fastapi/routes/transactions.py`: took the lane's version (the base is F's empty stub).
- Auto-merged: `fastapi/install.py` (`_configure_capture` only), `fastapi/capture.py`. No duplicated top-level defs
  (checked with a grep over every merged source file).
- Baseline after the merge: lane tests + `tests/engine/test_sqla*.py tests/test_foundation_round2.py
  tests/test_safety_matrix.py tests/safety/ tests/fastapi/test_capture_wiring.py`: 1296 passed, 3 skipped, 1 failed:
  the transactions overhead budget under `-n 4` (30.889 µs vs 30 µs, "within the noise"); it passed alone (1 passed),
  so it was load, not the rebase.

## Decisions

- Savepoint depth resets on the root `begin` and on the root commit/rollback (`_end`), not through pool `checkin`/`reset`
  as the plan sketched: the root begin always precedes the next `begin_nested()` on a checked-out connection, and it
  needed no new slot. Pool `checkin` IS used, for the post-commit point (finding 3).
- Finding 3: SQLAlchemy has no event after the DBAPI commit returns. The row closes COMMITTED at the `commit` event (so
  the status is immediate, as before) and is re-closed by `TransactionRecorder.settle` at the first post-commit point:
  pool `checkin`, the next `begin`/`rollback`, or a later non-statement `handle_error`. Known limit: a connection held
  idle after `commit()` adds the idle time until one of those points.
- `engine/sqla/events.py` gains `add_pool_listener("checkin", fn)` (Pool class-level, idempotent, `None` without
  SQLAlchemy). It is not re-exported from `sqla/__init__.py` (outside May-touch); `capture/transactions.py` imports it
  from `sharpit.engine.sqla.events`.
- `conn.info` holds `(weakref.ref(recorder), entry_id)`, never a context (finding 10); failures while closing a row
  report through `dispatch.routing_failed` (no context at hand).
- Golden parity: `isolation` is `"UNKNOWN"` (BootUI's value when it cannot tell), not `null`; `nullable.json` unchanged.
- Must-cover names: renamed `test_transaction_get_and_stream_do_not_trigger_side_effects` ->
  `test_transactions_get_no_side_effects` and `test_transaction_error_message_masks_connection_secrets` ->
  `test_error_message_masked` (bodies unchanged); added `test_inactive_transactions_paths_404`.
- Finding 6 is a pin, not a red (see `findings.md`).
- `IMPLEMENTED = True` / `implemented = true` were already set by the 0.4.0 lane.

## Must-cover

| Test | Exists | Passes at head |
|---|---|---|
| test_nested_unnamed_savepoint_rollback_is_rolled_back | yes | yes |
| test_untracked_inner_savepoint_does_not_close_tracked_outer | yes | yes |
| test_ring_stays_bounded_when_every_entry_is_open | yes | yes |
| test_savepoint_depth_reset_after_error_and_checkin | yes (pin) | yes |
| test_later_non_statement_error_does_not_rewrite_committed_row | yes | yes |
| test_report_golden_parity | yes | yes |
| test_transactions_get_no_side_effects | yes | yes |
| test_error_message_masked | yes | yes |

## Live check

In process, no port bound: `examples.fastapi_sqla.app.create_app(db_dir=<temp>)` under `TestClient` with lifespan;
`GET /owners` 200, `GET /owners/n-plus-one` 200, then `GET /sharpit/api/transactions` 200: `totalCaptured` 3,
`warnings` [], statuses COMMITTED 1 (seed) + ROLLED_BACK 2 (the read requests), `isolation` "UNKNOWN", `traceId` set
on request rows, `sqlStatementCount` 2 on the N+1 row correlated from SQL Trace.

## Gates (last run)

- `uv run ruff check`: all checks passed; `uv run ruff format --check`: 570 files formatted; `uv run pyright`: 0 errors.
- Full suite, `-n 4`, at 14f874c (log `0.5.0-integration/.superpowers/sdd/0.5.0/logs/R-transactions-full.log`):
  4790 passed, 11 skipped, 6 failed. Dispositions:
  - `tests/test_code_shape.py::test_complexity_only_goes_down` (`attach` C901 11 > 10): mine, fixed in 35a700b
    (`refactor:`; `_listen()` extracted), green after.
  - `tests/test_overhead_harness.py::test_every_budget_module_runs_last` and
    `::test_budget_order_check_survives_a_fixture_conftest`: `test_transactions_overhead.py` (from the 0.4.0 lane) is
    missing from `TIMING_MODULES` in `tests/conftest.py`, which this lane may not edit. Coordinator question 3.
  - `tests/fastapi/test_capture_overhead.py::test_request_overhead_budget`, `tests/fastapi/test_sql_trace_overhead.py::
    test_statement_overhead_budget`: load. Alone: sql-trace passed; capture passed twice at head and twice at base
    1fcaf46 (paired run), one solo overshoot "within the noise".
  - `tests/scripts/test_lane_gate.py::test_must_cover_uses_full_node_ids_and_refuses_skips`: xdist worker crash; passed
    alone.
- UI: `npm ci`, `npm run check`, vitest `tests/component/Transactions.test.ts` 2/2, `npm run build` (log
  `R-transactions-ui.log`).

## Questions for the coordinator

1. `src/sharpit/ui/static/` (index.html + two hashed assets) is outside May-touch but the brief requires the rebuilt
   bundle after UI changes; the 0.4.0 lane changed `Transactions.svelte` without rebuilding, so the drift job would
   fail without commit 14f874c. Keep or drop it at merge.
2. The transactions overhead budget passes alone but overshot within the noise once under `-n 4` load on the base of
   this lane (before any fix); budget constant untouched.

3. Add `test_transactions_overhead.py` to `TIMING_MODULES` in `tests/conftest.py` (outside May-touch) so the
   transactions budget runs last; `tests/test_overhead_harness.py` fails until then.

## How to resume

Nothing left in the lane plan. If review asks for changes: new red test first (never edit a test after its red
commit), `uv run python scripts/dev/red_check.py <ids>`, then the fix.
