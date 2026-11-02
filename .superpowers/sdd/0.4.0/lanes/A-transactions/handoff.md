# Handoff: A-transactions

Implementer: Codex (GPT-6)

## Status

In progress. Started at `a766132de82c0305b5cc4a1066a8a1a24cd2745a` on `lane/0.4.0-A-transactions`; no upstream changes merged or rebased.

## Done

- Read required rules/spec/plans/F handoff; registered as `codex-0-4-0-a-transactions`.
- Task 1 nullable reason fixture committed (`d50d6b6`). Captured golden absent, parity remains unverified.
- Task 2 recorder and connection callbacks committed (`88609ea`); 8 targeted tests, Ruff check and format check passed.
- Task 3 API red committed (`4723cd4`): installed FastAPI app does not yet expose a transactions report.

## Next step

Implement Task 3 wiring, REST/SSE routes, MCP and CLI tools, panel flag, API/safety/masking tests. Then Tasks 4–6 as time permits. Keep full gate logs outside this worktree and xdist at 4.

## Decisions

- F handoff API is `_configure_capture(app, ctx, settings) -> CaptureWiring`; listener attach uses `CaptureState.attachers` for late imports and lifespan restarts.
- F exposes begin/commit/rollback/savepoint events only. Failed commit is surfaced after pre-commit; park `test_failed_commit_is_unknown` under O1; no `engine/sqla.py` edits.
- Class-level listener registration is reference-counted across contexts.
- Live check requires the shared example, which this lane cannot edit; coordinator runs it.

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/capture/test_transactions.py::test_records_committed_root` | `79a37b42dd5a345c86a08766791adef111c3121d` | `a captured transaction must receive a positive id` |
| `tests/engine/capture/test_transactions.py::test_bounded_entries_report_stats` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `the transaction ring must respect max_entries` |
| `tests/engine/capture/test_transactions.py::test_clear_keeps_total_captured` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `clear must empty the retained transactions` |
| `tests/engine/capture/test_transactions.py::test_paused_records_nothing` | `a099754552f9d66f29d7e5e45f29d7e5e45a60e28d5fc14d47` | `a paused recorder must return the sentinel id` |
| `tests/engine/capture/test_transactions.py::test_error_message_is_masked` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `transaction errors must not expose connection passwords` |
| `tests/engine/capture/test_transactions.py::test_sql_trace_unavailable_warning` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `missing SQL Trace must explain why statement counts are unavailable` |
| `tests/engine/capture/test_transactions.py::test_savepoint_is_a_child_entry` | `12bf8d03b4dd14c916d74e77b6d4b1bf287a198d` | `releasing a savepoint must not close its outer transaction` |
| `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_a_committed_sqlite_transaction` | `4723cd4f6e5ccde839dbaa3f4eee8af47f11e96b` | `the implemented transactions panel must expose its GET report route` |

## Gates / live check

Task 2 targeted tests and Ruff passed before commit. The Task 3 red returned HTTP 403 because the panel is currently unimplemented. Full gates/live check not run.
