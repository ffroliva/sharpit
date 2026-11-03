# Lane R-transactions: resume the `transactions` panel from `lane/0.4.0-A-transactions` @ `666a0ab`

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `R-transactions` (worktree `C:\development\github\sharpit-wt\0.5.0-R-transactions`, branch `lane/0.5.0-R-transactions`, created by rebasing `lane/0.4.0-A-transactions` @ `666a0ab` onto `release/0.5.0`) |
| **Goal** | Close review round 2 (`VERDICT: CHANGES`) so `transactions` merges at golden parity. |
| **Spec** | §5.1; the 0.4.0 lane plan `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/A-transactions.md` (field map, interfaces, Tasks 1–6) still governs; this file lists only the resume work |
| **Review to close** | `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\lanes\A-transactions\review.md` (round 2, reviewer claude-opus-5-5) |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §2; golden `tests/fixtures/bootui/2.2.0/transactions/captured.json` (real rows) |
| **Worker** | codex gpt-6-luna (implemented the 0.4.0 lane); reviewer Opus |
| **Council** | not required |
| **Depends on** | F5b (the `sqla.py` edit lands in `engine/sqla/events.py`); R0 next: B-security-logs, D2 (`fastapi/capture.py`, `install.py`) |
| **May touch** | resolved from `git diff --name-only origin/main...666a0ab`: `src/sharpit/engine/capture/transactions.py`, `src/sharpit/engine/panels04/transactions.py`, `src/sharpit/engine/sqla/events.py` (the branch's `sqla.py` hunk: commit-failure / post-commit connection event only), `src/sharpit/engine/tools04/transactions.py`, `src/sharpit/fastapi/capture.py` (lines 46–50; review minor 7 ratified), `src/sharpit/fastapi/install.py` (`_configure_capture` only), `src/sharpit/fastapi/routes/transactions.py`, `tests/engine/capture/test_transactions.py`, `tests/fastapi/test_transactions_api.py`, `tests/fastapi/test_transactions_overhead.py`, `tests/fixtures/bootui/2.2.0/transactions/nullable.json`, `tests/masking/test_a_transactions_masking.py`, `tests/safety/test_a_transactions_safety.py`, `tests/test_foundation_round2.py` (minor 7 ratified), `ui/src/lib/panels04/transactions.ts`, `ui/src/views/Transactions.svelte`, `ui/tests/component/Transactions.test.ts`; the lane folder `.superpowers/sdd/0.5.0/lanes/R-transactions/` |
| **Must NOT touch** | `engine/sqla/` modules other than `events.py`; `engine/capture/sqltrace.py`; `settings.py`; shared UI files; other lanes' modules; existing budget constants |

## Review Focus

1. Two unnamed savepoints (SQLAlchemy 2.1 fires `savepoint(conn, None)`) never overwrite each other.
2. The ring is bounded even when every row stays open.
3. A committed row is never rewritten to `UNKNOWN` by a later non-statement `handle_error`.

Red rule: PLAN.md §Red rule. Third attempt by the same implementer: the reviewer replays round 2's majors as the named
reds below **before** reading the new code.

## Must-cover

`test_nested_unnamed_savepoint_rollback_is_rolled_back`, `test_untracked_inner_savepoint_does_not_close_tracked_outer`,
`test_ring_stays_bounded_when_every_entry_is_open`, `test_savepoint_depth_reset_after_error_and_checkin`,
`test_later_non_statement_error_does_not_rewrite_committed_row`, `test_report_golden_parity`,
`test_transactions_get_no_side_effects`, `test_error_message_masked`.

## Task 0: rebase and baseline

- [ ] **Step 1:** Rebase onto `release/0.5.0`; resolve the `sqla.py` hunk into `engine/sqla/events.py`. Record the
  mapping in `handoff.md`.
- [ ] **Step 2:** Run the lane tests + `tests/engine/test_sqla*.py tests/test_foundation_round2.py
  tests/test_safety_matrix.py tests/safety/ tests/fastapi/test_capture_wiring.py` (background). Green before any fix;
  a red here is a rebase defect, fixed first with its own finding row.

## Task 1: majors (review findings 1, 2)

**Files:** `src/sharpit/engine/capture/transactions.py`, `tests/engine/capture/test_transactions.py`.

- [ ] **Step 1:** Red commit `test: nested unnamed savepoints and an all-open ring` (real sqlite):
  - `test_nested_unnamed_savepoint_rollback_is_rolled_back` — two `begin_nested()`, inner release, outer rollback →
    outer row `ROLLED_BACK`, inner `COMMITTED` (expected failure: the second savepoint replaces the first under key
    `None`, outer row stays `OPEN`).
  - `test_untracked_inner_savepoint_does_not_close_tracked_outer` — paused while the inner begins, resumed before its
    release → outer still `OPEN` until its own end.
  - `test_ring_stays_bounded_when_every_entry_is_open` — `max_entries=3`, 30 begins, no end →
    `len(entries) <= 6` (expected failure: 30).
  - `test_evicted_open_row_counts_unknown` — the evicted open row increments `unknownCount` and `evicted`.
  - `test_savepoint_depth_reset_after_error_and_checkin` — a savepoint raises mid-way, the connection goes back to the
    pool and is checked out again: the next `begin_nested()` is depth 1 (expected failure: stale depth 2).
- [ ] **Step 2:** Savepoints keyed by a per-connection depth counter in `conn.info`, reset on the pool `checkin` and
  `reset` events (registered through the `engine/sqla/events.py` slot); open rows past capacity kept up to
  `2 × max_entries`, then the oldest evicted as `UNKNOWN`.
- [ ] **Step 3:** Green. Commit `fix: bound the transactions ring and key savepoints by depth`.

## Task 2: minors (review findings 3, 4, 5, 6, 8, 9, 10)

- [ ] **Step 1:** Red commit with one test per finding:
  - 3 `test_commit_duration_includes_dbapi_commit` — fake DBAPI whose `commit()` sleeps 50 ms → `durationMillis >= 50`.
  - 4 `test_later_non_statement_error_does_not_rewrite_committed_row` — commit, then a failing
    `get_isolation_level()` on the same connection → row stays `COMMITTED`.
  - 5 `test_transactions_capture_with_sql_trace_and_discovery_off` — `totalCaptured == 1` (expected failure: 0).
  - 6 `test_overhead_measures_production_contexts_path` — the overhead fixture's attached side routes through
    `_contexts` (assert via a counter on the production routing function), not the SQL Trace fallback.
  - 9 `test_two_attachments_one_remove_keeps_routing` — attach the same ctx twice, remove once → still routed.
  - 10 `test_conn_info_holds_no_strong_context_reference` — `weakref` to the context is dead after the context is
    dropped and `gc.collect()`, while the pooled connection lives.
  - 8 is dead code + a docstring: no test (removal only), noted in `findings.md` as `N/A — deletion`.
- [ ] **Step 2:** Fix each; finding 10 stores `weakref.ref(ctx)`. **Step 3:** Green + the overhead budget test
  (constant unchanged). Commit `fix: transactions review round 2 minors`.

## Task 3: what the 0.4.0 plan left open

- [ ] **Step 1:** 0.4.0 Tasks 3 (golden parity: `test_report_golden_parity` against `captured.json`), 5 (Svelte view),
  6 (live check) confirmed green or finished; `IMPLEMENTED = True` in `engine/panels04/transactions.py` and
  `ui/src/lib/panels04/transactions.ts`.
- [ ] **Step 2:** `test_inactive_transactions_paths_404` and `test_transactions_get_no_side_effects` (GET + stream)
  green. Commit `feat: transactions panel enabled`.

## §6.1 → task

| Item | Task |
|---|---|
| 1 golden parity + field map | 3 (field map: 0.4.0 lane plan) |
| 2 `# ported:` | carried from 0.4.0 |
| 3 safety + masking (`test_error_message_masked`) | 3, carried |
| 4 gatekeeper (`engine/sqla/events.py` only) | 0 |
| 5 overhead budget | 2 (finding 6) |
| 6 MCP read-only | carried (`test_mcp_tools_list_has_only_get`) |
| 7 Svelte view | 3 |
| 8 gates + lowest-direct + no-SQLAlchemy | 0, 3 (coordinator logs) |
| 9 live check | 3 |
| 10 handoff | every commit |

## Evidence

`.superpowers/sdd/0.5.0/lanes/R-transactions/`: `handoff.md` (rebase mapping, last green command), `findings.md`
(rows for review findings 1–10: `fixed` + red test + red SHA, `N/A — deletion` for 8, `N/A — ratified in May-touch` for 7),
`field-map.md` (copied from the 0.4.0 lane), `checklist.md`.
