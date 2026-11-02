# Findings: A-transactions

| Finding | Test | Red commit | Red output | Status |
|---|---|---|---|---|
| No BootUI captured golden is available in the lane worktree | `test_report_golden_parity` (Task 3) | — | — | parked until coordinator supplies fixture; nullable reason is recorded |
| Commit failure is surfaced after SQLAlchemy's pre-commit callback, but F's slot has no failure event | `test_failed_commit_is_unknown` (Task 2) | — | — | parked under O1; do not modify `engine/sqla.py` |

## Fixed test findings

| Finding | Test | Red commit | Fix commit |
|---|---|---|---|
| Recorder did not assign transaction ids or retain committed root transactions | `tests/engine/capture/test_transactions.py::test_records_committed_root` | `79a37b42dd5a345c86a08766791adef111c3121d` | pending |
| Recorder did not bound entries, maintain lifetime counts, honor pause/clear, or mask errors | `tests/engine/capture/test_transactions.py::{test_bounded_entries_report_stats,test_clear_keeps_total_captured,test_paused_records_nothing,test_error_message_is_masked,test_sql_trace_unavailable_warning}` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | pending |
