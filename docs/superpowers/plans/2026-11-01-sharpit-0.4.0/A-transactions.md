# Lane A-transactions: the `transactions` panel (SQLAlchemy connection events)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `A-transactions` (worktree `C:\development\github\sharpit-wt\0.4.0-A-transactions`, branch `lane/0.4.0-A-transactions`) |
| **Goal** | BootUI's `TransactionReport` for every transaction the app runs on a registered engine, recorded from SQLAlchemy **connection** events with a hot path that never queries the database. |
| **Spec** | §4, §6.1–§6.3, §7 row `transactions`, §11, §15 (round 1 "Transactions via class-level Session events"; round 3 "hot-path queries; field map") |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §2; BootUI `TransactionRecorder.java` (statuses `COMMITTED`/`ROLLED_BACK`/`UNKNOWN`, propagation `NEW`/`PARTICIPATING`, warnings at `:540-552`) |
| **Worker** | M, judgement-heavy (event semantics, hot path) → codex or Opus |
| **Depends on** | F (connection-event hook slot in `sqla.py`, `implemented` flag, route module stub, settings fields, golden loader); D1 |
| **May touch** | `src/sharpit/engine/capture/transactions.py` (new), `src/sharpit/fastapi/routes/transactions.py` (F stub), the `transactions` rows F pre-registered (flag flip), the `CaptureState.transactions` slot F added, F's MCP stubs, `ui/src/views/Transactions.svelte` (+ test), `tests/engine/capture/test_transactions.py`, `tests/fastapi/test_transactions_api.py`, `tests/fastapi/test_transactions_overhead.py`, `tests/fixtures/bootui/2.2.0/transactions/*`, lane folder |
| **Must NOT touch** | §10.3 protected files (incl. **existing** budget constants: this lane adds a new budget, never edits one); `engine/sqla.py` beyond filling F's connection-event slot; `engine/capture/sqltrace.py` (A-sqlalchemy-statistics owns it); other lanes' modules |

**Architecture:** A `TransactionRecorder` in `engine/capture/transactions.py` (bounded deque + stats, like
`SqlTraceRecorder`, `engine/capture/sqltrace.py:386`) owns state. The listener functions live behind F's slot in
`engine/sqla.py`, class-level on `Engine` like the statement listeners (`sqla.py:255-281`), routed with
`dispatch.recording`'s target rule (`engine/sources/dispatch.py:68`): in a request its own context; outside, the
context whose registry holds the engine, else the only one. Per-connection state lives in `conn.info`. SQL counts are
correlated at **report** time from the SQL Trace ring (BootUI correlates on the begin thread too), never on the hot path.

## Global Constraints

- No GET or MCP tool opens a socket, runs SQL, writes a file, changes logging/`os.environ`. **The listener never
  queries the database** (spec §7): isolation and read-only are not looked up.
- Every listener catches its own errors (`dispatch.routing_failed`), never changes the host's transaction; a raising
  recorder costs one warning (`CaptureWiring.hook_failed`).
