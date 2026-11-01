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
| **Depends on** | F (PLAN.md). Consumes F's F1a table (`F-foundation.md`): the connection-event slot in `sqla.py`, `CaptureState.transactions`, the `implemented` flag, `fastapi/routes/transactions.py`, settings fields, the MCP stub module, `tests/golden.py::assert_parity`, the `ui/src/views/Transactions.svelte` placeholder, the `tests/safety/` + `tests/masking/` helpers |
| **May touch** | `src/sharpit/engine/capture/transactions.py` (new), `src/sharpit/fastapi/routes/transactions.py` (F stub), the `transactions` rows F pre-registered (flag flip), the `CaptureState.transactions` slot F added, F's MCP stubs, `ui/src/views/Transactions.svelte` (replace F's placeholder) + `Transactions.test.ts`, `tests/engine/capture/test_transactions.py`, `tests/fastapi/test_transactions_api.py`, `tests/fastapi/test_transactions_overhead.py`, `tests/safety/test_a_transactions_safety.py`, `tests/masking/test_a_transactions_masking.py`, `tests/fixtures/bootui/2.2.0/transactions/*`, the implementer files in the lane folder (C2) |
| **Must NOT touch** | §10.3 protected files (incl. **existing** budget constants: this lane adds a new budget, never edits one); `engine/sqla.py` beyond filling F's connection-event slot; `engine/capture/sqltrace.py` (A-sqlalchemy-statistics owns it); other lanes' modules; `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (C5); any `review.md` or `gate/` path |

**Architecture:** A `TransactionRecorder` in `engine/capture/transactions.py` (bounded deque + stats, like
`SqlTraceRecorder`, `engine/capture/sqltrace.py:386`) owns state. The listener functions live behind F's slot in
`engine/sqla.py`, class-level on `Engine` like the statement listeners (`_LISTENERS`/`_sync_listeners`, `sqla.py:255-281`), routed
with `dispatch.recording`'s target rule (`dispatch._targets`, `engine/sources/dispatch.py:68`; `recording` at `:82`): in a request its own context; outside, the
context whose registry holds the engine, else the only one. Per-connection state lives in `conn.info`. SQL counts are
correlated at **report** time from the SQL Trace ring (BootUI correlates on the begin thread too), never on the hot path.

## Global Constraints

- No GET or MCP tool opens a socket, runs SQL, writes a file, changes logging/`os.environ`. **The listener never
  queries the database** (spec §7): isolation and read-only are not looked up.
- Every listener catches its own errors (`dispatch.routing_failed`, `engine/sources/dispatch.py:53`), never changes the
  host's transaction; a raising recorder costs one warning (`CaptureWiring.hook_failed`, `fastapi/capture.py:276`; the
  `CaptureHooks` port at `engine/capture/__init__.py:22`), as `sqla._context_failed` does.
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

- [ ] **Step 1:** G0a capture (or provisional from another worker, §12.11), sanitised, at
  `tests/fixtures/bootui/2.2.0/transactions/report.json` (C3; no flat file). `nullable.json`:
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
  - `test_error_message_masked` (`# derived: secret source errorMessage`) — a failed commit whose error text holds a
    DSN password; `errorMessage` is `ctx.masker.mask_text` output. Its corpus row goes in
    `tests/masking/test_a_transactions_masking.py` (C5).
- [ ] **Step 2:** FAIL on assertions. **Step 3:** Implement. `report()` key order = `TransactionReport`.
- [ ] **Step 4:** PASS. Commit `feat: transaction recorder over connection events`.

### Task 3: Wiring, routes, MCP, safety

**Files:** `src/sharpit/fastapi/routes/transactions.py` (F stub); the recorder construction in F's per-panel capture
setup (where `SqlTraceRecorder` is built, `fastapi/adapter.py:745` before F's split; its post-split home is in F's F1a
table) assigned to `CaptureState.transactions`; flag flip; Tests `tests/fastapi/test_transactions_api.py`,
`tests/safety/test_a_transactions_safety.py` (C5).

