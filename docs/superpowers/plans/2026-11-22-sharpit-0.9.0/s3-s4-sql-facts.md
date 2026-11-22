# S3 and S4: SQL Trace Availability and Connection Facts Implementation Plan

**Goal:** Port BootUI `v2.5.0`'s SQL Trace availability gate (`recorder.hasWrappedDataSource()`) to SQLAlchemy's class-level listener and engine-registry lifecycle (S3), close the #185 recorded-SQL edge case when a SQLAlchemy listener attachment fails with an engine registered (S4a), and derive `ConnectionPayload.statements` at connection check-in without adding work to the per-statement listener hot path (S4b).

**Architecture:** `src/sharpit/engine/sqla/` remains the single SQLAlchemy gatekeeper; `src/sharpit/engine/capture/sqltrace.py` and `src/sharpit/engine/capture/journal.py` expose read-only check-in cursors and tail counters so `src/sharpit/engine/sqla/connections.py` derives statement counts only at pool `checkout`/`checkin` boundaries (`0.00 µs` added per statement).

**Tech Stack:** Python `>=3.12`, SQLAlchemy `>=2.0` (optional, behind `src/sharpit/engine/sqla/`), `pytest`, `ruff`, `pyright`.

**Reference:** BootUI `v2.5.0` (`C:\development\github\boot-ui`), `docs/reports/2026-11-13-0.6.0-decisions.md` (decisions 3–5, lines 30–46), `docs/superpowers/plans/2026-11-22-sharpit-0.9.0/PLAN.md` (Track S), and `docs/superpowers/plans/2026-11-22-sharpit-0.9.0/s0-sql-listener-profile.md`.

**Predict verdict:** GO, 9/10 — no safety-model rule weakened; SQL capture fails closed to unrecorded/unavailable when listener attachment fails, and per-statement listener instructions remain unchanged.

---

## Global Constraints (from `AGENTS.md`)

1. **Port BootUI, do not reinvent.** Read BootUI's Java source at `v2.5.0` and translate the same order of checks, reason strings, and tests (`# ported:`). Every Python-forced difference is recorded as a deviation row in `docs/reference/matrix-updates/`.
2. **Reads have no side effects.** Every read route and read tool passes the `no_side_effects` fixture.
3. **Architecture boundaries (`tests/engine/test_import_boundary.py`).** SQLAlchemy is imported only inside `src/sharpit/engine/sqla/`. `engine/` never imports `sharpit.fastapi`.
4. **Performance and overhead budgets (`docs/development/overhead-budgets.md`).** `tests/fastapi/test_sql_trace_overhead.py` enforces a 50 µs/statement budget on `test_statement_overhead_budget` and `test_statement_overhead_budget_on_a_full_ring`. In `s0-sql-listener-profile.md`, the 2-vCPU Linux `sbx` runner measures 46–47 µs/statement (`3–4 µs` headroom). No budget may be raised, skipped, or deselected, and S4 must add `0.00 µs` per executed statement.
5. **Ratchets only go down (`tests/test_code_shape.py`).** No module under `src/` exceeds 1000 lines; no ruff `C901` complexity count in `tests/complexity_baseline.json` increases.
6. **Red-check discipline.** Every defect or parity test is watched red for the assertion that names the defect via `uv run python scripts/dev/red_check.py <node ids>` before the implementation commit. One condition per `assert` (ruff `PT018`).

---

## Risk Register

