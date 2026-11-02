# Findings: A-transactions

## Open / parked

| Finding | Test | Red commit | Red output | Status |
|---|---|---|---|---|
| No BootUI captured golden is available in the lane worktree | `test_report_golden_parity` (Task 3) | — | — | parked until coordinator supplies fixture; nullable reason is recorded |
| Commit failure is surfaced after SQLAlchemy's pre-commit callback, but F's slot has no failure event | `test_failed_commit_is_unknown` (Task 2) | — | — | parked under O1; do not modify `engine/sqla.py` |

## Fixed findings

| Finding | Test | Red commit | Fix commit |
|---|---|---|---|
| Recorder did not assign ids or retain committed root transactions | `tests/engine/capture/test_transactions.py::test_records_committed_root` | `79a37b42dd5a345c86a08766791adef111c3121d` | `88609ea6cfec6d00fcb8be5c4e56674fc78e01bc` |
| Recorder did not bound entries, maintain totals, honor pause/clear, or mask errors | `tests/engine/capture/test_transactions.py::{test_bounded_entries_report_stats,test_clear_keeps_total_captured,test_paused_records_nothing,test_error_message_is_masked,test_sql_trace_unavailable_warning}` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `88609ea6cfec6d00fcb8be5c4e56674fc78e01bc` |
| Savepoint begin marked the outer transaction unknown | `tests/engine/capture/test_transactions.py::test_savepoint_is_a_child_entry` | `12bf8d03b4dd14c916d74e77b6d4b1bf287a198d` | `88609ea6cfec6d00fcb8be5c4e56674fc78e01bc` |
| Savepoint release closed only one of several target contexts | `tests/engine/capture/test_transactions.py::test_savepoint_closes_one_child_per_context` | `41964581198fd775bd63e5b3d9559c87d28eeaf0` | `7d3a67252dd03cd8a135cfc3b4ba177fb056c176` |
| The implemented panel had no transaction report route | `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_committed_sqlite_with_loopback_client` | `5212a0865ee4ca430b56b4ef5eaf344ccf18f3f5` | `7d3a67252dd03cd8a135cfc3b4ba177fb056c176` |

## Superseded reds

| Test id | Historical SHA | Why |
|---|---|---|
| `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_a_committed_sqlite_transaction` | `4723cd4f6e5ccde839dbaa3f4eee8af47f11e96b` | The TestClient source was not loopback-trusted; replacement explicitly uses a loopback client. |

## Vitest reds

| Vitest test | Commit | Observed red output |
|---|---|---|
| `ui/tests/component/Transactions.test.ts::renders transactions, indents savepoints, and refreshes on a stream update` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |
| `ui/tests/component/Transactions.test.ts::hides transaction controls for a read-only panel` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |
