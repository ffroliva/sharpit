# Handoff: A-transactions

Implementer: codex gpt-6-luna

## Status

DONE_WITH_CONCERNS. Round 2 started at `b0206c85099a408ae8063e2649d94c4e94240cef` on `lane/0.4.0-A-transactions`.

## Done

- Read the required rules/spec/plans/F handoff and registered with agentctl (`codex-0-4-0-a-transactions`).
- Task 1 nullable `readOnly` reason fixture committed (`d50d6b6`). The captured BootUI golden is absent; parity remains unverified.
- Task 2 recorder, event callbacks, REST/SSE routes, recorder wiring, MCP/CLI tools, flag, UI view, and overhead budget are committed.
- Listener teardown now uses explicit `CaptureState.teardowns`; this review round removes GC-driven finalizer behavior.
- Repo Ruff check and format passed. Pyright returned 0 errors. Latest lane-targeted run: 23 passed, including the 30 µs listener budget. Latest measured overhead was 11.185 µs with 17.993 µs noise. The 100 µs delay control failed at 643.573 µs and was removed.
- UI Vitest passed 2/2; `npm --prefix ui run check` exited 0.

## Next step

Round 2 complete. Failed-commit red `80e02d54634909939028cde4a51bf4f4ef044273`, fix `cbf5ca11364afdb007f1bd651fbf84fa50ffca530`. The `test_clear_keeps_total_captured` test was deleted because its `bufferSize == 0` assertion pins the superseded meaning; the configured-capacity test remains. Coordinator ruling O1 permits only an additive `handle_error` event slot change in `engine/sqla.py`.

## Decisions

- F handoff API is `_configure_capture(app, ctx, settings) -> CaptureWiring`; the listener attacher returns `None` before SQLAlchemy is imported, and `CaptureState.attachers` retries it on startup/first request.
- Connection listeners are class-level and reference-counted. Dropping the owning teardown releases them; explicit uninstall releases immediately.
- SQLAlchemy's commit event is pre-DBAPI. The additive `handle_error` event revises the just-finalized transaction to `UNKNOWN` and extends its duration through a failed DBAPI commit.
- Savepoint callbacks close one nested entry per target context. SQL counts are correlated from SQL Trace at report time.

## Real pytest red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/capture/test_transactions.py::test_listener_release_never_runs_under_attach_lock` | `b9bb0a3651df951caecb6da77f2526ee2a77aa29` | `listener release must not block while the attach lock is held` |
| `tests/engine/capture/test_transactions.py::test_untracked_savepoint_end_does_not_close_root` | `2bf97fc036ea23f977da8766a24e3da5fdaf702b` | `an untracked savepoint release must not close the root transaction` |
| `tests/engine/capture/test_transactions.py::test_buffer_size_reports_capacity_when_empty` | `2e716bd859752f6cb6b57c764332cc20f43091de` | `bufferSize must report the configured ring capacity` |
| `tests/fastapi/test_transactions_api.py::test_transactions_alone_does_not_install_capture_middleware` | `7c52759e30828b9b3f34d2864647ac7c572c03b1` | `transactions alone must not add request capture middleware` |
| `tests/engine/capture/test_transactions.py::test_flags_slow_and_held` | `ea437338f777d67fdbc2066b4fe88244a55b6d6a` | `a zero slow threshold must disable slow transaction flags` |
| `tests/engine/capture/test_transactions.py::test_begin_over_open_entry_closes_it_unknown` | `ea437338f777d67fdbc2066b4fe88244a55b6d6a` | `an in-flight transaction must be reported as open` |
| `tests/engine/capture/test_transactions.py::test_oldest_open_entry_is_not_evicted` | `ea437338f777d67fdbc2066b4fe88244a55b6d6a` | `the oldest open transaction must remain retained` |
| `tests/fastapi/test_transactions_api.py::test_recording_post_recursion_error_returns_400` | `ec8ce4cd7841b9c78293977f957c5b6bf54b24e9` | `a recursively nested toggle body must be rejected with 400` |
| `tests/fastapi/test_transactions_api.py::test_transactions_capture_when_sql_trace_is_disabled` | `fa717b7fc3eb3bdf5da34567832e577084cf33a1` | `transactions must capture connection events while SQL Trace is off` |
| `tests/engine/capture/test_transactions.py::test_failed_commit_is_unknown_with_masked_error_and_commit_duration` | `80e02d54634909939028cde4a51bf4f4ef044273` | `a failed DBAPI commit must never be reported as committed` |
| `tests/engine/capture/test_transactions.py::test_listener_release_never_runs_under_attach_lock` | `b9bb0a3651df951caecb6da77f2526ee2a77aa29` | `listener release must not block while the attach lock is held` |
| `tests/engine/capture/test_transactions.py::test_records_committed_root` | `79a37b42dd5a345c86a08766791adef111c3121d` | `a captured transaction must receive a positive id` |
| `tests/engine/capture/test_transactions.py::test_bounded_entries_report_stats` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `the transaction ring must respect max_entries` |
| `tests/engine/capture/test_transactions.py::test_paused_records_nothing` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `a paused recorder must return the sentinel id` |
| `tests/engine/capture/test_transactions.py::test_error_message_is_masked` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `transaction error messages must not expose connection passwords` |
| `tests/engine/capture/test_transactions.py::test_sql_trace_unavailable_warning` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | `missing SQL Trace must explain why statement counts are not correlated` |
| `tests/engine/capture/test_transactions.py::test_savepoint_is_a_child_entry` | `12bf8d03b4dd14c916d74e77b6d4b1bf287a198d` | `releasing a savepoint must not close its outer transaction` |
| `tests/engine/capture/test_transactions.py::test_savepoint_closes_one_child_per_context` | `41964581198fd775bd63e5b3d9559c87d28eeaf0` | `a savepoint event must close its child entry in each context` |
| `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_committed_sqlite_with_loopback_client` | `5212a0865ee4ca430b56b4ef5eaf344ccf18f3f5` | `the implemented transactions panel must expose its GET report route` |