- `INTERNAL.get()` true → skip (sharpit's own reads in `run_db_read` are invisible).
- Overhead budget test, never marked slow or deselected; the budget is set once in this lane and never raised.
- Keys verbatim from `TransactionReport`/`TransactionStatsDto`/`TransactionEntryDto`; epoch ms; nulls emitted.
- `# ported: <Class>.<method>` on every ported test. Red is an assertion. PT018. Conventional commits, no attribution.

## Review Focus

1. **Savepoints and nesting.** `with session.begin_nested()` inside a request transaction, a released savepoint, a
   rolled-back savepoint followed by an outer commit. Expect a child entry with `parentId` = outer id, `propagation
   "PARTICIPATING"`, `nestedCount` 1, outer `COMMITTED`. Pinned in Task 2: `test_savepoint_is_a_child_entry`.
2. **A commit that fails** (sqlite deferred foreign key, `PRAGMA foreign_keys=ON` + `DEFERRABLE INITIALLY DEFERRED`).
   Expect `UNKNOWN` with a masked `errorMessage`, not `COMMITTED`. Pinned in Task 2: `test_failed_commit_is_unknown`.
3. **A connection returned to the pool mid-transaction / invalidated** (no commit or rollback event). Expect no leak:
   the open entry is dropped from `conn.info` on the next `begin` and counted `UNKNOWN`. Pinned in Task 2:
   `test_begin_over_open_entry_closes_it_unknown`.
4. **Async engines and threads.** `AsyncEngine` (aiosqlite) transactions fire on the greenlet; `thread` is the begin
   thread. Expect the same entry shape. Pinned in Task 3: `test_async_engine_transaction_recorded`.
5. **sharpit's own reads** (`run_db_read`, alembic refresh) never appear. Pinned in Task 3:
   `test_internal_reads_not_recorded`.

## Field map

| BootUI key | Python source |
|---|---|
| `id` | recorder counter |
| `methodName` | `call_site(None)` of the `begin` frame when `sql_trace_capture_call_site`, else `"unknown"` (BootUI's blank name) |
| `propagation` | `"NEW"` root, `"PARTICIPATING"` savepoint (BootUI constants) |
| `isolation` | `null` (never queried; DTO nullable) |
| `status` | `commit` → `COMMITTED`, `rollback` → `ROLLED_BACK`, failed commit / orphan → `UNKNOWN` |
| `startTimestamp`/`endTimestamp`/`durationMillis` | `time.time_ns()` at begin/end; hold time = begin → commit/rollback |
| `parentId` | enclosing entry id for a savepoint, else `null` |
| `thread` | `threading.current_thread().name` at begin |
| `traceId` | `REQUEST.get().id` at begin, else `null` |
| `sqlStatementCount` | report-time count of SQL Trace rows with the same `connectionId` inside `[start, end]`; `0` + BootUI warning when SQL Trace is off |
| `connectionCount` | `1` (one `Connection` per SQLAlchemy transaction) |
| `readOnly` | `null` + `nullable.json`: "SQLAlchemy does not expose read-only intent and the hot path never queries" |
| `slow` / `connectionHeld` | `durationMillis >= slow_transaction_threshold_millis` / `>= connection_hold_threshold_millis` |
| `errorMessage` | masked `handle_error` text for a failed commit, else `null` |
| stats `unknownCount`, `nestedCount`, `evicted` | recorder counters |

Settings (F adds fields; env `SHARPIT_TRANSACTIONS_*`): `transactions_enabled=True`, `transactions_recording=True`,
`transactions_max_entries=200`, `transactions_slow_transaction_threshold_millis=200`,
`transactions_connection_hold_threshold_millis=500` (contract §2).

---

### Task 1: Golden fixture and nullable keys

**Files:** `tests/fixtures/bootui/2.2.0/transactions/report.json`, `.../nullable.json`.

- [ ] **Step 1:** G0 capture (or provisional from another worker, §12.11), sanitised. `nullable.json`:
  `{"entries[].readOnly": "<reason above>"}`.
- [ ] **Step 2:** Commit `test: transactions golden fixture`.

### Task 2: `TransactionRecorder` and the event functions

**Files:** Create `src/sharpit/engine/capture/transactions.py`; fill F's slot in `src/sharpit/engine/sqla.py`; Test
`tests/engine/capture/test_transactions.py`.

**Interfaces:** Produces
- `class TransactionRecorder(masker: Masker, *, max_entries: int = 200, slow_threshold_ms: int = 200,
  hold_threshold_ms: int = 500, recording: bool = True)` with `begin(key: int, *, parent: int | None, method: str,
  thread: str, trace_id: str | None, connection_id: str | None) -> int`, `end(entry_id: int, status: str, error:
  BaseException | None = None) -> None`, `clear() -> None` (keeps `totalCaptured`), `set_recording(enabled: bool)`,
  `report(sql_rows: list[dict[str, Any]] | None) -> dict[str, Any]`, `changes: ChangeStream`.
- `unavailable_report(reason: str) -> dict[str, Any]`; constants `PAUSED = "Recording is paused. Resume it to capture
  new transactions."`, `NO_SQL_TRACE = "SQL Trace is not active, so SQL statement/connection counts are not correlated."`.
- In `sqla.py` (F's slot): `tx_begin(conn)`, `tx_commit(conn)`, `tx_rollback(conn)`, `tx_savepoint(conn, name)`,
  `tx_rollback_savepoint(conn, name, context)`, `tx_release_savepoint(conn, name, context)`; state in
  `conn.info["sharpit_tx"]: list[tuple[SharpitContext, int]]` (a stack). A failed commit is seen in the existing
  `handle_error` (`sqla.py:241`) when `exception_context.statement is None` and the stack is non-empty.

- [ ] **Step 1:** Stub; tests against a real sqlite engine with the listeners attached:
  - `test_records_committed_root` (`# ported: TransactionRecorderTests.recordsACommittedRootTransaction`)
  - `test_records_rolled_back` (`# ported: TransactionRecorderTests.recordsARolledBackTransactionWithErrorMessage`)
  - `test_savepoint_is_a_child_entry` (`# ported: TransactionRecorderTests.tracksParentChildNestingOnTheSameThread`)
  - `test_failed_commit_is_unknown` (`# ported: BootUiTransactionExecutionListenerTests.recordsUnknownStatusWhenCommitFails`)
  - `test_begin_over_open_entry_closes_it_unknown` (`# derived: pool return without end event`)
  - `test_evicts_oldest` (`# ported: TransactionRecorderTests.evictsOldestEntryOnceBufferIsFull`): `evicted == 1`
  - `test_flags_slow_and_held` (`# ported: TransactionRecorderTests.flagsSlowAndConnectionHeldTransactions`)
  - `test_clear_keeps_total` (`# ported: TransactionRecorderTests.clearEmptiesTheBufferWithoutResettingTotalCaptured`)
  - `test_paused_records_nothing` (`# ported: TransactionRecorderTests.beginTransactionReturnsSentinelWhenPaused`)
  - `test_unknown_end_ignored` (`# ported: TransactionRecorderTests.completeTransactionIgnoresSentinelAndUnknownIds`)
  - `test_subscriber_signalled` (`# ported: TransactionRecorderTests.subscribeIsNotifiedOnCompletionClearAndRecordingToggle`)
  - `test_sql_counts_correlated` (`# ported: TransactionRecorderTests.correlatesCompletedTransactionToSqlTraceExecutionsOnTheSameThread`)
  - `test_no_sql_trace_warning` (`# ported: TransactionRecorderTests.reportReflectsUnavailableSqlTraceCorrelationWarning`)
  - `test_listener_raising_recorder_is_swallowed` (`# ported: BootUiTransactionExecutionListenerTests.failsOpenWhenRecorderThrowsOnBegin`)
  - `test_listener_never_executes_sql` — `before_cursor_execute` spy counts zero statements issued during
    `tx_begin`/`tx_commit`.
- [ ] **Step 2:** FAIL on assertions. **Step 3:** Implement. `report()` key order = `TransactionReport`.
- [ ] **Step 4:** PASS. Commit `feat: transaction recorder over connection events`.

### Task 3: Wiring, routes, MCP, safety

**Files:** `src/sharpit/fastapi/routes/transactions.py` (F stub); the recorder construction in F's per-panel capture
setup (where `SqlTraceRecorder` is built, `fastapi/adapter.py:744` before F's split); flag flip; Tests
`tests/fastapi/test_transactions_api.py`, rows in `tests/test_safety_matrix.py`.

**Interfaces:** `GET {api}/transactions`, `POST {api}/transactions/clear`, `POST {api}/transactions/recording` (body
`{"enabled": bool|null}`; null/absent toggles — `TransactionsControllerSupportTests.recordingTogglesWhenNoExplicitValueIsGiven`),
`GET {api}/transactions/stream` (SSE `update`, reuse `sse_response` + `change_events`). MCP read tool
`get_transactions`; `clear_transactions`, `pause_transaction_recording`, `resume_transaction_recording` registered with
`action=True` (CLI-only, §6.1.6). Panel `actionCapable=True`.

- [ ] **Step 1:** Tests: `test_report_golden_parity`; `test_unavailable_without_recorder`
  (`# ported: TransactionsControllerSupportTests.traceReportsUnavailableWhenRecorderIsAbsent`);
  `test_unavailable_when_disabled` (`...WhenRecorderIsDisabled`); `test_clear` (`...clearEmptiesTheBuffer`);
  `test_recording_toggle` / `test_recording_explicit` (`...recordingTogglesWhenNoExplicitValueIsGiven`,
  `...recordingSetsExplicitValueWhenGiven`); `test_read_only_blocks_post` (403 `read_only_reason`);
  `test_get_no_side_effects` (`no_side_effects`, GET and stream); `test_mcp_tools_list_has_only_get`;
  `test_async_engine_transaction_recorded`; `test_internal_reads_not_recorded` (alembic refresh → 0 entries);
  `test_uninstall_capture_removes_listeners` (`sqla.attached()` false for the tx events).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS + full gate (background). Commit
  `feat: transactions panel routes, stream and MCP read tool`.

### Task 4: Overhead budget

**Files:** Create `tests/fastapi/test_transactions_overhead.py`.

- [ ] **Step 1:** Paired on/off with `tests/overhead.py::paired` and `check_budget`, as
  `tests/fastapi/test_sql_trace_overhead.py:45`: `BUDGET_NS = 30_000` per begin+commit pair (sqlite in-memory).
  Record the measured value and noise in `checklist.md`. Prove it bites: temporarily add a `time.sleep(0.0001)` in
  `tx_begin`, see FAIL, remove.
- [ ] **Step 2:** Commit `test: transactions hot-path overhead budget`.

### Task 5: Svelte view

**Files:** `ui/src/views/Transactions.svelte`, `ui/src/views/Transactions.test.ts`.

- [ ] **Step 1:** vitest: table from the golden; parent/child indentation by `parentId`; `null` `readOnly` shows "—";
  pause/resume/clear buttons hidden when `readOnly`; stream `update` triggers a refetch. Reference `views/Transactions.vue`.
- [ ] **Step 2:** FAIL → implement → `npm --prefix ui run check` + tests PASS. Commit `feat: transactions view`.

### Task 6: Live check and evidence

- [ ] **Step 1:** `/sharpit:live-verify` on `examples/fastapi_sqla` (a write route produces a `COMMITTED` row; a forced
  error route a `ROLLED_BACK` row); tiny-ledger-py deposits when available. Record in `live-verify.md`.
- [ ] **Step 2:** lowest-direct + no-SQLAlchemy logs with head SHA. Commit `docs: transactions lane evidence`.

## §6.1 → task

| Item | Task |
|---|---|
| 1 parity, nullable, field map | 1, 3 `test_report_golden_parity`, field map |
| 2 ported citations | 2, 3 |
| 3 safety (no_side_effects, PANELS, flags, guard, masking: `errorMessage` via `ctx.masker.mask_text`, test `test_error_message_masked` in Task 2 with a password in the DSN text) | 2, 3 |
| 4 gatekeeper (listeners only in `sqla.py`) | 2 |
| 5 overhead budget | 4 |
| 6 MCP read-only | 3 |
| 7 Svelte | 5 |
| 8 gates + lowest-direct + no-SQLAlchemy | 3, 6 |
| 9 live check | 6 |
| 10 handoff | every commit |

## Lane evidence checklist (`.superpowers/sdd/0.4.0/lanes/A-transactions/`)

`handoff.md` · `field-map.md` · `checklist.md` (incl. measured overhead) · `findings.md` · `review.md` (`VERDICT: APPROVE`,
reviewer ≠ implementer, head SHA; `ponytail-review` too, since it touches `sqla.py`) · `gate/` (four gates, lowest-direct, no-SQLAlchemy logs, each naming the head SHA) ·
`live-verify.md`.
