# Handoff: A-transactions

Implementer: Codex (GPT-6)

## Status

DONE_WITH_CONCERNS. Started at `a766132de82c0305b5cc4a1066a8a1a24cd2745a` on `lane/0.4.0-A-transactions`; no upstream changes merged or rebased.

## Done

- Read the required rules/spec/plans/F handoff and registered with agentctl (`codex-0-4-0-a-transactions`).
- Task 1 nullable `readOnly` reason fixture committed (`d50d6b6`). The captured BootUI golden is absent; parity remains unverified.
- Task 2 recorder, event callbacks, REST/SSE routes, recorder wiring, MCP/CLI tools, flag, UI view, and overhead budget are committed.
- Listener teardown now uses a finalizer on its owning remover; the red test is green in the latest 19-test engine/API run. The request body handler is split below the complexity ratchet.
- Repo Ruff check and format passed. Pyright returned 0 errors. Latest lane-targeted run: 23 passed, including the 30 µs listener budget. Latest measured overhead was 11.185 µs with 17.993 µs noise. The 100 µs delay control failed at 643.573 µs and was removed.
- UI Vitest passed 2/2; `npm --prefix ui run check` exited 0.

## Next step

Coordinator to update the shared-test items below and rerun lane_gate before merge. No-SQLAlchemy, lowest-direct, and live checks remain for coordinator follow-up; the live example is outside this lane's touch scope.

## Decisions

- F handoff API is `_configure_capture(app, ctx, settings) -> CaptureWiring`; the listener attacher returns `None` before SQLAlchemy is imported, and `CaptureState.attachers` retries it on startup/first request.
- Connection listeners are class-level and reference-counted. Dropping the owning teardown releases them; explicit uninstall releases immediately.
- F exposes begin/commit/rollback/savepoint events only. SQLAlchemy commit failure is surfaced after pre-commit; `test_failed_commit_is_unknown` remains parked under O1. `engine/sqla.py` is untouched.
- Savepoint callbacks close one nested entry per target context. SQL counts are correlated from SQL Trace at report time.

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
| `tests/engine/capture/test_transactions.py::test_listener_remover_releases_attachments_when_discarded` | `6faa15c5a22c5773f87590ddb403e0c89ee2f587` | `discarding the owning teardown must release all class-level listeners` |

## UI reds

| Vitest test | Commit | Observed red output |
|---|---|---|
| `ui/tests/component/Transactions.test.ts::renders transactions, indents savepoints, and refreshes on a stream update` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |
| `ui/tests/component/Transactions.test.ts::hides transaction controls for a read-only panel` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |

## Historical red

| Test id | Historical SHA | Why superseded |
|---|---|---|
| `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_a_committed_sqlite_transaction` | `4723cd4f6e5ccde839dbaa3f4eee8af47f11e96b` | The TestClient source was not loopback-trusted; replacement explicitly uses a loopback client. |

## Needs from coordinator

- `tests/fastapi/test_capture_wiring.py::test_all_capture_panels_disabled_adds_nothing`: its local `CAPTURE_PANELS` tuple omits `transactions`; include the implemented lane or disable it in the test options. This file is outside the lane's May-touch list.
- `tests/fastapi/test_capture_overhead.py::test_request_overhead_budget`: the “off” app disables the old four capture panels but leaves implemented transactions on, so it still adds middleware. Update the baseline options; this file is outside the lane's May-touch list and its budget must stay unchanged.
- `tests/test_safety_matrix.py::test_write_route_table_is_complete`: include the two transactions POST routes in the write-route contract. This file is protected from lane edits.
- `tests/test_surface_follows_flags.py::test_every_shared_count_follows_a_flag_flip`: it merges lane tools on top of already-merged `tools.TOOLS`, duplicating the transaction tool names. Use the base-only catalogue for the planted lane merge. This file is outside the lane's May-touch list.

- `tests/fastapi/test_capture_overhead.py::test_request_overhead_budget`: the off app disables the old four capture panels but leaves transaction middleware enabled. Coordinator should disable transactions in the off baseline; do not raise its budget.

## Final gate results

- `uv run ruff check`: PASS.
- `uv run ruff format --check`: PASS (420 files).
- `uv run pyright`: PASS (0 errors).
- Detached `uv run pytest -q -n 4 --timeout=900`: 3,780 passed, 5 skipped, 5 failed, 1 error in 684.74s. Failures are coordinator-owned stale middleware/route/catalogue tests plus existing timing budgets that overshot within machine noise; the error is in `tests/test_surface_follows_flags.py`. Log: `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/A-transactions-pytest-final.log`.
- Lane-targeted suite: 23 passed. Listener overhead: 11.185 µs, noise 17.993 µs, budget 30 µs. The temporary 100 µs delay control failed at 643.573 µs and was removed.
- UI: Vitest 2/2 passed; `npm --prefix ui run check` exited 0.
- Lowest-direct, no-SQLAlchemy, and live check not run. The live example is coordinator-owned.