| Dimension | Scenario | Mitigation in Tasks |
|---|---|---|
| Per-statement overhead budget (`50 µs` on `sbx`) | Counting statements inside `before_cursor_execute` / `after_cursor_execute` or `SqlTraceRecorder.record` pushes `test_statement_overhead_budget` over 50 µs on 2-vCPU `sbx` boxes | Derive `statements` exclusively in `connections.py` at `checkout`/`checkin` from existing counters and rings (`0.00 µs` per statement); verify with a 10-round paired `sbx` A/B run (Task 3) |
| Idle app after `install(app)` without `engines=[...]` | An app that imports SQLAlchemy before `install(app)` attaches class-level `Engine` listeners at install time, before any statement runs or any `Engine` instance is discovered | Define SQLAlchemy's equivalent of "wrapped" as `following_statements(ctx) or engine_registered(ctx) or sqlite3_traced(ctx) or bool(ctx.capture.sql_delivered)`, so an installed app with attached listeners stays available while an unattached context without an engine is unavailable (Task 2) |
| Failed `sa.event.listen` with `engines=[engine]` (#185) | `install.py` registers `ctx.engines` on `capture.engine_registry` before `wiring.attach_at_install`, and `sqla.add` mutates `_statement_contexts` before `_sync_listeners()` completes | Make `sqla.add` atomic (roll back `dispatch`, `_statement_contexts`, `_discovery_contexts`, and partial listeners on error) and require `following_statements(ctx)` (or explicit hook suspension) before a registered engine counts as a recorded or wrapped SQLAlchemy source (Tasks 1 and 2) |
| Multiple concurrent connections on one `QueuePool` | Two connections checked out simultaneously execute statements interleaved in `SqlTraceRecorder._entries` | Filter the `delta` new recorder entries at `checkin` by `row["connectionId"] == hex(id(dbapi_connection))` so each checkout counts only its own statements (Task 3) |
| Connection checkout while the SQL Trace panel is paused | `SqlTraceRecorder.recording` is `False`, so `recorder._total` does not advance while `RuntimeJournal` still records `"sql"` and `"connection"` events | Fall back at `checkin` to `RuntimeJournal.count_sql_since(...)` over the `j_delta` `"sql"` journal events accepted since `checkout` (Task 3) |
| Ring wrap during a single long checkout | A single connection checkout executes more than `sql_trace_max_statements` (or `runtime_journal_max_events`) statements before `checkin`, evicting early rows | Detect `recorder._evicted != start_evicted` (or `journal._evicted != start_journal_evicted`) and return `UNKNOWN_STATEMENTS = -1` rather than a truncated count (Task 3) |

---

## S3: BootUI's SQL Trace Availability Rule and the Python Adaptation

### BootUI `v2.5.0` Source Citations

In BootUI `v2.5.0`, `SqlTraceRecorder` tracks wrapped `DataSource` bean names in `dataSourceNames` and exposes `hasWrappedDataSource()`:

- `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sqltrace/SqlTraceRecorder.java:347, 537-541, 553-559`:

```java
private final Set<String> dataSourceNames = new ConcurrentSkipListSet<>();
// ...
public void registerDataSource(String name) {
    if (name != null && !name.isBlank()) {
        dataSourceNames.add(name);
    }
}
// ...
public List<String> dataSourceNames() {
    return List.copyOf(dataSourceNames);
}

public boolean hasWrappedDataSource() {
    return !dataSourceNames.isEmpty();
}
```

`SqlTraceDataSourceBeanPostProcessor` wraps each `DataSource` bean in a tracing JDBC proxy and calls `recorder.registerDataSource(beanName)` only after wrapping succeeds:

- `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/sqltrace/SqlTraceDataSourceBeanPostProcessor.java:92-103, 118-130`:

```java
try {
    DataSource traced = trace(dataSource, beanName, recorder);
    if (traced != dataSource) {
        recorder.registerDataSource(beanName);
    }
    return traced;
} catch (RuntimeException ex) {
    log.warn(
            "BootUI could not wrap DataSource bean '{}' for SQL tracing; leaving the original bean in place.",
            beanName,
            ex);
    return bean;
}
```

Both the SQL Trace report endpoint (`GET /bootui/api/sql-trace`) and the SQL Trace insights endpoint (`GET /bootui/api/sql-trace/insights`) gate availability on `recorder.hasWrappedDataSource()`:

- `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/sqltrace/SqlTraceControllerSupport.java:63-86`:

```java
private static SqlTraceReport report(
        SqlTraceRecorder recorder, BootUiExposure exposure, ObjectProvider<DataSource> dataSourceProvider) {
    if (!recorder.hasWrappedDataSource()) {
        return SqlTraceReport.unavailable(unavailableReason(recorder, dataSourceProvider));
    }
    boolean exposeParameters =
            recorder.isCaptureParameters() && exposure.valueExposure() != ValueExposure.METADATA_ONLY;
    return recorder.report(exposeParameters);
}

private static String unavailableReason(SqlTraceRecorder recorder, ObjectProvider<DataSource> dataSourceProvider) {
    if (!recorder.isEnabled()) {
        return "SQL tracing is disabled (set bootui.sql-trace.enabled=true in a trusted local profile).";
    }
    if (dataSourceProvider.getIfAvailable() == null) {
        return "No DataSource bean is available";
    }
    return "No DataSource has been wrapped for tracing yet.";
}
```

- `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sqltrace/SqlTraceInsightsService.java:57-65`:

```java
public SqlTraceInsightsReport insights(
        List<SqlRequestEvidence> requests,
        Set<SqlRouteAttribution.Correlation> supported,
        RouteTemplateResolver templates,
        String attributionUnavailableReason) {
    if (!recorder.isEnabled() || !recorder.hasWrappedDataSource()) {
        return SqlTraceInsightsReport.unavailable(
                "SQL tracing is not active, so there are no retained statements to rank.");
    }
```

- `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/web/PanelsController.java:243-244`:

```java
case BootUiPanels.SQL_TRACE ->
    availability(beanPresent(javax.sql.DataSource.class), "No DataSource bean is available");
```

### Why 0.6.0 Deferred S3 and How Python Adapts It

In `src/sharpit/engine/sqla/__init__.py:99-103`, `sql_trace_unavailable_reason(ctx)` currently checks only whether SQL tracing is enabled and whether `"sqlalchemy"` is present in `sys.modules` (or `sqlite3` is traced):

```python
def sql_trace_unavailable_reason(ctx: SharpitContext) -> str | None:
    """Unavailable reason for SQL trace when neither SQLAlchemy nor traced sqlite3 is active."""
    if not ctx.settings.sql_trace_enabled:
        return TRACING_DISABLED
    return None if sqlite3_traced(ctx) else unavailable_reason()
```

Unlike Spring Boot—where a `DataSource` is a container-managed bean discovered in `ApplicationContext` and wrapped per bean by `SqlTraceDataSourceBeanPostProcessor`—Python applications create `sqlalchemy.engine.Engine` instances outside any DI container, and sharpit attaches statement listeners once at the class level on `sqlalchemy.engine.Engine` (`STATEMENT_EVENTS = ("before_cursor_execute", "after_cursor_execute", "handle_error")` in `src/sharpit/engine/sqla/listeners.py:37`).

In 0.6.0 (`docs/reports/2026-11-13-0.6.0-decisions.md:30-37`, `docs/reference/matrix-updates/w5c-I-visible-flags.tsv:6`), gating the panel on `_in_use(ctx)` (`engine_registry.seen_any` or `sql_delivered`) broke idle apps that called `sharpit.install(app)` without passing `engines=[...]` and checked `/sharpit/api/panels` or `/sharpit/api/sql-trace` before executing their first query. Conversely, checking only `"sqlalchemy" in sys.modules` reports the SQL Trace panel as available even when:

1. `"sqlalchemy"` was imported *after* `sharpit.install(app)` (with `sql_trace_sqlite3_enabled=False`) and neither lifespan `on_startup` nor `on_first_request` has attached the SQLAlchemy listeners yet;
2. `sqla.add` failed to attach the SQLAlchemy statement listeners (`sa.event.listen` raised); or
3. a `SharpitContext` was constructed without attaching SQLAlchemy or `sqlite3` listeners and without registering an engine.

The Python adaptation of `recorder.hasWrappedDataSource()` (`sqla.sql_trace_wrapped(ctx)`) is therefore:

- **SQLite wrapped:** `sqlite3_traced(ctx)` is `True` (or `"sqlite3" in ctx.capture.sql_delivered`); **or**
- **SQLAlchemy listeners attached:** `following_statements(ctx)` is `True` (or `"sqlalchemy" in ctx.capture.sql_delivered`); **or**
- **SQLAlchemy engine registered on an attached context:** `ctx.capture.engine_registry is not None and ctx.capture.engine_registry.seen_any` while `"sqlalchemy" in ctx.capture.suspended_sources` (matching BootUI's `SqlTraceRecorder.suspendForIdle()` at `SqlTraceRecorder.java:1100-1103`, where suspending capture does not unwrap an already-registered `DataSource`).

When `ctx.settings.sql_trace_enabled` is `True`:

1. If `sqlite3_traced(ctx)` is `True`, `sql_trace_unavailable_reason(ctx)` returns `None`.
2. Otherwise, if `unavailable_reason()` is not `None` (SQLAlchemy is not imported or `< 2.0`), `sql_trace_unavailable_reason(ctx)` returns that reason (`NO_SQLALCHEMY` or `OLD_SQLALCHEMY`).
3. Otherwise, if `not sql_trace_wrapped(ctx)`, `sql_trace_unavailable_reason(ctx)` returns `NOT_WRAPPED = "No DataSource has been wrapped for tracing yet."` (verbatim from `SqlTraceControllerSupport.java:85`).

This single function (`sqla.sql_trace_unavailable_reason(ctx)`, re-exported as `tools.sql_trace_unavailable_reason(ctx)`) backs:

- `/sharpit/api/panels` (`src/sharpit/fastapi/adapter.py:217`: `"sql-trace": self._sql_trace_availability(ctx)`),
- `/sharpit/api/sql-trace` and MCP/CLI `sql_trace_report` (`src/sharpit/engine/tools.py:50, 295`: `reason = sql_trace_unavailable_reason(ctx)`), and
- `/sharpit/api/sql-trace/insights` (`src/sharpit/engine/tools04/sql_trace.py:7, 13`: passes `sql_trace_unavailable_reason(ctx)` to `insights_report(...)`).

Note on `sqlalchemy-statistics` (`src/sharpit/engine/collectors/sqlastats.py:125-129`): in BootUI, `HibernateStatisticsService` gates on `EntityManagerFactory` / `SessionFactory`, not `SqlTraceRecorder.hasWrappedDataSource()`. `sqlastats._unavailable_reason(ctx)` therefore calls `sqla.tracing_unavailable_reason(ctx)` (`TRACING_DISABLED` when `not ctx.settings.sql_trace_enabled`, else `None if sqla.sqlite3_traced(ctx) else sqla.unavailable_reason()`), keeping `tests/engine/test_sqlastats.py` unchanged.

---

## S4: Connection Statement Counts and the #185 Failed-Attach Fix

### Part 1: Fixing the #185 Known Limit (Failed SQLAlchemy Listener Attach with a Registered Engine)

#### BootUI `v2.5.0` Rule

In `SqlTraceDataSourceBeanPostProcessor.java:92-103`, `recorder.registerDataSource(beanName)` is called only *after* `trace(dataSource, beanName, recorder)` returns the wrapped proxy without throwing. If wrapping throws, `recorder.hasWrappedDataSource()` stays `false`, and `SqlCapture.of(recorder, true, r2dbc)` in `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/insights/SqlCapture.java:60-68` returns `notRecorded(NOT_RECORDED)`:

```java
public static SqlCapture of(SqlTraceRecorder recorder, boolean tracedDataSourceRequired, boolean r2dbc) {
    if (recorder != null && !recorder.isEnabled()) {
        return notRecorded(DISABLED);
    }
    if (recorder == null || (tracedDataSourceRequired && !recorder.hasWrappedDataSource())) {
        return notRecorded(r2dbc ? R2DBC_ONLY : NOT_RECORDED);
    }
    return r2dbc ? recordedExcept(R2DBC_NOT_RECORDED) : capturing();
}
```

#### Root Cause in sharpit

Three interactions in sharpit currently cause `sqlcapture.for_context(ctx)` to return `SqlCapture.capturing()` after a failed SQLAlchemy listener attach when `engines=[engine]` was passed to `sharpit.install(app, engines=[engine])`:

1. `src/sharpit/fastapi/install.py:105-107` seeds `capture.engine_registry.add(engine)` before `wiring.attach_at_install(app, ctx)` runs `self._attach_sqla(ctx)` (`src/sharpit/fastapi/capture.py:427-436`), and `src/sharpit/engine/sqla/listeners.py:232-235` also adds `ctx.engines` to `registry` before `_sync_listeners()`. Consequently, `registry.seen_any` is `True` even if `sa.event.listen` raises on the first listener.
2. In `src/sharpit/engine/sqla/listeners.py:236-242`, `sqla.add` adds `ctx` to `dispatch` and `_statement_contexts[ctx.context_id] = ctx` *before* calling `_sync_listeners()`. When `sa.event.listen` raises part-way through `STATEMENT_EVENTS`, `ctx` remains in `_statement_contexts` and `dispatch`, and any listener attached earlier in the loop remains attached to `sa.engine.Engine`.
3. In `src/sharpit/engine/sqla/__init__.py:69-97`, `_in_use(ctx)` returns `{SQLALCHEMY}` whenever `registry.seen_any` is `True`, and `sources_recorded(ctx)` treats any source in `_in_use(ctx)` that is not in `capture.suspended_sources` as `live`. Because a startup hook failure calls `self.hook_failed("sql listeners", exc)` without suspending a previously working hook, `sources_recorded(ctx)` returns `(True, None)`.

#### The Fix

1. **Add `following_statements(ctx: SharpitContext) -> bool` in `src/sharpit/engine/sqla/listeners.py`** (mirroring `following_connections(ctx)` at `listeners.py:318-322`):

```python
def following_statements(ctx: SharpitContext) -> bool:
    """Whether the statement listeners run for ``ctx``: SQLAlchemy statements can be recorded."""
    with _lock:
        armed = attached()
        return ctx.context_id in _statement_contexts and all(armed[name] for name in STATEMENT_EVENTS)
```

2. **Make `sqla.add` atomic in `src/sharpit/engine/sqla/listeners.py:228-243`:**
   - Record prior membership (`had_statements = ctx.context_id in _statement_contexts`, `had_discovery = ctx.context_id in _discovery_contexts`) before mutating state.
   - Run `_sync_listeners()` inside `try / except Exception:`. On failure, restore `_statement_contexts` and `_discovery_contexts` (and `dispatch.remove_context(ctx)` if neither remains), call `_sync_listeners()` under `contextlib.suppress(Exception)` so any partially attached SQLAlchemy listener is removed, and re-raise.
   - Register `for engine in ctx.engines: registry.add(engine)` in `sqla.add` only *after* `_sync_listeners()` succeeds.

3. **Require attached (or explicitly suspended) listeners for a registered engine in `src/sharpit/engine/sqla/__init__.py:69-97`:**
   - In `_in_use(ctx)`, a SQLAlchemy source is in use when:
     - `SQLALCHEMY in capture.sql_delivered`, or
     - `following_statements(ctx)` and `registry is not None and registry.seen_any`, or
     - `SQLALCHEMY in capture.suspended_sources` and `registry is not None and registry.seen_any`.
   - Thus, if `sqla.add` failed to attach the SQLAlchemy listeners (so `following_statements(ctx)` is `False` and `SQLALCHEMY` was never suspended nor delivered a statement), `SQLALCHEMY` is not in `_in_use(ctx)`, `sources_recorded(ctx)` returns `(False, NOT_RECORDED)` when `sqlite3` is not active, and Runtime Insights SQL checks report `UNAVAILABLE`.

---

### Part 2: How BootUI Counts Statements per Connection and sharpit's Zero-Per-Statement-Cost Design

#### BootUI `v2.5.0` Source Citations

In BootUI `v2.5.0`, `SqlTracingProxies` wraps every `Connection` returned by `DataSource.getConnection()` in a `ConnectionHandler` carrying a `ConnectionCheckout` state object:

- `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sqltrace/SqlTracingProxies.java:272-275`:

```java
return wrapConnection(
        connection, recorder, name, recorder.checkoutConnection(name, System.nanoTime() - start));
```

- `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sqltrace/ConnectionCheckout.java:13-35`:

```java
public record ConnectionCheckout(
        String dataSource,
        long waitNanos,
        long obtainedNanos,
        String checkoutRequestId,
        String checkoutThread,
        AtomicInteger statements,
        AtomicBoolean released) {

    public ConnectionCheckout(
            String dataSource, long waitNanos, long obtainedNanos, String checkoutRequestId, String checkoutThread) {
        this(
                dataSource != null ? dataSource : "",
                Math.max(0L, waitNanos),
                obtainedNanos,
                checkoutRequestId,
                checkoutThread,
                new AtomicInteger(),
                new AtomicBoolean());
    }

    public void statementExecuted() {
        statements.incrementAndGet();
    }
```

- `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sqltrace/SqlTracingProxies.java:740-742, 800-802`:

```java
if (checkout != null) {
    checkout.statementExecuted();
}
```

- `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sqltrace/SqlTraceRecorder.java:1009-1031` and `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/journal/ConnectionPayload.java:11-23`:

```java
void releaseConnection(ConnectionCheckout checkout) {
    if (checkout == null || !checkout.markReleased()) {
        return;
    }
    RuntimeJournal j = this.journal;
    if (j == null || !j.accepts(JournalSource.CONNECTION)) {
        return;
    }
    long releasedNanos = System.nanoTime();
    long durationNanos = Math.max(0L, releasedNanos - checkout.obtainedNanos());
    j.offer(
            JournalSource.CONNECTION,
            releasedNanos,
            durationNanos,
            checkout.checkoutRequestId(),
            checkout.checkoutThread(),
            new ConnectionPayload(
                    checkout.dataSource(),
                    checkout.waitNanos(),
                    checkout.statements().get(),
                    checkout.obtainedNanos()));
}
```

Downstream in BootUI `v2.5.0`:

- `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/journal/RequestJournalProfiles.java:1032-1041` reads `connection.statements()` to render `"waited X µs, N statement(s)"`.
- `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/insights/ConnectionReacquisition.java:365, 427-446` reads `OrmPayload.statements()` (`Math.max(0, r.statements)`) on `"orm"` journal events, whereas `ConnectionPayload.statements()` is the statement count on `"connection"` pool events (`src/sharpit/engine/collectors/insights/kinds/connection_reacquisition.py:1-8` remains a stub until lane `J3`).

#### Why Per-Statement Counting Is Too Expensive in Python and Comparison of Designs

In Python, `tests/fastapi/test_sql_trace_overhead.py` holds a single SQLAlchemy connection open (`with engine.connect() as conn:`) across 45 rounds × 200 statements (`9,000` statements) and asserts median overhead `<= 50.0 µs/statement`. On the 2-vCPU Linux `sbx` runner (`s0-sql-listener-profile.md`), the full listener + recorder + journal path already takes `46–47 µs/statement`.

| Design | Mechanism | Per-statement cost | Connection-state invariance (`test_connection_journal.py:115-128`) | Verdict |
|---|---|---|---|---|
| **Design 1: Mutate pool record / fairy per statement** (reverted in 0.6.0 #184) | In `listeners._emit`, look up `conn.connection._connection_record.info[CHECKOUT_KEY]` and increment `checkout.statements += 1` | **+0.8 to +1.5 µs / statement** (attribute traversal + dict lookup + slot mutation on every statement) | Violates `assert state() == before` during statement execution | **Rejected** — consumes 25–45% of remaining `sbx` headroom |
| **Design 2: Per-connection counter dict in `SqlTraceRecorder`** | Maintain `_by_connection: dict[str, int]` inside `SqlTraceRecorder.record` keyed by `connection_id` | **+0.15 to +0.30 µs / statement** (extra dict lookup and integer store under `recorder._lock` on every statement; misses statements while paused) | Preserved | **Rejected** — adds instructions to `SqlTraceRecorder.record` on every statement |
| **Design 3 (Chosen): Derive count at `checkin` from existing counters and rings** | Snapshot `(recorder._total, recorder._evicted, journal._accepted["sql"], journal._evicted)` at pool `checkout`; compute `statements` at pool `checkin` | **0.00 µs / statement** (zero instructions added to `before_cursor_execute`, `after_cursor_execute`, `_emit`, `dispatch`, `SqlTraceRecorder.record`, or `RuntimeJournal.offer_flat`) | Preserved (`state() == before` holds across all statements) | **Selected** |

#### How Design 3 Derives `statements` at `checkin`

Every statement executed through `src/sharpit/engine/sqla/listeners.py:124-140` (`_emit`) *already* computes `connection_id = hex(id(conn.connection.dbapi_connection))` and passes it to `dispatch.record_sql_event(event)`. Inside `dispatch._record` (`src/sharpit/engine/sources/dispatch.py:249-269`):

- When `recorder.recording` is `True`, `SqlTraceRecorder.record` (`src/sharpit/engine/capture/sqltrace.py:312, 328-329`) appends a dict containing `"connectionId": connection_id` to `recorder._entries` and increments `recorder._total += 1` (and `recorder._evicted += 1` when the deque wraps).
- When `journal.accepts("sql")` is `True` (including when the SQL Trace panel is paused), `RuntimeJournal.offer_flat` (`src/sharpit/engine/capture/journal.py:322-337`) appends the `"sql"` event (with `"completedNanos"`, `"requestId"`, `"thread"`) to `journal._events` and increments `journal._accepted["sql"] += 1` (and `journal._evicted += 1` when the deque wraps).

Therefore, `src/sharpit/engine/sqla/connections.py` needs only two read helpers on `SqlTraceRecorder` and `RuntimeJournal`, called exclusively at `checkout` and `checkin`:

1. **At `checkout(dbapi_connection, record, proxy)` (`connections.py:65-77`):**
   - For each target `ctx` where `ctx.capture.journal.accepts(CONNECTION)`:
     - Read `(start_total, start_evicted) = ctx.capture.sql_trace.checkout_cursor()` (returns `(self._total, self._evicted)` without taking a lock on the fast path or under `self._lock` at checkout).
     - Read `(start_sql_accepted, start_journal_evicted) = ctx.capture.journal.sql_cursor()` (returns `(self._accepted.get("sql", 0), self._evicted)`).
     - Store these four integers in a per-context mapping `cursors: dict[int, tuple[int, int, int, int]]` on `Checkout` in `record.info[CHECKOUT_KEY]`.
2. **At `checkin(dbapi_connection, record)` (`connections.py:80-112`):**
   - Pop `state: Checkout` from `record.info.pop(CHECKOUT_KEY, None)` before offering any event.
   - Compute `connection_id = hex(id(dbapi_connection))` once when `dbapi_connection is not None` (or falls back when `dbapi_connection` is `None`).
   - For each target `ctx`:
     - Look up `(start_total, start_evicted, start_sql_accepted, start_journal_evicted)` from `state.cursors.get(ctx.context_id)`.
     - Call `_count_statements(ctx, state, connection_id)`:
       1. Ask `recorder.count_for_connection(connection_id, start_total, start_evicted)`:
          - Under `recorder._lock`, let `delta = self._total - start_total`.
          - Let `j_delta = journal.sql_accepted_since(start_sql_accepted)` when `journal.accepts("sql")` else `delta`.
          - **Zero-statement fast path (`O(1)`):** If `delta == 0` and `j_delta == 0` and (`self._recording` or `journal.accepts("sql")`), return `0`.
          - **Recorder tail scan (`O(delta)` at checkin):** If `delta == j_delta` (no statement executed while the panel was paused), `self._evicted == start_evicted`, and `0 < delta <= len(self._entries)`: iterate the last `delta` entries of `reversed(self._entries)` and return `sum(1 for entry in islice(reversed(self._entries), delta) if entry["connectionId"] == connection_id)`.
       2. **Paused-panel journal fallback (`O(j_delta)` at checkin):** If the panel was paused during the checkout (`j_delta > delta` or `not recorder.recording`) and `journal.accepts("sql")`:
          - Ask `journal.count_sql_since(state.obtained_ns, state.request_id, state.thread, start_sql_accepted, start_journal_evicted)`:
          - Under `journal._lock`, if `self._evicted == start_journal_evicted` and `0 <= j_delta <= len(self._events)`, scan backward from `reversed(self._events)` while `stored["completedNanos"] >= obtained_ns`, inspecting at most `j_delta` `"sql"` events and counting those whose `(stored["requestId"], stored["thread"]) == (request_id, thread)`.
       3. **Honest unknown fallback (`UNKNOWN_STATEMENTS = -1`):** If rows from this checkout were evicted (`_evicted != start_evicted`), `clear()` reset the recorder mid-checkout (`delta > len(self._entries)`), or the panel was paused while `"sql"` was excluded from `runtime_journal_sources`, return `UNKNOWN_STATEMENTS = -1`.

#### How the Paired `sbx` Measurement Proves Zero Per-Statement Cost

1. **Local sanity check (`-n 0`):**
   - `uv run pytest -q -n 0 tests/fastapi/test_sql_trace_overhead.py`
   - `uv run python -m scripts.dev.profile_sql_listener --statements 20000 --runs 3`
2. **Paired 10-round A/B measurement on the 2-vCPU Linux `sbx` runner (`docs/development/overhead-budgets.md`):**
   - Run 10 interleaved pairs (`base` vs `feat/0.9.0-s34`) of `pytest -q -n 0 tests/fastapi/test_sql_trace_overhead.py -s` on the same `sbx` box.
   - Because `test_statement_overhead_budget` opens a single connection (`with engine.connect() as conn:`) before the 45 measurement rounds and closes it only after all 9,000 statements finish, `checkout` runs once before the timed loop and `checkin` runs once after the timed loop.
   - Expected paired delta (`head - base`): `0.0 µs/statement` within `±0.3 µs` split-half noise, with both `test_statement_overhead_budget` and `test_statement_overhead_budget_on_a_full_ring` under `50.0 µs`.

---

## Tasks

### Task 1: Close the #185 Failed Listener-Attach Gap (`S4a`)

**Files:**
- Modify: `src/sharpit/engine/sqla/listeners.py`
- Modify: `src/sharpit/engine/sqla/__init__.py`
- Test: `tests/engine/insights/test_insights_sqlrecorded.py`

**Interfaces:**
- `src/sharpit/engine/sqla/listeners.py`:
  - `following_statements(ctx: SharpitContext) -> bool`
  - Atomic rollback in `add(ctx: SharpitContext, *, statements: bool, discovery: bool) -> bool`
- `src/sharpit/engine/sqla/__init__.py`:
  - Re-export `following_statements` in `__all__`
  - Update `_in_use(ctx: SharpitContext) -> set[str]` so `registry.seen_any` counts for `SQLALCHEMY` only when `following_statements(ctx)` is `True` or `SQLALCHEMY in capture.suspended_sources`

- [ ] **Step 1: Write the failing tests in `tests/engine/insights/test_insights_sqlrecorded.py`**

Add two tests to `tests/engine/insights/test_insights_sqlrecorded.py` (replacing the known-limit note at lines 10–11):

```python
def test_a_failed_sqlalchemy_listener_attach_with_an_engine_registered_reads_not_recorded(
    handles: list[SharpitHandle],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_listen(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated listener failure")

    monkeypatch.setattr(sa.event, "listen", fail_listen)
    ctx = _install(handles, engines=[_engine()], sql_trace_sqlite3_enabled=False)._context
    capture = sqlcapture.for_context(ctx)

    assert not capture.recorded
    assert capture.reason == NOT_RECORDED
    assert _dml_check(ctx)["status"] == "UNAVAILABLE"


def test_a_failed_listener_attach_rolls_back_partial_listeners_and_routing(
    handles: list[SharpitHandle],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_listen = sa.event.listen

    def fail_on_after(target: object, identifier: str, fn: object, *args: object, **kwargs: object) -> None:
        if identifier == "after_cursor_execute":
            raise RuntimeError("simulated partial attach failure")
        real_listen(target, identifier, fn, *args, **kwargs)

    monkeypatch.setattr(sa.event, "listen", fail_on_after)
    ctx = _install(handles, engines=[_engine()], sql_trace_sqlite3_enabled=False)._context

    assert not sqla.following_statements(ctx)
    assert sqla.routed(ctx) == (False, False)
    assert not any(sqla.attached().values())
```

- [ ] **Step 2: Prove the tests fail for the right reason with `red_check.py`**

Run:
```bash
uv run python scripts/dev/red_check.py \
  tests/engine/insights/test_insights_sqlrecorded.py::test_a_failed_sqlalchemy_listener_attach_with_an_engine_registered_reads_not_recorded \
  tests/engine/insights/test_insights_sqlrecorded.py::test_a_failed_listener_attach_rolls_back_partial_listeners_and_routing
```
Expected:
- `test_a_failed_sqlalchemy_listener_attach_with_an_engine_registered_reads_not_recorded` fails at `assert not capture.recorded` (`capture.recorded` is `True`).
- `test_a_failed_listener_attach_rolls_back_partial_listeners_and_routing` fails at `assert not sqla.following_statements(ctx)` or `assert sqla.routed(ctx) == (False, False)`.

- [ ] **Step 3: Implement `following_statements`, atomic `sqla.add`, and `_in_use` guard**

In `src/sharpit/engine/sqla/listeners.py`:

```python
def add(ctx: SharpitContext, *, statements: bool, discovery: bool) -> bool:
    """Route SQLAlchemy events to ``ctx`` and attach any missing class-level listeners."""
    if not is_available() or (not statements and not discovery):
        return False
    with _lock:
        had_statements = ctx.context_id in _statement_contexts
        had_discovery = ctx.context_id in _discovery_contexts
        if statements:
            dispatch.add_context(ctx)
            _statement_contexts[ctx.context_id] = ctx
        if discovery:
            _discovery_contexts[ctx.context_id] = ctx
        try:
            _sync_listeners()
        except Exception:
            if statements and not had_statements:
                _statement_contexts.pop(ctx.context_id, None)
                dispatch.remove_context(ctx)
            if discovery and not had_discovery:
                _discovery_contexts.pop(ctx.context_id, None)
            with contextlib.suppress(Exception):
                _sync_listeners()
            raise
        registry = ctx.capture.engine_registry
        if isinstance(registry, EngineRegistry):
            for engine in ctx.engines:
                registry.add(engine)
        return True
```

And add `following_statements(ctx)` next to `following_connections(ctx)` in `src/sharpit/engine/sqla/listeners.py`:

```python
def following_statements(ctx: SharpitContext) -> bool:
    """Whether the statement listeners run for ``ctx``: SQLAlchemy statements can be recorded."""
    with _lock:
        armed = attached()
        return ctx.context_id in _statement_contexts and all(armed[name] for name in STATEMENT_EVENTS)
```

In `src/sharpit/engine/sqla/__init__.py`, export `following_statements` and update `_in_use(ctx)`:

```python
def _in_use(ctx: SharpitContext) -> set[str]:
    """Sources with evidence of use in ``ctx``: a registered SQLAlchemy engine or a routed statement."""
    capture = ctx.capture
    used = set(capture.sql_delivered)
    registry = capture.engine_registry
    if (
        registry is not None
        and registry.seen_any
        and (following_statements(ctx) or SQLALCHEMY in capture.suspended_sources)
    ):
        used.add(SQLALCHEMY)
    return used
```

- [ ] **Step 4: Run tests and static gates**

Run:
```bash
uv run pytest -q -n 2 tests/engine/insights/test_insights_sqlrecorded.py tests/engine/insights/test_insights_sqlcapture.py
uv run ruff check
uv run ruff format --check
uv run pyright
```
Expected: all tests pass; `ruff` and `pyright` clean.

- [ ] **Step 5: Commit**

```bash
git add src/sharpit/engine/sqla/listeners.py src/sharpit/engine/sqla/__init__.py tests/engine/insights/test_insights_sqlrecorded.py
git commit -m "fix: mark SQL unrecorded when SQLAlchemy listener attachment fails"
```

---

### Task 2: Port BootUI's SQL Trace Wrapped-Source Availability Rule (`S3`)

**Files:**
- Modify: `src/sharpit/engine/sqla/__init__.py`
- Modify: `src/sharpit/engine/collectors/sqlastats.py`
- Test: `tests/fastapi/test_sql_trace_api.py`
- Test: `tests/engine/insights/test_insights_sqlrecorded.py`

**Interfaces:**
- `src/sharpit/engine/sqla/__init__.py`:
  - `NOT_WRAPPED = "No DataSource has been wrapped for tracing yet."`
  - `sql_trace_wrapped(ctx: SharpitContext) -> bool`
  - `tracing_unavailable_reason(ctx: SharpitContext) -> str | None` (for `sqlastats`, which checks SQLAlchemy presence and `sql_trace_enabled` without requiring statement listeners)
  - `sql_trace_unavailable_reason(ctx: SharpitContext) -> str | None` (returns `TRACING_DISABLED`, `NO_SQLALCHEMY` / `OLD_SQLALCHEMY`, `NOT_WRAPPED`, or `None`)

- [ ] **Step 1: Write the failing tests in `tests/fastapi/test_sql_trace_api.py`**

Add tests covering an unattached context where SQLAlchemy is imported after `install(app)` (before `on_startup` / `on_first_request`) and a failed listener attachment with a registered engine:

```python
def test_sql_trace_unavailable_when_sqlalchemy_imported_after_install_before_listeners_attach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ported: SqlTraceControllerSupportTests.unavailableWhenNoDataSourceWrappedYet
    real_sa = sys.modules["sqlalchemy"]
    monkeypatch.delitem(sys.modules, "sqlalchemy")
    app = FastAPI()
    handle = sharpit.install(app, enabled="ON", sql_trace_sqlite3_enabled=False)
    try:
        monkeypatch.setitem(sys.modules, "sqlalchemy", real_sa)
        ctx = handle._context

        assert tools.sql_trace_unavailable_reason(ctx) == sqla.NOT_WRAPPED
        assert tools.sql_trace_report(ctx)["available"] is False
        assert tools.sql_trace_report(ctx)["unavailableReason"] == sqla.NOT_WRAPPED
        assert sql_trace_tools.insights(ctx)["available"] is False
    finally:
        handle.uninstall()


def test_sql_trace_unavailable_after_failed_sqlalchemy_listener_attach_even_with_registered_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_listen(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated listener failure")

    engine = sa.create_engine("sqlite:///:memory:")
    monkeypatch.setattr(sa.event, "listen", fail_listen)
    app = FastAPI()
    handle = sharpit.install(app, enabled="ON", engines=[engine], sql_trace_sqlite3_enabled=False)
    try:
        ctx = handle._context

        assert tools.sql_trace_unavailable_reason(ctx) == sqla.NOT_WRAPPED
        assert tools.sql_trace_report(ctx)["available"] is False
        assert sql_trace_tools.insights(ctx)["available"] is False
    finally:
        handle.uninstall()
        engine.dispose()
```

- [ ] **Step 2: Prove the tests fail for the right reason with `red_check.py`**

Run:
```bash
uv run python scripts/dev/red_check.py \
  tests/fastapi/test_sql_trace_api.py::test_sql_trace_unavailable_when_sqlalchemy_imported_after_install_before_listeners_attach \
  tests/fastapi/test_sql_trace_api.py::test_sql_trace_unavailable_after_failed_sqlalchemy_listener_attach_even_with_registered_engine
```
Expected: both tests fail at the assertion on `tools.sql_trace_unavailable_reason(ctx)` / `tools.sql_trace_report(ctx)["available"] is False` because `sql_trace_unavailable_reason(ctx)` currently returns `None` whenever `"sqlalchemy"` is in `sys.modules`.

- [ ] **Step 3: Implement `sql_trace_wrapped`, `tracing_unavailable_reason`, and updated `sql_trace_unavailable_reason`**

In `src/sharpit/engine/sqla/__init__.py`:

```python
NOT_WRAPPED = "No DataSource has been wrapped for tracing yet."
```

```python
def sql_trace_wrapped(ctx: SharpitContext) -> bool:
    """Whether ``ctx`` has wrapped a SQL source: listeners are attached, an engine is registered, or SQL ran."""
    if sqlite3_traced(ctx) or following_statements(ctx) or bool(ctx.capture.sql_delivered):
        return True
    registry = ctx.capture.engine_registry
    return SQLALCHEMY in ctx.capture.suspended_sources or (
        registry is not None and registry.seen_any and SQLALCHEMY in ctx.capture.suspended_sources
    )


def tracing_unavailable_reason(ctx: SharpitContext) -> str | None:
    """Unavailable reason when SQL tracing is disabled or SQLAlchemy 2.0+ is absent."""
    if not ctx.settings.sql_trace_enabled:
        return TRACING_DISABLED
    return None if sqlite3_traced(ctx) else unavailable_reason()


def sql_trace_unavailable_reason(ctx: SharpitContext) -> str | None:
    """Unavailable reason for the SQL Trace panel, report, and insights."""
    reason = tracing_unavailable_reason(ctx)
    if reason is not None:
        return reason
    return None if sql_trace_wrapped(ctx) else NOT_WRAPPED
```

In `src/sharpit/engine/collectors/sqlastats.py:125-129`, call `sqla.tracing_unavailable_reason(ctx)`:

```python
def _unavailable_reason(ctx: SharpitContext) -> str | None:
    reason = sqla.tracing_unavailable_reason(ctx)
    if reason is not None:
        return reason
    return None if sqla.orm_available() else sqla.NO_ORM
```

- [ ] **Step 4: Run tests and static gates**

Run:
```bash
uv run pytest -q -n 2 tests/fastapi/test_sql_trace_api.py tests/fastapi/test_panel_availability.py tests/fastapi/test_sql_trace_insights_api.py tests/engine/test_sqlastats.py tests/engine/insights/test_insights_sqlrecorded.py
uv run ruff check
uv run ruff format --check
uv run pyright
```
Expected: all tests pass; `ruff` and `pyright` clean.

- [ ] **Step 5: Commit**

```bash
git add src/sharpit/engine/sqla/__init__.py src/sharpit/engine/collectors/sqlastats.py tests/fastapi/test_sql_trace_api.py
git commit -m "feat: gate SQL Trace availability on wrapped listeners or registered engine"
```

---

### Task 3: Derive `ConnectionPayload.statements` at Check-in Without Per-Statement Work (`S4b`)

**Files:**
- Modify: `src/sharpit/engine/capture/sqltrace.py`
- Modify: `src/sharpit/engine/capture/journal.py`
- Modify: `src/sharpit/engine/sqla/connections.py`
- Test: `tests/engine/capture/test_connection_journal.py`

**Interfaces:**
- `src/sharpit/engine/capture/sqltrace.py`:
  - `SqlTraceRecorder.checkout_cursor(self) -> tuple[int, int]`
  - `SqlTraceRecorder.count_for_connection(self, connection_id: str | None, start_total: int, start_evicted: int) -> int | None`
- `src/sharpit/engine/capture/journal.py`:
  - `RuntimeJournal.sql_cursor(self) -> tuple[int, int]`
  - `RuntimeJournal.count_sql_since(self, obtained_ns: int, request_id: str | None, thread: str, start_accepted: int, start_evicted: int) -> int | None`
- `src/sharpit/engine/sqla/connections.py`:
  - `Checkout.cursors: dict[int, tuple[int, int, int, int]]`
  - `_count_statements(ctx: SharpitContext, state: Checkout, connection_id: str | None) -> int`

- [ ] **Step 1: Write the failing tests in `tests/engine/capture/test_connection_journal.py`**

Update the existing assertion in `test_connection_journal_event_offered_once_per_release_with_bootui_fields` (`assert record["statements"] == 2`) and `test_connection_journal_is_offered_while_the_panel_is_paused` (`assert _only(handle)["statements"] == 1`), update `test_connection_journal_statement_count_is_unknown_and_statements_keep_no_connection_state` to assert `[3, 3]` while preserving `assert state() == before`, and add tests for 0 statements and concurrent checkouts:

```python
def test_connection_journal_counts_statements_at_checkin_and_statements_keep_no_connection_state(
    handles: list[_Handle],
) -> None:
    handle = _open(handles)
    _use(handle.engine, 3)

    with handle.engine.connect() as conn:
        fairy = conn.connection
        record = fairy._connection_record
        assert record is not None

        def state() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            return (dict(conn.info), dict(fairy.info), dict(record.info))

        before = state()
        for _ in range(3):
            conn.execute(sa.text("SELECT 1")).fetchall()
            assert state() == before

    assert [r["statements"] for r in _records(handle)] == [3, 3]


def test_connection_journal_counts_zero_statements_when_released_unused(handles: list[_Handle]) -> None:
    # ported: SqlTracingProxiesTests.zeroStatementConnectionStillPublishesHoldEvent
    handle = _open(handles)
    _use(handle.engine, 0)

    assert _only(handle)["statements"] == 0


def test_connection_journal_counts_each_concurrent_connection_separately(handles: list[_Handle]) -> None:
    handle = _open(handles, pool_size=2, max_overflow=0)
    with handle.engine.connect() as first, handle.engine.connect() as second:
        first.execute(sa.text("SELECT 1")).fetchall()
        second.execute(sa.text("SELECT 1")).fetchall()
        first.execute(sa.text("SELECT 1")).fetchall()

    assert [r["statements"] for r in _records(handle)] == [2, 1]
```

- [ ] **Step 2: Prove the tests fail for the right reason with `red_check.py`**

Run:
```bash
uv run python scripts/dev/red_check.py \
  tests/engine/capture/test_connection_journal.py::test_connection_journal_event_offered_once_per_release_with_bootui_fields \
  tests/engine/capture/test_connection_journal.py::test_connection_journal_counts_statements_at_checkin_and_statements_keep_no_connection_state \
  tests/engine/capture/test_connection_journal.py::test_connection_journal_counts_zero_statements_when_released_unused \
  tests/engine/capture/test_connection_journal.py::test_connection_journal_counts_each_concurrent_connection_separately \
  tests/engine/capture/test_connection_journal.py::test_connection_journal_is_offered_while_the_panel_is_paused
```
Expected: all five fail at the `statements` assertion because `record["statements"]` is `-1` (`UNKNOWN_STATEMENTS`).

- [ ] **Step 3: Implement checkout cursors and checkin count derivation**

In `src/sharpit/engine/capture/sqltrace.py`, add `checkout_cursor` and `count_for_connection` on `SqlTraceRecorder`:

```python
def checkout_cursor(self) -> tuple[int, int]:
    """Return ``(total_recorded, evicted)`` at connection checkout without per-statement work."""
    return self._total, self._evicted


def count_for_connection(
    self,
    connection_id: str | None,
    start_total: int,
    start_evicted: int,
) -> int | None:
    """Count statements recorded for ``connection_id`` since ``start_total``, or ``None`` if not retained."""
    with self._lock:
        delta = self._total - start_total
        if delta == 0:
            return 0 if self._recording else None
        if connection_id is None or self._evicted != start_evicted or delta < 0 or delta > len(self._entries):
            return None
        return sum(
            1
            for entry in itertools.islice(reversed(self._entries), delta)
            if entry.get("connectionId") == connection_id
        )
```

In `src/sharpit/engine/capture/journal.py`, add `sql_cursor` and `count_sql_since` on `RuntimeJournal`:

```python
def sql_cursor(self) -> tuple[int, int]:
    """Return ``(sql_accepted, evicted)`` at connection checkout."""
    return self._accepted.get("sql", 0), self._evicted


def count_sql_since(
    self,
    obtained_ns: int,
    request_id: str | None,
    thread: str,
    start_accepted: int,
    start_evicted: int,
) -> int | None:
    """Count ``sql`` journal events since ``start_accepted`` matching ``(request_id, thread)``."""
    with self._lock:
        if "sql" not in self._sources or self._evicted != start_evicted:
            return None
        delta = self._accepted.get("sql", 0) - start_accepted
        if delta == 0:
            return 0
        if delta < 0 or delta > len(self._events):
            return None
        seen_sql = 0
        matched = 0
        for stored in reversed(self._events):
            if stored["source"] != "sql":
                continue
            seen_sql += 1
            if stored["completedNanos"] >= obtained_ns and (
                stored["requestId"] == request_id and stored["thread"] == thread
            ):
                matched += 1
            if seen_sql >= delta:
                break
        return matched
```

In `src/sharpit/engine/sqla/connections.py`, snapshot cursors per active context in `checkout(...)` and derive `statements` in `_offer(...)` at `checkin(...)`:

```python
@dataclass(slots=True)
class Checkout:
    """State carried on a pool record between ``checkout`` and ``checkin``."""

    wait_ns: int
    obtained_ns: int
    request_id: str | None
    thread: str
    cursors: dict[int, tuple[int, int, int, int]]
```

```python
def _cursors(targets: tuple[SharpitContext, ...]) -> dict[int, tuple[int, int, int, int]]:
    out: dict[int, tuple[int, int, int, int]] = {}
    for ctx in targets:
        journal = ctx.capture.journal
        if journal.accepts(CONNECTION):
            total, evicted = ctx.capture.sql_trace.checkout_cursor()
            sql_acc, j_evicted = journal.sql_cursor()
            out[ctx.context_id] = (total, evicted, sql_acc, j_evicted)
    return out


def _count_statements(ctx: SharpitContext, state: Checkout, connection_id: str | None) -> int:
    cursor = state.cursors.get(ctx.context_id)
    if cursor is None:
        return UNKNOWN_STATEMENTS
    start_total, start_evicted, start_sql_acc, start_j_evicted = cursor
    recorder = ctx.capture.sql_trace
    journal = ctx.capture.journal
    cur_sql_acc, _ = journal.sql_cursor()
    cur_total, _ = recorder.checkout_cursor()
    sql_delta = cur_sql_acc - start_sql_acc
    rec_delta = cur_total - start_total
    if not journal.accepts("sql") or sql_delta == rec_delta:
        count = recorder.count_for_connection(connection_id, start_total, start_evicted)
        if count is not None:
            return count
    count = journal.count_sql_since(
        state.obtained_ns,
        state.request_id,
        state.thread,
        start_sql_acc,
        start_j_evicted,
    )
    return count if count is not None else UNKNOWN_STATEMENTS
```

- [ ] **Step 4: Run functional tests, local overhead budget (`-n 0`), and static gates**

Run:
```bash
uv run pytest -q -n 2 tests/engine/capture/test_connection_journal.py
uv run pytest -q -n 0 tests/fastapi/test_sql_trace_overhead.py
uv run ruff check
uv run ruff format --check
uv run pyright
```
Expected: all tests in `test_connection_journal.py` and `test_sql_trace_overhead.py` pass; `ruff` and `pyright` clean.

- [ ] **Step 5: Commit**

```bash
git add src/sharpit/engine/capture/sqltrace.py src/sharpit/engine/capture/journal.py src/sharpit/engine/sqla/connections.py tests/engine/capture/test_connection_journal.py
git commit -m "feat: derive connection journal statement counts at check-in"
```

---

### Task 4: Update Parity Matrix Fragments and Regenerate `PARITY.md`

**Files:**
- Modify: `docs/reference/matrix-updates/w5c-I-visible-flags.tsv`
- Modify: `docs/reference/matrix-updates/w5a-P-connection.tsv`
- Modify: `scripts/dev/generate_parity_deviations.py`
- Modify: `docs/reference/PARITY.md`

**Deviation Rows (Decision 5):**

```tsv
xc:sql-trace-panel-availability	adapted	src/sharpit/engine/sqla/__init__.py:sql_trace_unavailable_reason	tests/fastapi/test_sql_trace_api.py::test_sql_trace_unavailable_when_sqlalchemy_imported_after_install_before_listeners_attach	BootUI checks recorder.hasWrappedDataSource() after SqlTraceDataSourceBeanPostProcessor wraps a Spring DataSource bean; Python has no container DataSource beans, so sharpit treats the SQL source as wrapped once SQLAlchemy statement listeners are attached (or sqlite3 is traced, or an engine is registered on an attached context) and returns "No DataSource has been wrapped for tracing yet." otherwise
journal-source:connection	adapted	src/sharpit/engine/sqla/connections.py	tests/engine/capture/test_connection_journal.py::test_connection_journal_event_offered_once_per_release_with_bootui_fields	Pool connect/checkout/checkin listeners publish ConnectionPayload on checkin with dataSource, waitNanos, statements and obtainedNanos; statements is derived at checkin from SqlTraceRecorder and RuntimeJournal cursors so executed statements pay 0.00 us per statement, falling back to -1 only when rows were evicted or unrecorded during a paused checkout
xc:insights-sqlcapture-not-recorded	adapted	src/sharpit/engine/sqla/__init__.py:sources_recorded	tests/engine/insights/test_insights_sqlrecorded.py::test_a_failed_sqlalchemy_listener_attach_with_an_engine_registered_reads_not_recorded	BootUI calls SqlTraceRecorder.registerDataSource only after DataSource proxy wrapping succeeds; sharpit rolls back sqla.add on listener attach failure and requires attached (or explicitly suspended) statement listeners before a registered engine counts as a recorded SQLAlchemy source
```

- [ ] **Step 1: Update the TSV fragments and `scripts/dev/generate_parity_deviations.py`, then regenerate `docs/reference/PARITY.md`**

Run:
```bash
uv run python scripts/dev/generate_parity_deviations.py
```

- [ ] **Step 2: Run parity and documentation tests and static gates**

Run:
```bash
uv run pytest -q -n 2 tests/test_code_shape.py tests/engine/test_import_boundary.py
uv run ruff check
uv run ruff format --check
uv run pyright
```
Expected: all checks pass.

- [ ] **Step 3: Commit**

```bash
git add docs/reference/matrix-updates/w5c-I-visible-flags.tsv docs/reference/matrix-updates/w5a-P-connection.tsv scripts/dev/generate_parity_deviations.py docs/reference/PARITY.md
git commit -m "docs: record S3 and S4 parity adaptations in matrix fragments"
```

---

## Definition of Done

- [ ] Every new or updated defect/parity test in Tasks 1–3 has been watched red via `uv run python scripts/dev/red_check.py <node ids>` before its implementation commit.
- [ ] `uv run pytest -q -n 2 tests/engine/insights/test_insights_sqlrecorded.py tests/engine/insights/test_insights_sqlcapture.py tests/fastapi/test_sql_trace_api.py tests/fastapi/test_panel_availability.py tests/fastapi/test_sql_trace_insights_api.py tests/engine/test_sqlastats.py tests/engine/capture/test_connection_journal.py tests/test_code_shape.py tests/engine/test_import_boundary.py` passes.
- [ ] `uv run pytest -q -n 0 tests/fastapi/test_sql_trace_overhead.py` passes locally and in a 10-round paired `sbx` A/B run with `~0.0 µs` paired delta.
- [ ] `uv run ruff check`, `uv run ruff format --check`, and `uv run pyright` are clean.
