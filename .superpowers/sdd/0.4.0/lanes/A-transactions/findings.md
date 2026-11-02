# Findings: A-transactions

| Finding | Test | Red commit | Red output | Status |
|---|---|---|---|---|
| No BootUI captured golden is available in the lane worktree | `test_report_golden_parity` (Task 3) | — | — | parked until coordinator supplies fixture; nullable reason is recorded |
| A commit failure needs a slot event after SQLAlchemy's pre-commit callback | `test_failed_commit_is_unknown` (Task 2) | — | — | verify F slot; park if absent, per O1 |
