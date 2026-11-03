# R-transactions findings

Implementer: Claude subagent (claude-opus-5-5)

Review closed: `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\lanes\A-transactions\review.md`
(round 2, VERDICT: CHANGES) and `ponytail-review.md` round 2. Every red below was replayed at its red SHA in a detached
worktree with `scripts/dev/red_check.py` (log: `0.5.0-integration/.superpowers/sdd/0.5.0/logs/R-transactions-replay.log`):
all RED (assertion under tests/).

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/capture/test_transactions.py::test_nested_unnamed_savepoint_rollback_is_rolled_back | 333a91a79a88ddd338280d12e9d44aab6fab214c | a rolled-back outer savepoint must never be reported committed (review 1) | Fixed in aca8e8ad75656dc838160dc369a11cf4bac9022e |
| tests/engine/capture/test_transactions.py::test_untracked_inner_savepoint_does_not_close_tracked_outer | 333a91a79a88ddd338280d12e9d44aab6fab214c | releasing an untracked inner savepoint must not close the tracked outer one (review 1) | Fixed in aca8e8ad75656dc838160dc369a11cf4bac9022e |
| tests/engine/capture/test_transactions.py::test_ring_stays_bounded_when_every_entry_is_open | 333a91a79a88ddd338280d12e9d44aab6fab214c | open transactions must not grow the ring past twice its capacity (review 2) | Fixed in aca8e8ad75656dc838160dc369a11cf4bac9022e |
| tests/engine/capture/test_transactions.py::test_evicted_open_row_counts_unknown | 333a91a79a88ddd338280d12e9d44aab6fab214c | an open row evicted past the hard cap must be counted as evicted (review 2) | Fixed in aca8e8ad75656dc838160dc369a11cf4bac9022e |
| tests/engine/capture/test_transactions.py::test_commit_duration_includes_dbapi_commit | 1b8f5eb2cafdfc0e4d2879a077dc8ae6c7c59c42 | a committed transaction's duration must include the DBAPI commit (review 3) | Fixed in 625ca640a5cb51917cc448885b674283e1af7485 |
| tests/engine/capture/test_transactions.py::test_later_non_statement_error_does_not_rewrite_committed_row | 1b8f5eb2cafdfc0e4d2879a077dc8ae6c7c59c42 | an error after a successful commit must not rewrite the row to UNKNOWN (review 4) | Fixed in 625ca640a5cb51917cc448885b674283e1af7485 |
| tests/fastapi/test_transactions_api.py::test_transactions_capture_with_sql_trace_and_discovery_off | 1b8f5eb2cafdfc0e4d2879a077dc8ae6c7c59c42 | the only installed context must capture with SQL Trace and discovery off (review 5) | Fixed in 625ca640a5cb51917cc448885b674283e1af7485 |
| tests/engine/capture/test_transactions.py::test_two_attachments_one_remove_keeps_routing | 1b8f5eb2cafdfc0e4d2879a077dc8ae6c7c59c42 | removing one of two attachments must keep routing to the still-attached context (review 9) | Fixed in 625ca640a5cb51917cc448885b674283e1af7485 |
| tests/engine/capture/test_transactions.py::test_conn_info_holds_no_strong_context_reference | 1b8f5eb2cafdfc0e4d2879a077dc8ae6c7c59c42 | a pooled connection's info must not keep a dropped sharpit context alive (review 10) | Fixed in 625ca640a5cb51917cc448885b674283e1af7485 |
| tests/fastapi/test_transactions_api.py::test_report_golden_parity | df651a97e3bdca67fa0d98f5c995ae201f15959e | transactions/captured.json parity: entries[].isolation: null in payload, golden has string (raised in tests/golden.py) | Fixed in c94811f84b6fee07fe04a81c71e8437663076538 |

## Pins (pass on the base; mutation-proven)

