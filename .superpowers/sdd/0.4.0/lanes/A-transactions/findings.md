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
| `tests/engine/capture/test_transactions.py::test_listener_remover_releases_attachments_when_discarded` | `6faa15c5a22c5773f87590ddb403e0c89ee2f587` | Replaced GC-owned listener lifetime with explicit CaptureState teardown per R17; test now verifies explicit remover behavior. |

## Round 1 review reds

| Test | Red SHA | Assertion | Disposition |
|---|---|---|---|
| `tests/engine/capture/test_transactions.py::test_listener_release_never_runs_under_attach_lock` | `b9bb0a3651df951caecb6da77f2526ee2a77aa29` | `listener release must not block while the attach lock is held` | Fixed in `85fbff9fe8ba8e242b63a2952e6750ecfd7d0083` |
| `tests/engine/capture/test_transactions.py::test_untracked_savepoint_end_does_not_close_root` | `2bf97fc036ea23f977da8766a24e3da5fdaf702b` | `an untracked savepoint release must not close the root transaction` | Fixed in `df3ae12e86ae16163ed5d557b9b157960eff4fd2` |
| `tests/engine/capture/test_transactions.py::test_buffer_size_reports_capacity_when_empty` | `2e716bd859752f6cb6b57c764332cc20f43091de` | `bufferSize must report the configured ring capacity` | Fixed in `42604e9ceb04cf4b7aea3ff27057e068e3411315` |
| `tests/fastapi/test_transactions_api.py::test_transactions_alone_does_not_install_capture_middleware` | `7c52759e30828b9b3f34d2864647ac7c572c03b1` | `transactions alone must not add request capture middleware` | Fixed in `3f988275370502a79441e92b0eb59e754c20a615` |
| `tests/engine/capture/test_transactions.py::test_flags_slow_and_held` | `ea437338f777d67fdbc2066b4fe88244a55b6d6a` | `a zero slow threshold must disable slow transaction flags` | Fixed in `pending transactions safety fix` |
| `tests/engine/capture/test_transactions.py::test_begin_over_open_entry_closes_it_unknown` | `ea437338f777d67fdbc2066b4fe88244a55b6d6a` | `an in-flight transaction must be reported as open` | Fixed in `pending transactions safety fix` |
| `tests/engine/capture/test_transactions.py::test_oldest_open_entry_is_not_evicted` | `ea437338f777d67fdbc2066b4fe88244a55b6d6a` | `the oldest open transaction must remain retained` | Fixed in `pending transactions safety fix` |
| `tests/fastapi/test_transactions_api.py::test_recording_post_recursion_error_returns_400` | `ec8ce4cd7841b9c78293977f957c5b6bf54b24e9` | `a recursively nested toggle body must be rejected with 400` | Fixed in `pending transactions safety fix` |
| `tests/fastapi/test_transactions_api.py::test_transactions_capture_when_sql_trace_is_disabled` | `fa717b7fc3eb3bdf5da34567832e577084cf33a1` | `transactions must capture connection events while SQL Trace is off` | Fixed in `pending transactions safety fix` |

## Vitest reds

| Vitest test | Commit | Observed red output |
|---|---|---|
| `ui/tests/component/Transactions.test.ts::renders transactions, indents savepoints, and refreshes on a stream update` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |
| `ui/tests/component/Transactions.test.ts::hides transaction controls for a read-only panel` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |
