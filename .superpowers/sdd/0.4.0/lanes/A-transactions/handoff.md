# Handoff: A-transactions

Implementer: Codex (GPT-6)

## Status

In progress. Started at `a766132de82c0305b5cc4a1066a8a1a24cd2745a` on `lane/0.4.0-A-transactions`; no upstream changes merged or rebased.

## Done

- Read the canonical rules, full COMMON brief, spec, global and lane plans, council amendments, and F handoff; registered as `codex-0-4-0-a-transactions`.
- Task 1 committed nullable `readOnly` reason (`d50d6b6`). Captured transaction golden absent; parity is unverified.
- Task 2 recorder committed at the next feature commit: bounded ring, DTO/stat report, masking, clear/pause, SQL Trace report-time correlation, savepoint callbacks, real SQLite listener attachment with reference-counted teardown. Targeted tests: 8 passed; targeted Ruff check and format check passed.

## Next step

Task 3: construct the recorder and register its attacher in `fastapi/install.py`, implement API/SSE and MCP/CLI tools, flip the panel flag, add route/safety/masking tests. Continue to honor the narrow May-touch list.

## Decisions

- Follow F handoff: `_configure_capture(app, ctx, settings) -> CaptureWiring`; listener arm/removal uses `CaptureState.attachers` so late SQLAlchemy imports and lifespan restarts work.
- F exposes begin/commit/rollback/savepoint events only. SQLAlchemy commit failure is surfaced after the pre-commit callback, so `test_failed_commit_is_unknown` is parked under O1. No `engine/sqla.py` edits.
- Class listeners are reference-counted across Sharpit contexts to avoid duplicate capture and premature removal.
- Live check remains out of scope because the plan forbids editing the shared example; coordinator must run it.

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/capture/test_transactions.py::test_records_committed_root` | `79a37b42dd5a345c86a08766791adef111c3121d` | `a captured transaction must receive a positive id` |
| `tests/engine/capture/test_transactions.py::test_bounded_entries_report_stats` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `the transaction ring must respect max_entries` |
| `tests/engine/capture/test_transactions.py::test_clear_keeps_total_captured` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `clear must empty the retained transactions` |
| `tests/engine/capture/test_transactions.py::test_paused_records_nothing` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `a paused recorder must return the sentinel id` |
| `tests/engine/capture/test_transactions.py::test_error_message_is_masked` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `transaction errors must not expose connection passwords` |
| `tests/engine/capture/test_transactions.py::test_sql_trace_unavailable_warning` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `missing SQL Trace must explain why statement counts are unavailable` |
| `tests/engine/capture/test_transactions.py::test_savepoint_is_a_child_entry` | `12bf8d03b4dd14c916d74e77b6d4b1bf287a198d` | `releasing a savepoint must not close its outer transaction` |

## Gates / live check

Targeted Task 2 commands passed. Full gates and live check not run yet.