**Interfaces:** `GET {api}/transactions`, `POST {api}/transactions/clear`, `POST {api}/transactions/recording` (body
`{"enabled": bool|null}`; null/absent toggles — `TransactionsControllerSupportTests.recordingTogglesWhenNoExplicitValueIsGiven`),
`GET {api}/transactions/stream` (SSE `update`, reuse `fastapi/sse.py:72::sse_response` +
`engine/capture/streams.py:221::change_events`). MCP read tool
`get_transactions`; `clear_transactions`, `pause_transaction_recording`, `resume_transaction_recording` registered with
`action=True` (CLI-only, §6.1.6). Panel `actionCapable=True`.

- [ ] **Step 1:** Tests: `test_report_golden_parity` (`assert_parity("transactions", "report", body)`); `test_unavailable_without_recorder`
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

- [ ] **Step 1:** Paired on/off with `tests/overhead.py::paired` (`:65`) and `check_budget` (`:38`), as
  `tests/fastapi/test_sql_trace_overhead.py:61-66` (its own `BUDGET_NS = 50_000` at `:25` is untouched):
  `BUDGET_NS = 30_000` per begin+commit pair (sqlite in-memory), a new constant in the new file.
  Record the measured value and noise in `checklist.md`. Prove it bites: temporarily add a `time.sleep(0.0001)` in
  `tx_begin`, see FAIL, remove.
- [ ] **Step 2:** Commit `test: transactions hot-path overhead budget`.

### Task 5: Svelte view

**Files:** `ui/src/views/Transactions.svelte`, `ui/src/views/Transactions.test.ts`.

- [ ] **Step 1:** Replace F's placeholder view; flip the `transactions` `implemented` flag in F's `ui/src/lib/nav.ts`
  wiring (flag only). vitest: table from the golden; parent/child indentation by `parentId`; `null` `readOnly` shows "—";
  pause/resume/clear buttons hidden when `readOnly`; stream `update` triggers a refetch. Reference `views/Transactions.vue`.
- [ ] **Step 2:** FAIL → implement → `npm --prefix ui run check` + tests PASS. Commit `feat: transactions view`.

### Task 6: Live check and evidence

- [ ] **Step 1:** `/sharpit:live-verify` on `examples/fastapi_sqla` (a write route produces a `COMMITTED` row; a forced
  error route a `ROLLED_BACK` row); tiny-ledger-py deposits when available. Record requests in `handoff.md` §Live
  check (`live-verify.md` is the coordinator's, C2).
- [ ] **Step 2:** lowest-direct + no-SQLAlchemy as a local pre-check (commands in `checklist.md` item 8; gated logs are
  the coordinator's). Commit `docs: transactions lane evidence`.

## §6.1 → task (spec order; `checklist.md` adds the evidence paths)

| Item | Task |
|---|---|
| 1 golden parity, `nullable.json`, field map | 1, 3 `test_report_golden_parity`, field map |
| 2 `# ported:` citations | 2, 3 |
| 3 safety (`no_side_effects`, `PANELS`, flags, guard, masking: `errorMessage` via `ctx.masker.mask_text`, `test_error_message_masked` in Task 2 + `tests/masking/test_a_transactions_masking.py`) | 2, 3 |
| 4 gatekeeper (listeners only in `sqla.py`) | 2 |
| 5 overhead budget | 4 |
| 6 MCP read-only | 3 |
| 7 Svelte view | 5 |
| 8 four gates + lowest-direct + no-SQLAlchemy | 3, 6 (gated logs: coordinator) |
| 9 live check | 6 |
| 10 handoff current | every commit |

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/A-transactions/`)

- **Implementer, in the lane worktree:** `handoff.md` (last green command, next step, open findings, live-check
  requests), `findings.md` (`finding → test → red output`, each row `fixed` + red-test name or `parked` + reason),
  `field-map.md` (the field map above), `checklist.md` (the ten §6.1 items above in the spec's order, each with an evidence
  path or `N/A` + reason). `checklist.md` item 5 records the measured overhead and noise. Review includes `ponytail-review` (touches `sqla.py`).
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`, reviewer id ≠
  implementer id, head SHA), `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path (`lane_gate.py` refuses it).
