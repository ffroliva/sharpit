# Handoff: A-transactions

Implementer: Codex (GPT-6)

## Status

In progress. Started at `a766132de82c0305b5cc4a1066a8a1a24cd2745a` on `lane/0.4.0-A-transactions`; no upstream changes merged or rebased.

## Done

- Read the canonical rules, full COMMON brief, spec, global and lane plans, council amendments, and F handoff.
- Registered with agentctl as `codex-0-4-0-a-transactions`.
- Task 1 nullable field fixture committed (`d50d6b6`). The captured transaction golden is absent in this worktree, so parity remains unverified.
- Task 2 assertion reds committed; implementing the framework-free recorder next.

## Next step

Implement Task 2 in `engine/capture/transactions.py`, verify each red test turns green, then add event listener, wiring, routes and UI within the plan's May-touch list. Full suite log must stay outside this worktree and xdist is capped at 4.

## Decisions

- Follow F handoff: `_configure_capture(app, ctx, settings) -> CaptureWiring`; listener arm/removal belongs in `CaptureState.attachers` so late SQLAlchemy imports and lifespan restarts are handled.
- F exposes only begin/commit/rollback/savepoint event hooks. SQLAlchemy commit failure is surfaced after the `commit` event via `handle_error`, so `test_failed_commit_is_unknown` is parked under O1 unless a later slot interface supports it.
- Never modify `engine/sqla.py`.

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/capture/test_transactions.py::test_records_committed_root` | `79a37b42dd5a345c86a08766791adef111c3121d` | `a captured transaction must receive a positive id` |
| `tests/engine/capture/test_transactions.py::test_bounded_entries_report_stats` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `the transaction ring must respect max_entries` |
| `tests/engine/capture/test_transactions.py::test_clear_keeps_total_captured` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `clear must empty the retained transactions` |
| `tests/engine/capture/test_transactions.py::test_paused_records_nothing` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `a paused recorder must return the sentinel id` |
| `tests/engine/capture/test_transactions.py::test_error_message_is_masked` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `transaction errors must not expose connection passwords` |
| `tests/engine/capture/test_transactions.py::test_sql_trace_unavailable_warning` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `missing SQL Trace must explain why statement counts are unavailable` |

## Gates / live check

Not run yet. Live check not run; example app wiring is out of lane touch scope.
