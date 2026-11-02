# Handoff: A-transactions

Implementer: Codex (GPT-6)

## Status

In progress. Started at `a766132de82c0305b5cc4a1066a8a1a24cd2745a` on `lane/0.4.0-A-transactions`; no upstream changes merged or rebased.

## Done

- Read required rules/spec/plans/F handoff and registered with agentctl (`codex-0-4-0-a-transactions`).
- Task 1 nullable `readOnly` reason fixture committed (`d50d6b6`). The captured transaction golden is absent; parity remains unverified.
- Task 2 recorder and callbacks committed (`88609ea`); REST/SSE, wiring, MCP/CLI tools and flag committed (`7d3a672`); UI view committed (`b422cd1`); overhead budget committed (`895a4d7`).
- Focused backend tests passed (16 tests), then four targeted checks passed for async engines, internal callback exclusion, report-time SQL correlation, and late-import/partial listener retry (`66fec2c`). UI Vitest passed 2/2 and `npm --prefix ui run check` exited 0.
- Overhead: 14.507 µs over a 30 µs budget, 13.519 µs noise. Temporary `time.sleep(0.0001)` control failed at 643.573 µs and was removed.
- Lane docs and §6.1 checklist updated.

## Next step

Run the four gates: `ruff check`, `ruff format --check`, `pyright`, and full `pytest -q -n 4` detached with its log outside this worktree. Then run lowest-direct and no-SQLAlchemy checks if time permits; update gate status, commit evidence, and report. Live check is coordinator-owned because the shared sample is outside lane scope.

## Decisions

- F handoff API is `_configure_capture(app, ctx, settings) -> CaptureWiring`; listener arm/removal uses `CaptureState.attachers` so late SQLAlchemy imports and lifespan restarts work.
- F exposes begin/commit/rollback/savepoint events only. SQLAlchemy commit failure is surfaced after pre-commit; `test_failed_commit_is_unknown` is parked under O1. `engine/sqla.py` is untouched.
- Connection listeners are reference-counted across contexts; savepoint events close one nested entry per target context.
- Live check uses the coordinator-owned example, which this lane cannot edit.

## Real pytest red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/capture/test_transactions.py::test_records_committed_root` | `79a37b42dd5a345c86a08766791adef111c3121d` | `a captured transaction must receive a positive id` |
| `tests/engine/capture/test_transactions.py::test_bounded_entries_report_stats` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `the transaction ring must respect max_entries` |
| `tests/engine/capture/test_transactions.py::test_clear_keeps_total_captured` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `clear must empty the retained transactions` |
| `tests/engine/capture/test_transactions.py::test_paused_records_nothing` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `a paused recorder must return the sentinel id` |
| `tests/engine/capture/test_transactions.py::test_error_message_is_masked` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `transaction error messages must not expose connection passwords` |
| `tests/engine/capture/test_transactions.py::test_sql_trace_unavailable_warning` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `missing SQL Trace must explain why statement counts are not correlated` |
| `tests/engine/capture/test_transactions.py::test_savepoint_is_a_child_entry` | `12bf8d03b4dd14c916d74e77b6d4b1bf287a198d` | `releasing a savepoint must not close its outer transaction` |
| `tests/engine/capture/test_transactions.py::test_savepoint_closes_one_child_per_context` | `41964581198fd775bd63e5b3d9559c87d28eeaf0` | `a savepoint event must close its child entry in each context` |
| `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_committed_sqlite_with_loopback_client` | `5212a0865ee4ca430b56b4ef5eaf344ccf18f3f5` | `the implemented transactions panel must expose its GET report route` |
| 	ests/engine/capture/test_transactions.py::test_listener_remover_releases_attachments_when_discarded | 6faa15c5a22c5773f87590ddb403e0c89ee2f587 | discarding the owning teardown must release all class-level listeners |

## UI reds

| Vitest test | Commit | Observed red output |
|---|---|---|
| `ui/tests/component/Transactions.test.ts::renders transactions, indents savepoints, and refreshes on a stream update` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |
| `ui/tests/component/Transactions.test.ts::hides transaction controls for a read-only panel` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |

## Historical red

| Test id | Historical SHA | Why superseded |
|---|---|---|
| `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_a_committed_sqlite_transaction` | `4723cd4f6e5ccde839dbaa3f4eee8af47f11e96b` | The TestClient source was not loopback-trusted; replacement explicitly uses a loopback client. |

## Gates / live check

Targeted results recorded above; full four gates are next. Live check not run; coordinator-owned example is outside lane touch scope.


## Needs from coordinator

- `tests/fastapi/test_capture_wiring.py::test_all_capture_panels_disabled_adds_nothing`: this file's local `CAPTURE_PANELS` tuple omits `transactions`, so the test still observes `CaptureMiddleware` after the transactions panel is implemented. Add the lane flag to that test's disabled panel set; the file is outside this lane's May-touch list.
- `tests/test_safety_matrix.py::test_write_route_table_is_complete`: include `POST /sharpit/api/transactions/clear` and `POST /sharpit/api/transactions/recording` in the write-route contract. This file is coordinator-owned/protected for lanes.
- `tests/test_surface_follows_flags.py::test_every_shared_count_follows_a_flag_flip`: the data-flag scenario passes already-merged `tools.TOOLS` as the base and merges implemented transactions tools again, producing collisions. Build that scenario from the base-only catalogue or otherwise exclude already merged lane tools. This file is outside this lane's May-touch list.

## Preliminary full suite

The first detached `-n 4` run reported 3,777 passed, 5 skipped, 7 failed, 2 errors. It overlapped source edits and is not final verification. The named lane-owned listener cleanup and complexity failures are being addressed; several other failures are coordinator-owned or overhead noise. Rerun after the pending fixes. Log: `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/A-transactions-pytest.log`.
