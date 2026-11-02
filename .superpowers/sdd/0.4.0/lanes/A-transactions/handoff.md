# Handoff: A-transactions

Implementer: Codex (GPT-6)

## Status

In progress. Started at `a766132de82c0305b5cc4a1066a8a1a24cd2745a` on `lane/0.4.0-A-transactions`; no upstream changes merged or rebased.

## Done

- Read required rules/spec/plans/F handoff and registered with agentctl (`codex-0-4-0-a-transactions`).
- Task 1 nullable `readOnly` reason fixture committed (`d50d6b6`). The captured transaction golden is absent; parity remains unverified.
- Task 2 recorder and connection callbacks committed (`88609ea`); 8 engine tests and targeted Ruff checks passed.
- Task 3 REST/SSE, recorder wiring, MCP/CLI tools and flag are implemented locally. The focused backend run passed 15 tests; feature commit is pending.
- Task 5 UI assertion tests committed at `46af71a`; both fail on the placeholder for the expected missing transaction view.

## Next step

Finish Task 3/5 commit boundaries, add the fixed Svelte view, and run `npm --prefix ui run check` plus the focused Vitest file. Then add the transaction overhead budget, update checklist/docs, run four gates detached with pytest log outside the worktree, then lowest-direct/no-SQLAlchemy if time permits.

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
| `tests/engine/capture/test_transactions.py::test_sql_trace_unavailable_warning` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `missing SQL Trace must explain why statement counts are unavailable` |
| `tests/engine/capture/test_transactions.py::test_savepoint_is_a_child_entry` | `12bf8d03b4dd14c916d74e77b6d4b1bf287a198d` | `releasing a savepoint must not close its outer transaction` |
| `tests/engine/capture/test_transactions.py::test_savepoint_closes_one_child_per_context` | `41964581198fd775bd63e5b3d9559c87d28eeaf0` | `a savepoint event must close its child entry in each context` |
| `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_committed_sqlite_with_loopback_client` | `5212a0865ee4ca430b56b4ef5eaf344ccf18f3f5` | `the implemented transactions panel must expose its GET report route` |

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

Focused backend log: `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/A-transactions-focused.log` (15 passed). Full gates and live check not run.