| Test | Commit | Mutation (scratch, reverted) | Failure under the mutation |
|---|---|---|---|
| tests/engine/capture/test_transactions.py::test_savepoint_depth_reset_after_error_and_checkin | 333a91a79a88ddd338280d12e9d44aab6fab214c | both savepoint-frame resets (`_savepoints(...).clear()` in the root `_begin` and in `_end`) replaced by `pass` | `AssertionError: a savepoint left open by an error must not survive the connection's return to the pool` |
| tests/fastapi/test_transactions_overhead.py::test_overhead_measures_production_contexts_path | 625ca640a5cb51917cc448885b674283e1af7485 | the old helper (`teardowns.pop()()` then `attach()` without ctx) instead of `_listeners_detached()` | `AssertionError: the attached side must route through the panel's own contexts, not SQL Trace's` |
| tests/safety/test_a_transactions_safety.py::test_inactive_transactions_paths_404 | 43f00a0f4cd30465bb76cf14915f6c1266e31166 | none: the global fail-closed guard (also pinned by `tests/test_safety_matrix.py::test_inactive_is_404_everywhere`) | N/A |
| tests/engine/capture/test_transactions.py::test_clear_empties_the_buffer_without_resetting_total_captured | 213b9933eadd24c4a59bdbfeb91ab935c97d7f5c | `clear()` also sets `self._total = 0` | `AssertionError: clear must not reset totalCaptured` |

Why finding 6 is a pin, not a red: its defect lives in the test's own helper. A red test may not reference a top-level
name that changes after its red commit, so the helper fix and the test landed together and the old helper was
mutation-replayed instead.

New rules mutation-proven (scratch edit, reverted with `git checkout`):

| Rule | Mutation | Failing test |
|---|---|---|
| hard cap `2 x max_entries` on open rows | `if False:` | `test_ring_stays_bounded_when_every_entry_is_open`, `test_evicted_open_row_counts_unknown` |
| settle the commit at pool checkin | `_settle(connection_record.info)` -> `pass` | `test_commit_duration_includes_dbapi_commit` |
| only an in-transaction error fails the commit | `_settle(conn.info, error)` unconditionally | `test_later_non_statement_error_does_not_rewrite_committed_row` |

## Review round 2 findings and their disposition

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | major | unnamed savepoints share the `None` key | fixed: LIFO frames per connection (depth), always pushed; red rows above |
| 2 | major | ring unbounded when every row is open | fixed: open rows kept up to `2 x max_entries`, then the oldest evicted, counted in `evicted` and `unknownCount` |
| 3 | minor | commit duration excludes the DBAPI commit | fixed: closed COMMITTED at the commit event, re-closed (`settle`) at the first post-commit point: pool `checkin` (new `add_pool_listener` in `engine/sqla/events.py`), the next `begin`/`rollback`, or a later non-statement error |
| 4 | minor | stale pending commit rewrites a committed row | fixed: `handle_error` fails the commit only while `conn.in_transaction()` |
| 5 | minor | nothing captured with SQL Trace and discovery off | fixed: `_targets` falls back to the only attached context when SQL Trace's routing finds none |
| 6 | minor | overhead test measures the SQL Trace fallback path | fixed (pin above): `_listeners_detached()` removes and restores the production class listeners (`CONNECTION_CALLBACKS` + pool `checkin`); routing untouched |
| 7 | minor | `fastapi/capture.py` / `tests/test_foundation_round2.py` outside May-touch | N/A — ratified in May-touch |
| 8 | minor | dead `_end(name=)` branch, stale docstring | N/A — deletion (branch removed in aca8e8a; docstring fixed in the merge 4378fea) |
| 9 | minor | double attach + one remove drops routing | fixed: per-context attachment count |
| 10 | minor | `conn.info` holds strong context refs | fixed: `conn.info` holds `weakref.ref(recorder)` only |
| golden | n/a | `isolation` null vs golden string | fixed: `"UNKNOWN"`, BootUI's value when it cannot tell |