## UI reds

| Vitest test | Commit | Observed red output |
|---|---|---|
| `ui/tests/component/Transactions.test.ts::renders transactions, indents savepoints, and refreshes on a stream update` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |
| `ui/tests/component/Transactions.test.ts::hides transaction controls for a read-only panel` | `46af71a7bfd9cffe2df3cabd8d8564aa7e051035` | `Expected: orders:create; Received: transactionsThis panel's view is not built yet.` |

## Historical SHA

| Test id | Historical SHA | Why superseded |
|---|---|---|
| `tests/fastapi/test_transactions_api.py::test_transaction_route_reports_a_committed_sqlite_transaction` | `4723cd4f6e5ccde839dbaa3f4eee8af47f11e96b` | The TestClient source was not loopback-trusted; replacement explicitly uses a loopback client. |
| `tests/engine/capture/test_transactions.py::test_listener_remover_releases_attachments_when_discarded` | `6faa15c5a22c5773f87590ddb403e0c89ee2f587` | Replaced GC-owned cleanup with explicit capture teardown to avoid finalizers acquiring host locks. |
| `tests/engine/capture/test_transactions.py::test_clear_keeps_total_captured` | `a099754552f9d66f29d7e5e45a60e28d5fc14d47` | Deleted because its `bufferSize == 0` assertion contradicts the configured ring-capacity contract; capacity coverage remains. |

## Remaining constraints

- Commit failure finalization is covered by the new red/fix test and additive `handle_error` slot event.
- The historical clear test was removed; the capacity test continues to pin configured ring capacity.
- G0a's captured transaction fixture is present, but the lane has no report-golden parity assertion; coordinator should verify parity before integration.
- `CAPTURE_PANELS` no longer includes `transactions`; `tests/test_foundation_round2.py` now covers only request-capture panels, while the lane API test pins transaction-only installs to no middleware.
- The overhead test removes its own attacher and ensures the class event callbacks are detached for the off side even when a different test left an attachment reference active in the worker.
- The coordinator owns live verification and the lowest-direct/no-SQLAlchemy gate logs.

## Final gate results

- Failed-commit red `80e02d54634909939028cde4a51bf4f4ef044273` failed with the intended `AssertionError`; fix `cbf5ca11364afdb007f1bd651fbf84fa50ffca530` makes it pass. The test covers `UNKNOWN`, masked error text, and duration through the DBAPI commit.
- Targeted lane tests: 36 passed. Safety matrix, lane sweeps, surface flags, and SQLAlchemy tests: 1,077 passed, 3 skipped. Log: `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/A-transactions-round2-safety-final.log`.
- `uv run ruff check`: passed. `uv run ruff format --check`: passed (468 files). `uv run pyright`: 0 errors, 0 warnings.
- Full detached suite (`-n 4`): 4,188 passed, 9 skipped, 43 warnings. Log: `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/A-transactions-round2-full.log`.
- The safety exports are present in `tests/safety/test_a_transactions_safety.py`; GET rows cover report and stream, WRITE rows cover clear and recording.
- The coordinator still owns merged-golden parity, lowest-direct/no-SQLAlchemy checks, and live verification.

