# SQL listener per-statement profile (0.9.0 lane S0)

## Context and baseline

`tests/fastapi/test_sql_trace_overhead.py::test_statement_overhead_budget` guards the per-statement cost of the SQLAlchemy listener against a 50 µs budget (`ROUNDS = 45`, `PER_ROUND = 200`, warm cache hit on `select * from (select 1 as n) where n = :n`).

Paired and interleaved measurements across 10 rounds on the 2-vCPU Linux `sbx` runner (2026-11-22):

- `v0.8.0`: median **46.0 to 46.7 µs** per statement;
- `0.9.0` head: median **47.1 to 47.7 µs** per statement;
- paired head minus base: **+0.2 to +0.6 µs** (within run-to-run noise);
- run-to-run spread on `sbx`: about **±3 µs**, so a fleet run crosses the 50 µs budget at random.

**Target for lane S2:** cut the warm per-statement cost by at least **20–25% (~9–11 µs on `sbx`, ~6.5–7.5 µs on a Windows workstation)** so the `sbx` median sits at **36–38 µs** (below 40 µs), leaving **12–14 µs** of headroom below the 50 µs budget for run-to-run variance and Track J (`J3` ORM journal source).

---

## 1. Per-statement execution path

Under `test_statement_overhead_budget`, `install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])` registers one `SharpitContext` with `SqlTraceRecorder` (`recording=True`, `capture_call_site=True`, `capture_parameters=False`) and `RuntimeJournal` (`max_events=50_000`, `"sql"` enabled). The connection is opened once (`with engine.connect() as conn:`) and the statement cache and normaliser cache are warmed before timing begins.

Each `conn.execute(statement, {"n": i})` call on the attached listener passes through 35 sharpit functions/expressions across two SQLAlchemy `Engine` events:

### Phase A: `before_cursor_execute` (`src/sharpit/engine/sqla/listeners.py:77-95`)

1. `sharpit.engine.sqla.listeners.before_cursor_execute` (`listeners.py:77`)
   - `INTERNAL.get()` (`ContextVar.get`, `listeners.py:82`) — returns `False`.
2. `sharpit.engine.sqla.orm._record_relationship` (`orm.py:206`, called at `listeners.py:84`)
   - `TEST.get()` (`ContextVar.get`, `orm.py:208`) — returns `None` outside a pytest-plugin test session and exits at `orm.py:210`.
3. `sharpit.engine.sources.dispatch.recording` (`dispatch.py:140`, called at `listeners.py:85`)
   - Calls `sharpit.engine.sources.dispatch._targets` (`dispatch.py:77`, called at `dispatch.py:148`):
     - Builds `contexts = [c for r in _refs if (c := r()) is not None]` (`dispatch.py:79`, 1st list allocation + `weakref.ref.__call__`).
     - `REQUEST.get()` (`ContextVar.get`, `dispatch.py:80`) — `None` outside an HTTP request (or `RequestInfo` in `test_statement_overhead_budget_on_a_full_ring`).
     - When `info is None`: builds `held = [c for c in contexts if c.capture.engine_registry is not None and c.capture.engine_registry.holds(engine)]` (`dispatch.py:84`, 2nd list allocation), which calls `sharpit.engine.sqla.inspect.EngineRegistry.holds` (`inspect.py:321`) and allocates a generator `<genexpr>` (`inspect.py:322`) passed to `builtins.any()`.
     - Returns `held or (contexts if len(contexts) == 1 else [])` (`dispatch.py:88`).
   - Builds `routed = [c for c in _targets(engine) if source != "sqlite3" or c.settings.sql_trace_sqlite3_enabled]` (`dispatch.py:148`, 3rd list allocation).
   - Loops `for c in routed: if source not in c.capture.sql_delivered: c.capture.sql_delivered.add(source)` (`dispatch.py:149-151`).
   - Builds `[c for c in routed if _records(c) and source not in c.capture.suspended_sources]` (`dispatch.py:152`, 4th list allocation), calling `sharpit.engine.sources.dispatch._records` (`dispatch.py:103`).
4. Back in `before_cursor_execute` (`listeners.py:86-93`):
   - `time.perf_counter_ns()` (`listeners.py:88`).
   - Stores `context._sharpit_start = (started_ns, targets)` on SQLAlchemy's `DefaultExecutionContext` (`listeners.py:90`).

### Phase B: `after_cursor_execute` (`src/sharpit/engine/sqla/listeners.py:158-167`)

5. `sharpit.engine.sqla.listeners.after_cursor_execute` (`listeners.py:158`)
6. `sharpit.engine.sqla.listeners._pop_start` (`listeners.py:97`, called at `listeners.py:162`)
   - Calls `builtins.vars(context)` (`listeners.py:98`), checks `"_sharpit_start" in state` (`listeners.py:99`), and calls `state.pop("_sharpit_start")` (`listeners.py:100`).
7. `sharpit.engine.sqla.listeners._named` (`listeners.py:104`, called at `listeners.py:164`)
   - Calls `getattr(context, "compiled", None)` and `getattr(context, "compiled_parameters", None)` (`listeners.py:111`), returning `(rows[0], None)` (`listeners.py:117`).
8. `getattr(cursor, "rowcount", -1)` (`listeners.py:165`).
9. `sharpit.engine.sqla.listeners._emit` (`listeners.py:120`, called at `listeners.py:165`)
   - `duration = time.perf_counter_ns() - started` (`listeners.py:131`).
   - `connection_id = hex(id(conn.connection.dbapi_connection))` (`listeners.py:133`, invoking `Connection.connection` property -> `_ConnectionFairy.dbapi_connection` -> `id` -> `hex`).
   - Calls `sharpit.engine.sqla.dialect_source.engine_dialect(conn)` (`dialect_source.py:32`, called at `listeners.py:138`):
     - `_attribute(conn, "dialect")` (`dialect_source.py:12`, `object.__getattribute__`).
     - `_candidate(candidate)` (`dialect_source.py:24`) -> `_attribute(candidate, "name")` (`dialect_source.py:28`) -> `sharpit.engine.sqltext.dialect.dialect_of_name(name)` (`sqltext/dialect.py:64`).
   - Constructs `sharpit.engine.sources.dispatch.SqlEvent` (`NamedTuple`, 12 fields, `listeners.py:140-153`).
10. `sharpit.engine.sources.dispatch.deliver` (`dispatch.py:281`, called at `listeners.py:139`)
    - Calls `sharpit.engine.sources.dispatch._record(event, targets)` (`dispatch.py:285`) and checks `_sink` (`None`).
11. `sharpit.engine.sources.dispatch._record` (`dispatch.py:247`)
    - `info = REQUEST.get()` (`ContextVar.get`, `dispatch.py:248`, 2nd `REQUEST.get()` per statement).
    - Allocates `<genexpr>` (`dispatch.py:250`) and calls `builtins.any(c.capture.sql_trace and c.capture.sql_trace.capture_call_site for c in targets)`.
    - Calls `sharpit.engine.capture.sqltrace.call_site(None)` (`sqltrace.py:96`, called at `dispatch.py:250`):
      - `sys._getframe()` (`sqltrace.py:99`).
      - `sys.modules.get("greenlet")` (`sqltrace.py:100`); because SQLAlchemy imports `greenlet`, calls `greenlet_module.getcurrent()` and `getattr(..., "parent", None)` (`sqltrace.py:103`) on every statement before walking frames.
      - Walks ~11 frames (`call_site` -> `_record` -> `deliver` -> `_emit` -> `after_cursor_execute` -> 6 SQLAlchemy frames -> `_round`), calling `sharpit.engine.capture.frames.is_application_frame(code.co_filename)` (`frames.py:21`, `@functools.lru_cache` hit) at each frame and formatting `f"{current.f_globals.get('__name__', '?')}:{code.co_name}:{current.f_lineno}"` (`sqltrace.py:113`).
    - `thread = threading.current_thread().name` (`dispatch.py:252`).
12. `sharpit.engine.sources.dispatch._trace_text` (`dispatch.py:222`, called at `dispatch.py:258`)
    - Allocates closure `lambda ctx=ctx: application_family(ctx)` and calls `sharpit.engine.sqla.dialect_source.event_dialect` (`dialect_source.py:83`, called at `dispatch.py:227`):
      - `_attribute(event, "error")` (`dialect_source.py:86`).
      - `_event_proof(event)` (`dialect_source.py:46`):
        - `_attribute(event, "dialect")` -> `_candidate(...)` (`dialect_source.py:48`).
        - `_attribute(event, "context")` (`dialect_source.py:49`) — **`SqlEvent` has no `context` attribute, so `object.__getattribute__(event, "context")` raises and catches `AttributeError` on every statement**.
        - `_attribute(event, "engine")` (`dialect_source.py:52`).
        - `engine_dialect(engine)` (`dialect_source.py:53`) — calls `_attribute(engine, "dialect")`, `_candidate(...)`, `_attribute(d, "name")`, and `dialect_of_name(name)` a **second time** per statement, then `_agreed(proof, other)` (`dialect_source.py:40`).
13. `sharpit.engine.capture.sqltrace.SqlTraceRecorder.record` (`sqltrace.py:259`, called at `dispatch.py:230`)
    - `self._shape(sql, dialect)` (`sqltrace.py:283`, `@functools.lru_cache` hit on `functools.partial(sqltext.statement_shape, masker)`; hashing `Dialect` invokes `enum.Enum.__hash__` in Python).
    - `sharpit.engine.capture.sqltrace._truncate(shape.text, self._max_sql_length)` (`sqltrace.py:159`, called at `sqltrace.py:286`, calling `shape.text.strip()` and `len(text) <= limit`).
    - `sharpit.engine.capture.sqltrace.category_of(sql)` (`sqltrace.py:72`, called at `sqltrace.py:296`, 2nd `@functools.lru_cache` hit).
    - `time.time_ns()` (`sqltrace.py:300`, 1st wall-clock call per statement).
    - `self._slow(millis)` (`sqltrace.py:233`, called at `sqltrace.py:313`).
    - Builds 20-key `row` dict (`sqltrace.py:298-322`).
    - Under `with self._lock:` (`threading.RLock`, `sqltrace.py:323`): assigns `next(self._ids)`, appends `row` to `self._entries` (`deque`), increments counters, looks up `self._aggregates.get(key)` and calls `self._aggregates.move_to_end(key)` (`OrderedDict`, `sqltrace.py:335-349`).
    - Calls `self.changes.signal()` (`streams.py:195`, called at `sqltrace.py:350`) -> forwards to `activity` `ChangeStream.signal()` -> calls `_Hub.signal()` (`streams.py:170`) twice.
14. `sharpit.engine.sources.dispatch._journal_event` (`dispatch.py:174`, called at `dispatch.py:265`)
    - Calls `sharpit.engine.otel.current_trace_id()` (`otel.py:51`, called at `dispatch.py:189`): because `import fastapi` imports `fastapi.telemetry`, which imports `opentelemetry.trace` whenever `opentelemetry-api` is installed, `sys.modules.get("opentelemetry.trace")` is non-`None` and calls `trace.get_current_span().get_span_context()` on every statement.
    - `time.time_ns() // 1_000_000 - event.duration_ns // 1_000_000` (`dispatch.py:192`, 2nd `time.time_ns()` call per statement).
    - Calls `sharpit.engine.sources.dispatch._batch(event)` (`dispatch.py:164`, called at `dispatch.py:208`).
    - Builds 15-key `record` dict and computes `size` (`dispatch.py:193-218`).
15. `sharpit.engine.capture.journal.RuntimeJournal.offer_flat` (`journal.py:276`, called at `dispatch.py:266`)
    - Allocates closure `lambda stored: (stored, size, started)` (`journal.py:286`).
    - Calls `RuntimeJournal._offer` (`journal.py:288`): checks `self._owned()` (`RLock._is_owned`) and `getattr(self._copying, "active", False)` (`threading.local`), sets `self._copying.active = True`, reads `event.get("source")`, invokes the lambda closure `store(event)`, resets `self._copying.active = False`, and acquires `with self._lock:`.
    - Calls `RuntimeJournal._append` (`journal.py:311`): checks `self._accepting` and `source not in self.sources`, calls `time.time_ns() // 1_000_000` (`journal.py:316`, 3rd `time.time_ns()` call per statement), evicts oldest events when at `max_events` or `max_bytes`, appends `(stored, size, stamp, started)` to `self._events` (`deque`), and increments `self._accepted[source] += 1` (`Counter`).

---

## 2. Profile results (20,000 statements per side, 3 runs, `-n 0`)

Generated with `uv run python -m scripts.dev.profile_sql_listener --statements 20000 --runs 3` on Windows 11 (CPython 3.13.7, SQLAlchemy 2.1.6, `-n 0`, ambient CPU load ~15%).

### 2.1 Uninstrumented paired overhead (20,000 statements/side = 100 alternating rounds × 200 statements)

| Mode | Run 1 overhead (noise) | Run 2 overhead (noise) | Run 3 overhead (noise) | Median overhead |
|---|---:|---:|---:|---:|
| Default journal ring (`max_events=50,000`, `REQUEST=None`) | 33.212 µs (1.903 µs) | 35.669 µs (6.139 µs) | 33.513 µs (6.656 µs) | **33.513 µs** |
| Full journal ring (`max_events=64`, `REQUEST` set) | 31.681 µs (0.848 µs) | 32.504 µs (3.040 µs) | 33.137 µs (1.266 µs) | **32.504 µs** |

*(Note: `test_statement_overhead_budget_on_a_full_ring` is ~1.0 µs faster than the default ring despite running the journal eviction loop on every statement because `REQUEST` is set, which causes `dispatch._targets` to short-circuit before `EngineRegistry.holds(engine)`.)*

### 2.2 Per-function `cProfile` cost table (20,000 statements/side, 3 runs)

Shares are percentages of total sharpit listener cumulative time (`before_cursor_execute` + `after_cursor_execute` `cumtime`: Run 1 = `77.10 µs/stmt`, Run 2 = `75.48 µs/stmt`, Run 3 = `70.49 µs/stmt`). Every relative share is stable to within **±0.2 percentage points** across all three runs.

| # | Function (`src/sharpit/...`) | Calls / 20k stmts | Calls / stmt | Self (`tottime`) / stmt (R1 / R2 / R3) | Cum (`cumtime`) / stmt (R1 / R2 / R3) | Self share % (R1 / R2 / R3) | Cum share % (R1 / R2 / R3) |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `engine/capture/sqltrace.py:259:record` | 20,000 | 1 | 9.291 / 9.159 / 8.485 µs | 16.174 / 15.871 / 14.705 µs | **12.1 / 12.1 / 12.0%** | 21.0 / 21.0 / 20.9% |
| 2 | `engine/capture/sqltrace.py:96:call_site` | 20,000 | 1 | 5.053 / 4.997 / 4.641 µs | 5.741 / 5.660 / 5.272 µs | **6.6 / 6.6 / 6.6%** | 7.4 / 7.5 / 7.5% |
| 3 | `engine/sources/dispatch.py:247:_record` | 20,000 | 1 | 4.193 / 4.083 / 3.807 µs | 55.395 / 54.236 / 50.644 µs | **5.4 / 5.4 / 5.4%** | 71.8 / 71.9 / 71.8% |
| 4 | `engine/sqla/dialect_source.py:12:_attribute` | 160,000 | 8 | 3.988 / 3.920 / 3.568 µs | 3.988 / 3.920 / 3.568 µs | **5.2 / 5.2 / 5.1%** | 5.2 / 5.2 / 5.1% |
| 5 | `engine/sources/dispatch.py:174:_journal_event` | 20,000 | 1 | 3.072 / 3.018 / 2.824 µs | 8.473 / 8.207 / 7.716 µs | **4.0 / 4.0 / 4.0%** | 11.0 / 10.9 / 10.9% |
| 6 | `engine/sqla/listeners.py:120:_emit` | 20,000 | 1 | 3.070 / 3.011 / 2.815 µs | 64.023 / 62.717 / 58.531 µs | **4.0 / 4.0 / 4.0%** | 83.0 / 83.1 / 83.0% |
| 7 | `engine/capture/journal.py:288:_offer` | 20,000 | 1 | 2.818 / 2.766 / 2.591 µs | 7.662 / 7.501 / 7.074 µs | **3.7 / 3.7 / 3.7%** | 9.9 / 9.9 / 10.0% |
| 8 | `engine/capture/journal.py:311:_append` | 20,000 | 1 | 2.636 / 2.579 / 2.470 µs | 3.472 / 3.384 / 3.241 µs | **3.4 / 3.4 / 3.5%** | 4.5 / 4.5 / 4.6% |
| 9 | `engine/sqla/dialect_source.py:24:_candidate` | 60,000 | 3 | 2.065 / 2.012 / 1.905 µs | 4.126 / 4.044 / 3.804 µs | **2.7 / 2.7 / 2.7%** | 5.4 / 5.4 / 5.4% |
| 10 | `engine/capture/streams.py:195:signal` (`ChangeStream`) | 40,000 | 2 | 1.866 / 1.868 / 1.706 µs | 2.148 / 2.144 / 1.961 µs | **2.4 / 2.5 / 2.4%** | 2.8 / 2.8 / 2.8% |
| 11 | `engine/sqla/dialect_source.py:46:_event_proof` | 20,000 | 1 | 1.846 / 1.864 / 1.717 µs | 7.320 / 7.224 / 6.698 µs | **2.4 / 2.5 / 2.4%** | 9.5 / 9.6 / 9.5% |
| 12 | `engine/sources/dispatch.py:222:_trace_text` | 20,000 | 1 | 1.818 / 1.750 / 1.609 µs | 26.474 / 25.982 / 24.090 µs | **2.4 / 2.3 / 2.3%** | 34.3 / 34.4 / 34.2% |
| 13 | `engine/sqla/listeners.py:77:before_cursor_execute` | 20,000 | 1 | 1.730 / 1.718 / 1.566 µs | 8.182 / 8.033 / 7.457 µs | **2.2 / 2.3 / 2.2%** | 10.6 / 10.6 / 10.6% |
| 14 | `engine/sources/dispatch.py:77:_targets` | 20,000 | 1 | 1.667 / 1.632 / 1.514 µs | 3.597 / 3.548 / 3.299 µs | **2.2 / 2.2 / 2.1%** | 4.7 / 4.7 / 4.7% |
| 15 | `engine/sqla/listeners.py:158:after_cursor_execute` | 20,000 | 1 | 1.572 / 1.538 / 1.468 µs | 68.920 / 67.449 / 63.038 µs | **2.0 / 2.0 / 2.1%** | 89.4 / 89.4 / 89.4% |
| 16 | `engine/sources/dispatch.py:141:recording` | 20,000 | 1 | 1.504 / 1.453 / 1.374 µs | 5.451 / 5.326 / 4.981 µs | **2.0 / 1.9 / 1.9%** | 7.1 / 7.1 / 7.1% |
| 17 | `engine/otel.py:51:current_trace_id` | 20,000 | 1 | 1.382 / 1.342 / 1.274 µs | 4.501 / 4.311 / 4.076 µs | **1.8 / 1.8 / 1.8%** | 5.8 / 5.7 / 5.8% |
| 18 | `engine/sqla/dialect_source.py:32:engine_dialect` | 40,000 | 2 | 1.320 / 1.290 / 1.226 µs | 6.114 / 5.964 / 5.582 µs | **1.7 / 1.7 / 1.7%** | 7.9 / 7.9 / 7.9% |
| 19 | `engine/sqla/listeners.py:97:_pop_start` | 20,000 | 1 | 1.082 / 1.033 / 0.991 µs | 2.014 / 1.922 / 1.818 µs | **1.4 / 1.4 / 1.4%** | 2.6 / 2.5 / 2.6% |
| 20 | `engine/sqla/inspect.py:321:holds` | 20,000 | 1 | 0.948 / 0.948 / 0.883 µs | 1.798 / 1.777 / 1.660 µs | **1.2 / 1.3 / 1.3%** | 2.3 / 2.4 / 2.4% |
| 21 | `engine/capture/journal.py:276:offer_flat` | 20,000 | 1 | 0.912 / 0.893 / 0.844 µs | 8.574 / 8.394 / 7.918 µs | **1.2 / 1.2 / 1.2%** | 11.1 / 11.1 / 11.2% |
| 22 | `engine/sqltext/dialect.py:64:dialect_of_name` | 40,000 | 2 | 0.884 / 0.872 / 0.823 µs | 1.444 / 1.437 / 1.338 µs | **1.1 / 1.2 / 1.2%** | 1.9 / 1.9 / 1.9% |
| 23 | `engine/sqla/listeners.py:104:_named` | 20,000 | 1 | 0.783 / 0.761 / 0.731 µs | 1.127 / 1.089 / 1.049 µs | **1.0 / 1.0 / 1.0%** | 1.5 / 1.4 / 1.5% |
| 24 | `engine/sqla/dialect_source.py:83:event_dialect` | 20,000 | 1 | 0.772 / 0.756 / 0.724 µs | 8.483 / 8.361 / 7.776 µs | **1.0 / 1.0 / 1.0%** | 11.0 / 11.1 / 11.0% |
| 25 | `engine/capture/sqltrace.py:159:_truncate` | 20,000 | 1 | 0.702 / 0.654 / 0.623 µs | 1.100 / 1.043 / 0.987 µs | **0.9 / 0.9 / 0.9%** | 1.4 / 1.4 / 1.4% |
| 26 | `engine/sources/dispatch.py:281:deliver` | 20,000 | 1 | 0.666 / 0.662 / 0.595 µs | 56.061 / 54.898 / 51.239 µs | **0.9 / 0.9 / 0.8%** | 72.7 / 72.7 / 72.7% |
| 27 | `engine/sqla/orm.py:206:_record_relationship` | 20,000 | 1 | 0.412 / 0.422 / 0.375 µs | 0.551 / 0.557 / 0.511 µs | **0.5 / 0.6 / 0.5%** | 0.7 / 0.7 / 0.7% |
| 28 | `engine/sources/dispatch.py:250:<genexpr>` | 20,000 | 1 | 0.390 / 0.379 / 0.390 µs | 0.390 / 0.379 / 0.390 µs | **0.5 / 0.5 / 0.6%** | 0.5 / 0.5 / 0.6% |
| 29 | `engine/sqla/inspect.py:322:<genexpr>` | 20,000 | 1 | 0.390 / 0.378 / 0.355 µs | 0.390 / 0.378 / 0.355 µs | **0.5 / 0.5 / 0.5%** | 0.5 / 0.5 / 0.5% |
| 30 | `engine/sources/dispatch.py:103:_records` | 20,000 | 1 | 0.349 / 0.325 / 0.309 µs | 0.349 / 0.325 / 0.309 µs | **0.5 / 0.4 / 0.4%** | 0.5 / 0.4 / 0.4% |
| 31 | `engine/capture/sqltrace.py:233:_slow` | 20,000 | 1 | 0.286 / 0.279 / 0.265 µs | 0.286 / 0.279 / 0.265 µs | **0.4 / 0.4 / 0.4%** | 0.4 / 0.4 / 0.4% |
| 32 | `engine/capture/streams.py:169:signal` (`_Hub`) | 40,000 | 2 | 0.282 / 0.276 / 0.255 µs | 0.282 / 0.276 / 0.255 µs | **0.4 / 0.4 / 0.4%** | 0.4 / 0.4 / 0.4% |
| 33 | `engine/sources/dispatch.py:164:_batch` | 20,000 | 1 | 0.219 / 0.213 / 0.201 µs | 0.219 / 0.213 / 0.201 µs | **0.3 / 0.3 / 0.3%** | 0.3 / 0.3 / 0.3% |
| 34 | `engine/sqla/dialect_source.py:40:_agreed` | 20,000 | 1 | 0.208 / 0.203 / 0.196 µs | 0.208 / 0.203 / 0.196 µs | **0.3 / 0.3 / 0.3%** | 0.3 / 0.3 / 0.3% |
| 35 | `engine/capture/journal.py:286:<lambda>` | 20,000 | 1 | 0.189 / 0.183 / 0.170 µs | 0.189 / 0.183 / 0.170 µs | **0.2 / 0.2 / 0.2%** | 0.2 / 0.2 / 0.2% |

*(Note: `SqlTraceRecorder._shape` at `sqltrace.py:200`, `category_of` at `sqltrace.py:72`, and `is_application_frame` at `frames.py:21` are wrapped in `@functools.lru_cache`; on warm cache hits CPython's C `_lru_cache_wrapper` returns without entering the Python function frame, so their cache-lookup cost is included in the `tottime` of `SqlTraceRecorder.record` and `call_site`.)*

### 2.3 Top 10 sharpit functions by self-time share (and top direct non-sharpit callees)

#### Top 10 sharpit functions by self-time share (across 3 runs)

| Rank (R1 / R2 / R3) | Function | Calls / stmt | Median self share | Median cum share | Subsystem |
|---:|---|---:|---:|---:|---|
| 1 / 1 / 1 | `engine/capture/sqltrace.py:259:record` | 1 | **12.1%** | 21.0% | Recorder ring + aggregate update |
| 2 / 2 / 2 | `engine/capture/sqltrace.py:96:call_site` | 1 | **6.6%** | 7.5% | Stack frame walk (11 frames) |
| 3 / 3 / 3 | `engine/sources/dispatch.py:247:_record` | 1 | **5.4%** | 71.8% | Per-target dispatch + thread/site setup |
| 4 / 4 / 4 | `engine/sqla/dialect_source.py:12:_attribute` | 8 | **5.2%** | 5.2% | Dialect resolution (`object.__getattribute__`) |
| 5 / 5 / 5 | `engine/sources/dispatch.py:174:_journal_event` | 1 | **4.0%** | 10.9% | SQL journal event dict + size calculation |
| 6 / 6 / 6 | `engine/sqla/listeners.py:120:_emit` | 1 | **4.0%** | 83.0% | `connection_id`, `engine_dialect(conn)`, `SqlEvent` |
| 7 / 7 / 7 | `engine/capture/journal.py:288:_offer` | 1 | **3.7%** | 9.9% | Journal reentrancy guard + `_copying.active` + lock |
| 8 / 8 / 8 | `engine/capture/journal.py:311:_append` | 1 | **3.4%** | 4.5% | Journal ring append + timestamp + `Counter` update |
| 9 / 9 / 9 | `engine/sqla/dialect_source.py:24:_candidate` | 3 | **2.7%** | 5.4% | Dialect `.name` extraction and validation |
| 10 / 10 / 10* | `engine/capture/streams.py:195:signal` / `dialect_source.py:46:_event_proof` | 2 / 1 | **2.4%** / **2.4%** | 2.8% / 9.5% | Stream tick forwarding / 3-holder dialect proof |

#### Top 10 direct non-sharpit callees invoked by sharpit listener functions

| Rank | Callee (and sharpit caller) | Calls / 20k stmts | Median cum / stmt | Median share % |
|---:|---|---:|---:|---:|
| 1 | `opentelemetry/trace/propagation/__init__.py:24:get_current_span` (from `otel.py:51:current_trace_id`) | 20,000 | 2.401 µs | **3.2%** |
| 2 | `builtins.any` (from `sqla/inspect.py:321:holds`) | 20,000 | 0.829 µs | **1.1%** |
| 3 | `sqlalchemy/engine/base.py:connection` property (from `sqla/listeners.py:120:_emit`) | 20,000 | 0.826 µs | **1.1%** |
| 4 | `builtins.any` (from `sources/dispatch.py:247:_record`) | 20,000 | 0.788 µs | **1.0%** |
| 5 | `threading.py:1429:current_thread` (from `sources/dispatch.py:247:_record`) | 20,000 | 0.700 µs | **0.9%** |
| 6 | `collections.deque.append` (from `capture/sqltrace.py:259:record`) | 20,000 | 0.601 µs | **0.8%** |
| 7 | `enum.py:1312:Enum.__hash__` (from `capture/sqltrace.py:259:record` via `_shape(sql, dialect)`) | 20,000 | 0.560 µs | **0.7%** |
| 8 | `mappingproxy.get` (from `sqltext/dialect.py:64:dialect_of_name`) | 40,000 | 0.560 µs | **0.7%** |
| 9 | `dict.get` (from `capture/sqltrace.py:96:call_site`) | 40,000 | 0.444 µs | **0.6%** |
| 10 | `builtins.vars` (from `sqla/listeners.py:97:_pop_start`) | 20,000 | 0.440 µs | **0.6%** |

### 2.4 Direct `time.perf_counter_ns` component timings (20,000 iterations, 3 runs)

| Stage / Function | Run 1 | Run 2 | Run 3 | Median |
|---|---:|---:|---:|---:|
| SQLAlchemy `Engine` event-dispatch floor (no-op `before` + `after` listeners) | 1.599 µs | 2.289 µs | -0.337 µs | **1.599 µs** |
| `listeners.before_cursor_execute` (total) | 1.431 µs | 1.475 µs | 1.441 µs | **1.441 µs** |
| — `INTERNAL.get()` | 0.032 µs | 0.033 µs | 0.031 µs | **0.032 µs** |
| — `orm._record_relationship(context)` | 0.177 µs | 0.111 µs | 0.108 µs | **0.111 µs** |
| — `dispatch.recording(conn.engine)` | 0.949 µs | 1.046 µs | 1.049 µs | **1.046 µs** |
|   — `dispatch._targets(conn.engine)` | 0.683 µs | 0.673 µs | 0.690 µs | **0.683 µs** |
|   — `EngineRegistry.holds(conn.engine)` | 0.320 µs | 0.326 µs | 0.335 µs | **0.326 µs** |
| `listeners._pop_start(conn, context)` | 0.246 µs | 0.330 µs | 0.282 µs | **0.282 µs** |
| `listeners._named(parameters, context, False)` | 0.189 µs | 0.192 µs | 0.178 µs | **0.189 µs** |
| `hex(id(conn.connection.dbapi_connection))` | 0.186 µs | 0.134 µs | 0.120 µs | **0.134 µs** |
| `dialect_source.engine_dialect(conn)` | 0.424 µs | 0.492 µs | 0.425 µs | **0.425 µs** |
| `dispatch.SqlEvent(...)` | 0.430 µs | 0.456 µs | 0.364 µs | **0.430 µs** |
| `sqltrace.call_site(None)` (at real `conn.execute` stack depth = 10 frames) | 1.427 µs | 1.522 µs | 1.466 µs | **1.466 µs** |
| `threading.current_thread().name` | 0.110 µs | 0.155 µs | 0.118 µs | **0.118 µs** |
| `dialect_source.event_dialect(event, ...)` | 1.646 µs | 2.065 µs | 1.697 µs | **1.697 µs** |
| `SqlTraceRecorder.record(...)` | 2.739 µs | 3.259 µs | 2.737 µs | **2.739 µs** |
| — `recorder._shape(sql, dialect)` (`lru_cache` hit) | 0.144 µs | 0.187 µs | 0.232 µs | **0.187 µs** |
| — `_truncate(shape.text, max_sql_length)` | 0.100 µs | 0.125 µs | 0.145 µs | **0.125 µs** |
| — `category_of(sql)` (`lru_cache` hit) | 0.108 µs | 0.085 µs | 0.075 µs | **0.085 µs** |
| — `time.time_ns()` | 0.059 µs | 0.079 µs | 0.070 µs | **0.070 µs** |
| `dispatch._journal_event(...)` | 1.144 µs | 1.495 µs | 1.239 µs | **1.239 µs** |
| — `otel.current_trace_id()` | 0.313 µs | 0.503 µs | 0.346 µs | **0.346 µs** |
| `RuntimeJournal.offer_flat(record, size, started)` | 1.572 µs | 1.556 µs | 1.633 µs | **1.572 µs** |

---

## 3. Ranked cuts (measured with interleaved paired runs)

Every candidate cut below was measured in an interleaved paired harness (`tests.overhead.paired`, 60 rounds × 500 calls, 3 repetitions) and in an end-to-end 3-way interleaved `conn.execute` benchmark (`off` vs `baseline on` vs `cuts on`, 100 rounds × 200 statements = 20,000 statements per side, 3 repetitions).

### Summary table of ranked cuts

| Rank | Where (`src/sharpit/...`) | Cause of cost | Proposed change | Measured local saving (3-run median) | Expected `sbx` saving (~47.4 µs base) | Safety-model risk |
|---:|---|---|---|---:|---:|---|
| **1** | `engine/sqla/dialect_source.py:46-54,83-89`, `engine/sqla/listeners.py:138`, `engine/sources/dispatch.py:227` | 8 `_attribute` calls (`object.__getattribute__`), 3 `_candidate` calls, 2 `engine_dialect` calls, 1 closure allocation, and 1 raised/caught `AttributeError` (`event.context` on `SqlEvent`) per statement (15.1% of `cProfile` time) | Read `conn.dialect` and `conn.engine.dialect` once in `_emit`; when they are the same object (`is`), resolve `_candidate` once; fast-path `type(event) is SqlEvent` in `event_dialect` without `AttributeError` on `"context"` | **1.00 µs/stmt** (1.76 -> 0.76 µs) | **~1.7–2.2 µs/stmt** | None: still reads both `conn.dialect` and `engine.dialect` on every statement with no cache or lock; custom/host objects still go through `_attribute` |
| **2** | `engine/capture/sqltrace.py:96-115`, `engine/sources/dispatch.py:250` | `call_site(None)` unconditionally calls `sys.modules.get("greenlet")` + `greenlet.getcurrent().parent` on every statement and materializes 5 `PyFrameObject` heap wrappers for sharpit's own frames (`call_site`, `_record`, `deliver`, `_emit`, `after_cursor_execute`) before reaching SQLAlchemy (7.5% of `cProfile` time) | Start at `sys._getframe(5)` when `frame is None` (falling back to `sys._getframe(1)` on `ValueError` for 1-frame greenlets) and defer the `greenlet` lookup to the `if current is None:` branch | **0.62 µs/stmt** (1.14 -> 0.52 µs) | **~1.3–1.8 µs/stmt** | None: frame classification rule (`is_application_frame`) is unchanged |
| **3** | `engine/sources/dispatch.py:77-89,140-153` | `dispatch.recording` allocates 4 intermediate lists per statement, and `_targets` calls `EngineRegistry.holds(engine)` (allocating `<genexpr>` + `builtins.any`) even when `len(contexts) == 1`, where `_targets` returns `contexts` regardless of `holds(engine)` (7.1% of `cProfile` time) | In `_targets`, return `contexts` immediately when `info is None and len(contexts) <= 1`; collapse the 3 list comprehensions in `recording` into one loop | **0.54 µs/stmt** (0.83 -> 0.28 µs) | **~1.1–1.5 µs/stmt** | None: `holds(engine)` is pure and still runs whenever `len(contexts) > 1` |
| **4** | `engine/capture/sqltrace.py:200,283-350`, `engine/capture/streams.py:195-198`, `engine/sqltext/dialect.py:13` | `SqlTraceRecorder.record` makes 2 separate `lru_cache` calls (`_shape` and `category_of`), hashes `Dialect` via Python `Enum.__hash__` (0.56 µs in `cProfile`), runs `_truncate(shape.text)` (`str.strip`) on every cache hit, calls `move_to_end` on a 1-item `OrderedDict`, and calls `ChangeStream.signal` -> `super().signal()` twice when no SSE subscribers exist (23.8% of `cProfile` time) | Cache `(shape, truncated_text, category)` in one per-recorder `lru_cache`, set `__hash__ = object.__hash__` on `Dialect`, skip `move_to_end` when `len(_aggregates) <= 1`, and guard `ChangeStream.signal` with `if self._subscribers:` | **0.42 µs/stmt** (1.81 -> 1.40 µs) | **~1.0–1.5 µs/stmt** | None: cache remains per-`SqlTraceRecorder` instance (bound to its `Masker` and `_max_sql_length`) |
| **5** | `engine/capture/journal.py:276-336` | `RuntimeJournal.offer_flat` allocates a lambda closure `lambda stored: (stored, size, started)` and toggles `threading.local()` `self._copying.active = True` / `False` on every statement even when `size >= 1` (no host `__repr__` or copy runs) (11.1% of `cProfile` time) | When `size is not None and size >= 1`, check `self._owned() or getattr(self._copying, "active", False)` and `isinstance(source, str)`, then acquire `self._lock` and call `self._append((event, size, started), source)` directly | **0.26 µs/stmt** (1.23 -> 0.97 µs) | **~0.6–0.9 µs/stmt** | None: reentrancy check (`_owned()` and `_copying.active`), source validation, and read-time masking are unchanged |
| **6** | `engine/sqla/listeners.py:97-101`, `engine/sources/dispatch.py:247-252` | `_pop_start` calls `vars(context)`, `"_sharpit_start" in state`, and `state.pop(...)`; `dispatch._record` allocates a `<genexpr>` and calls `builtins.any(...)` per statement to check `capture_call_site` (3.6% of `cProfile` time) | Use `context.__dict__.pop("_sharpit_start", None)` in `_pop_start` and a direct loop over `targets` in `dispatch._record` | **0.27 µs/stmt** (0.44 -> 0.17 µs) | **~0.5–0.8 µs/stmt** | None |
| **7** | `engine/otel.py:51-60`, `engine/sources/dispatch.py:189` | `import fastapi` loads `fastapi.telemetry`, which imports `opentelemetry.trace` whenever `opentelemetry-api` is installed; `otel.current_trace_id()` sees `"opentelemetry.trace"` in `sys.modules` and calls `trace.get_current_span().get_span_context()` on every statement even when `_TRACER_PROVIDER` is `None` (5.8% of `cProfile` time) | Return `None` immediately when `trace.__dict__.get("_TRACER_PROVIDER", _MISSING) is None` (no provider configured on the real OTel module) | **0.14 µs/stmt** (0.21 -> 0.08 µs; 4.3 µs in `cProfile`) | **~0.3–0.6 µs/stmt** | None: fake `ModuleType("opentelemetry.trace")` objects in tests have no `_TRACER_PROVIDER` key (or set it non-`None`) and continue to resolve |

### End-to-end interleaved verification of Cuts 1–7 combined

Running all 7 cuts together against the unmodified baseline in a 3-way interleaved loop (`off`, `baseline on`, `cuts on` within each of 100 rounds × 200 statements = 20,000 statements per side, 3 runs):

| Run | `off` min | Baseline `on` min | Baseline overhead (`on - off`) | Cuts 1–7 `on` min | Cuts 1–7 overhead (`on - off`) | Net saving | Relative reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| Run 1 | 16.03 µs | 44.82 µs | **28.79 µs** | 37.85 µs | **21.82 µs** | **+6.97 µs** | **24.2%** |
| Run 2 | 15.92 µs | 44.77 µs | **28.85 µs** | 37.89 µs | **21.97 µs** | **+6.88 µs** | **23.9%** |
| Run 3 | 16.40 µs | 44.75 µs | **28.35 µs** | 37.78 µs | **21.38 µs** | **+6.97 µs** | **24.6%** |
| **Median** | **16.03 µs** | **44.77 µs** | **28.79 µs** | **37.85 µs** | **21.82 µs** | **+6.97 µs** | **24.2%** |

*(Note: the end-to-end saving of **+6.97 µs** exceeds the sum of the isolated micro-benchmarks [**+3.25 µs**] because eliminating 7 per-statement heap allocations [3 intermediate lists in `recording`, 2 generator frames in `holds` and `_record`, 2 lambda closures in `_trace_text` and `offer_flat`, and 5 `PyFrameObject` wrappers in `call_site`] and cutting 15 function calls per statement reduces `pymalloc` / free-list churn and instruction-cache eviction across the surrounding SQLAlchemy execution loop.)*

---

## 4. Detailed cut specifications and existing test coverage

### Cut 1: Single-pass connection/engine dialect verification and `SqlEvent` fast path
- **Files and lines:**
  - `src/sharpit/engine/sqla/listeners.py:138-153` (`_emit`)
  - `src/sharpit/engine/sqla/dialect_source.py:32-54, 83-89` (`engine_dialect`, `_event_proof`, `event_dialect`)
  - `src/sharpit/engine/sources/dispatch.py:222-227` (`_trace_text`)
- **Why it costs:**
  - `_emit` calls `engine_dialect(conn)` (`_attribute(conn, "dialect")` -> `_candidate` -> `_attribute(d, "name")` -> `dialect_of_name`).
  - `_trace_text` then calls `event_dialect(event, lambda ctx=ctx: application_family(ctx))`, which calls `_attribute(event, "error")`, `_attribute(event, "dialect")`, `_candidate(...)`, `_attribute(event, "context")` (which **raises and catches `AttributeError`** on every `SqlEvent` because `SqlEvent` has no `context` field), `_attribute(event, "engine")`, and `engine_dialect(engine)` (re-reading `engine.dialect.name` even though `conn.dialect is conn.engine.dialect` on every normal SQLAlchemy connection).
- **The change:**
  - Add a helper in `dialect_source.py` (e.g., `connection_dialect(conn, engine)`) that reads `c_dial = _attribute(conn, "dialect")` and `e_dial = _attribute(engine, "dialect")` once per statement. When `c_dial is e_dial` (the same dialect instance), compute `_candidate(c_dial)` once instead of twice; when they differ (e.g., `engine.dialect` was replaced after `conn` opened), return `_agreed(_candidate(c_dial), _candidate(e_dial))`.
  - In `event_dialect`, when `type(event) is SqlEvent` and `event.error is None`, read `event.dialect` and `event.engine` directly without calling `object.__getattribute__(event, "context")`.
- **Safety-model check:**
  - No dialect caching across statements: `conn.dialect` and `conn.engine.dialect` are still read via `_attribute` (`object.__getattribute__`) on every statement, so a replaced dialect (`engine.dialect = ...`) or mutated `engine.dialect.name` or hostile `str` subclass on `name` is detected immediately and fails closed to `Dialect.UNSUPPORTED`.
  - Custom event objects in unit tests (`type(event) is not SqlEvent`) still run the full `_attribute` checks on `dialect`, `context`, `engine`, and `error`.
- **Existing tests that prove behaviour is unchanged:**
  - `tests/engine/sqltext/test_resolver.py::test_engine_event_candidates_conflict`
  - `tests/engine/sqltext/test_resolver.py::test_an_event_with_no_error_never_reaches_the_exception_source`
  - `tests/engine/sqltext/test_resolver.py::test_a_statement_that_proves_its_family_never_reads_the_application`
  - `tests/engine/sqltext/test_resolver.py::test_a_disagreeing_engine_hides_an_event_with_no_error`
  - `tests/engine/sqltext/test_resolver.py::test_a_disagreeing_context_hides_an_agreeing_event`
  - `tests/engine/sqltext/test_resolver.py::test_an_event_field_that_cannot_be_read_hides`
  - `tests/engine/sqltext/test_resolver.py::test_engine_dialect_follows_a_changed_name`
  - `tests/engine/sqltext/test_resolver.py::test_engine_dialect_follows_a_replaced_dialect`
  - `tests/engine/sqltext/test_resolver.py::test_a_name_string_subclass_runs_no_code_and_hides`
  - `tests/engine/test_application_family.py::test_a_statement_on_a_connection_older_than_the_engine_dialect_hides`

### Cut 2: Skip sharpit's internal frames in C and defer `greenlet` lookup in `call_site`
- **Files and lines:**
  - `src/sharpit/engine/capture/sqltrace.py:96-115` (`call_site`)
- **Why it costs:**
  - When `frame is None`, `sys._getframe()` starts at frame 0 (`call_site`) and walks through `_record`, `deliver`, `_emit`, and `after_cursor_execute` in Python, allocating a `PyFrameObject` on the heap for each of those 5 sharpit frames and calling `is_application_frame(code.co_filename)` on each one.
  - Because SQLAlchemy imports `greenlet`, `sys.modules.get("greenlet")` is always non-`None`, so `call_site` calls `greenlet_module.getcurrent()` and `getattr(..., "parent", None)` on every statement even though `parent` is only used inside `if current is None:` when a child greenlet exhausts its own frames without finding an application frame.
- **The change:**
  - When `frame is None` (called from `dispatch._record`), start with `sys._getframe(5)` (or pass the starting depth from `_record`, falling back to `sys._getframe(1)` on `ValueError` for shallow stacks such as `test_call_site_follows_greenlet_parent` where `call_site` is the root frame of a child greenlet). CPython's `sys._getframe(depth)` walks `_PyInterpreterFrame->previous` pointers in C without allocating intermediate `PyFrameObject` heap wrappers.
  - Move `sys.modules.get("greenlet")` and `greenlet_module.getcurrent().parent` inside the `if current is None:` branch, guarded by a `greenlet_checked = False` flag.
- **Negative finding (do not do in S2):**
  - Do **not** replace `is_application_frame(code.co_filename)` (`@functools.lru_cache` keyed by `str`) with an `@functools.lru_cache` keyed by `CodeType` (`current.f_code`). Paired measurement showed `@lru_cache` on `CodeType` **adds +10.4 µs/stmt** (`1.68 µs -> 12.07 µs`) because CPython's `PyCodeObject` does not cache its hash (`code_hash` hashes `co_name`, `co_code`, `co_consts`, `co_names`, `co_varnames`, etc. on every lookup), whereas `str` caches `ob_shash` in `PyASCIIObject`.
- **Safety-model check:**
  - None (`call_site` only inspects code file paths and formats `module:function:line`).
- **Existing tests that prove behaviour is unchanged:**
  - `tests/engine/capture/test_sqltrace.py::test_call_site_is_first_application_frame`
  - `tests/engine/capture/test_sqltrace.py::test_call_site_follows_greenlet_parent`
  - `tests/engine/capture/test_sqltrace.py::test_call_site_without_greenlet`
  - `tests/engine/capture/test_sqltrace.py::test_call_site_walk_is_bounded`
  - `tests/engine/capture/test_sqltrace.py::test_call_site_off_ignores_given_call_site`

### Cut 3: Short-circuit single-context routing in `dispatch._targets` and `dispatch.recording`
- **Files and lines:**
  - `src/sharpit/engine/sources/dispatch.py:77-89` (`_targets`), `140-153` (`recording`)
- **Why it costs:**
  - In `_targets(engine)` (`dispatch.py:83-88`):
    ```python
    held = (
        [c for c in contexts if c.capture.engine_registry is not None and c.capture.engine_registry.holds(engine)]
        if engine is not None
        else []
    )
    return held or (contexts if len(contexts) == 1 else [])
    ```
    When `info is None` and `len(contexts) == 1` (the normal single-install case), `_targets(engine)` **always returns `contexts`** whether `holds(engine)` is `True` (`held = [contexts[0]]`) or `False` (`held = []`, falling back to `contexts if len(contexts) == 1`). Calling `EngineRegistry.holds(engine)` (which allocates a generator `<genexpr>` and calls `builtins.any()`) when `len(contexts) == 1` is pure dead work.
  - `recording()` allocates 3 additional list comprehensions (`contexts`, `routed`, and the final filtered list) on every statement.
- **The change:**
  - In `_targets(engine)`, when `info is None and len(contexts) <= 1`, return `contexts` immediately without calling `EngineRegistry.holds(engine)`.
  - In `recording(engine, source)`, filter and mark `sql_delivered` in a single loop over `_targets(engine)`.
- **Safety-model check:**
  - `EngineRegistry.holds(engine)` has no side effects. When `len(contexts) > 1` (multiple contexts installed in one process), `_targets(engine)` still filters by `holds(engine)`.
- **Existing tests that prove behaviour is unchanged:**
  - `tests/engine/test_sqla.py::test_statement_outside_request_routed_by_registry`
  - `tests/engine/test_application_family.py::test_raw_sqlite_seen_respects_request_context`
  - `tests/engine/capture/test_sql_journal.py::test_sql_journal_event_carries_the_request_id_of_this_install_only`

### Cut 4: Single per-recorder statement cache entry, `Dialect` identity hash, and inline `ChangeStream.signal` check
- **Files and lines:**
  - `src/sharpit/engine/capture/sqltrace.py:200, 283-351` (`SqlTraceRecorder.__init__`, `SqlTraceRecorder.record`)
  - `src/sharpit/engine/sqltext/dialect.py:13` (`Dialect`)
  - `src/sharpit/engine/capture/streams.py:195-198` (`ChangeStream.signal`)
- **Why it costs:**
  - `SqlTraceRecorder.record` performs two separate `@functools.lru_cache` lookups per statement (`self._shape(sql, dialect)` and `category_of(sql)`), hashes `Dialect` through Python's `enum.Enum.__hash__` (`0.56 µs/stmt` in `cProfile`), and calls `_truncate(shape.text, self._max_sql_length)` (`shape.text.strip()` + length slice, `0.70 µs/stmt` in `cProfile`) on every cache hit even though `shape.text` and its truncated form are invariant for a given `(sql, dialect)` in that recorder.
  - Under `self._lock`, `self._aggregates.move_to_end(key)` is called on every statement even when `len(self._aggregates) == 1`.
  - `self.changes.signal()` calls `target.signal()` and `super().signal()` (4 method calls per statement, `2.15 µs/stmt` in `cProfile`) even when `self._subscribers` is empty on both `sql_trace.changes` and `activity.changes`.
- **The change:**
  - Cache `(shape, truncated_text, category)` together in one per-recorder `@functools.lru_cache(maxsize=1024)` function in `SqlTraceRecorder`.
  - Set `__hash__ = object.__hash__` on `Dialect` (enum members are singletons, so identity hashing in C is exact and avoids `enum.Enum.__hash__`).
  - Skip `self._aggregates.move_to_end(key)` when `len(self._aggregates) <= 1`.
  - In `ChangeStream.signal()`, check `if target._subscribers or target._forwards:` before forwarding and `if self._subscribers:` before calling `super().signal()`.
- **Safety-model check:**
  - The per-recorder cache stays bound to `self._masker` and `self._max_sql_length`, so one recorder's masker configuration never leaks into another recorder's cache.
- **Existing tests that prove behaviour is unchanged:**
  - `tests/engine/capture/test_sqltrace.py::test_a_repeated_statement_is_masked_once`
  - `tests/engine/capture/test_sqltrace.py::test_a_shape_without_a_fingerprint_is_not_aggregated`
  - `tests/engine/capture/test_sqltrace.py::test_sql_cut_at_max_length`
  - `tests/engine/capture/test_sqltrace.py::test_category_of_table`
  - `tests/engine/capture/test_sqltrace.py::test_aggregates_capped_500_lru`
  - `tests/engine/capture/test_sqltrace.py::test_signals_on_record_clear_and_recording_change`

### Cut 5: Direct `RuntimeJournal.offer_flat` path when `size >= 1`
- **Files and lines:**
  - `src/sharpit/engine/capture/journal.py:276-310` (`offer_flat`, `_offer`)
- **Why it costs:**
  - `offer_flat` allocates a closure `lambda stored: (stored, size, started)` on every statement and delegates to `_offer`, which reads and writes `self._copying.active = True` / `False` on a `threading.local()` object around calling that no-op lambda.
  - Setting `self._copying.active = True` exists to prevent recursive offers from host `__repr__` / `__str__` methods while `_copied` walks an arbitrary host event outside the lock; when `offer_flat` is called with `size >= 1`, no copy or host method runs before `self._lock`.
- **The change:**
  - In `offer_flat`, when `size is not None and size >= 1`:
    1. Check `if self._owned() or getattr(self._copying, "active", False): self.count_dropped(REENTRANT); return False`.
    2. Validate `source = event.get("source")` (`if not isinstance(source, str): self.count_dropped(FAILED); return False`).
    3. Acquire `with self._lock:` and call `self._append((event, size, started), source)` directly without allocating a lambda closure or writing to `self._copying.active`.
- **Safety-model check:**
  - Reentrancy protection is preserved: if `offer_flat` is called from inside an active `_copied` host walk (`self._copying.active` is `True`) or while `self._lock` is held on the current thread (`self._owned()` is `True`, e.g., a GC finalizer during `records()`, `view()`, `status()`, or `_append()`), it still refuses the offer and increments `reentrant`.
- **Existing tests that prove behaviour is unchanged:**
  - `tests/engine/capture/test_journal.py::test_an_offer_made_while_this_thread_reads_under_the_lock_is_refused_and_counted`
  - `tests/engine/capture/test_journal.py::test_a_nested_offer_during_an_append_is_refused_before_it_copies_anything`
  - `tests/engine/capture/test_journal.py::test_offer_flat_with_a_size_below_one_still_charges_the_event_and_respects_the_byte_bound`
  - `tests/engine/capture/test_sql_journal.py::test_sql_journal_event_content_is_this_exact_dict`
  - `tests/engine/capture/test_sql_journal.py::test_sql_journal_event_size_is_what_the_flat_walk_charges`

### Cut 6: Direct `context.__dict__.pop` in `_pop_start` and loop over `targets` in `dispatch._record`
- **Files and lines:**
  - `src/sharpit/engine/sqla/listeners.py:97-101` (`_pop_start`)
  - `src/sharpit/engine/sources/dispatch.py:247-252` (`_record`)
- **Why it costs:**
  - `_pop_start` calls `builtins.vars(context)`, checks `"_sharpit_start" in state`, and then calls `state.pop("_sharpit_start")` (two dict lookups plus `vars()`).
  - `dispatch._record` allocates a generator expression `<genexpr>` and calls `builtins.any(c.capture.sql_trace and c.capture.sql_trace.capture_call_site for c in targets)` on every statement (`1.18 µs/stmt` in `cProfile`).
- **The change:**
  - In `_pop_start`, when `context is not None`, call `start = context.__dict__.pop("_sharpit_start", None)` and return `start` if not `None`, falling back to `conn.info.pop(START_KEY, None)`.
  - In `dispatch._record`, replace `any(... for c in targets)` with a simple loop over `targets` (which has 1 element in normal operation).
- **Safety-model check:**
  - None.
- **Existing tests that prove behaviour is unchanged:**
  - `tests/engine/test_sqla.py::test_conn_info_fallback_without_request`
  - `tests/engine/test_sqla.py::test_statement_outside_request_routed_by_registry`
  - `tests/engine/capture/test_sqltrace.py::test_call_site_off_ignores_given_call_site`

### Cut 7: Skip `opentelemetry.trace.get_current_span()` when `_TRACER_PROVIDER` is `None`
- **Files and lines:**
  - `src/sharpit/engine/otel.py:51-60` (`current_trace_id`)
- **Why it costs:**
  - FastAPI (`fastapi.telemetry._api` and `fastapi.telemetry._asgi`) imports `opentelemetry.trace` at `import fastapi` time whenever `opentelemetry-api` is installed in the environment.
  - Consequently, `sys.modules.get("opentelemetry.trace")` is always non-`None` in test and production environments that have `opentelemetry-api` installed, causing `otel.current_trace_id()` to call `trace.get_current_span().get_span_context()` (6 nested Python function calls across `opentelemetry.trace` and `opentelemetry.context`, `3.2%` of total listener `cProfile` time) on every statement even when the host application has not configured a `TracerProvider` (`trace._TRACER_PROVIDER is None`).
- **The change:**
  - In `otel.current_trace_id()`, check `if trace is None or trace.__dict__.get("_TRACER_PROVIDER", _MISSING) is None: return None` before calling `trace.get_current_span().get_span_context()`.
  - Note: in `otel.py:37`, `_sdk_provider()` already uses `getattr(trace, "_TRACER_PROVIDER", _MISSING)` to detect whether the real `opentelemetry.trace` module has an active provider configured, while synthetic `ModuleType("opentelemetry.trace")` objects planted by unit tests either omit `_TRACER_PROVIDER` (returning `_MISSING`, which is not `None`) or set it to a provider instance.
- **Safety-model check:**
  - None (read-only check inside `engine/otel.py`, the OpenTelemetry gatekeeper under Architecture Rule 4).
- **Existing tests that prove behaviour is unchanged:**
  - `tests/engine/test_otel.py`
  - `tests/engine/capture/test_traces.py`
  - `tests/engine/capture/test_sql_journal.py::test_sql_journal_event_size_is_what_the_flat_walk_charges`
  - `tests/fastapi/test_capture_wiring.py`

---

## 5. Evidence for lane S2: does BootUI 2.5.0's event-sink capture apply?

Inspection of BootUI `v2.5.0` (`bootui-engine/src/main/java/io/github/jdubois/bootui/engine/journal/RuntimeEventSink.java`, `RuntimeJournal.java`, `JournalQueue.java`, and `sqltrace/SqlTraceRecorder.java`, `SqlTracingProxies.java`) shows that BootUI's SQL event-sink capture has three parts, **only one of which applies to sharpit's hot-path budget**:

1. **`RuntimeEventSink.beginCapture(JournalSource.SQL)` / `DeferredCapture` / `DeferredSqlEvent` (`RuntimeEventSink.java:36-57`, `SqlTraceRecorder.java:791-824, 876-877, 943-947, 1010-1056`, `SqlTracingProxies.java:393-541, 739-785`, `RuntimeJournal.java:1360-1415`): does NOT apply for speed.**
   - *Why BootUI has it:* In JDBC, `PreparedStatement.executeQuery()` returns a `ResultSet` before the application iterates over the rows. BootUI 2.4.0/2.5.0 added `beginCapture(JournalSource.SQL)` and `DeferredSqlEvent` so `SqlTracingProxies` can wrap the `ResultSet` in a dynamic proxy (`ResultSetHandler`), count `ResultSet.next()` calls until exhaustion or close, and only then publish the `RuntimeEvent` with `rowCount` via `DeferredSqlEvent.complete(rowCount)`.
   - *Why it does not lower sharpit's per-statement cost:* It **adds** two `synchronized` lock acquisitions (`journalBindingLock` and `deferredLifecycle`), a `JournalBinding` record allocation, a `DeferredSqlEvent` allocation, and a `SqlPayload.withRowCount` clone per query. In Python DBAPI / SQLAlchemy, `cursor.rowcount` is already read synchronously in `after_cursor_execute` (`listeners.py:165`), and SQLAlchemy has no cursor-level `ResultSet` exhaustion event. Porting `beginCapture` / `DeferredCapture` would make the per-statement path slower, not faster.
2. **Asynchronous `JournalQueue` + background `bootui-journal-dispatch` thread (`RuntimeJournal.java:1108-1124, 1433-1452, 1547-1629`, `JournalQueue.java:85-135`): already recorded as an intentional sharpit deviation (`src/sharpit/engine/capture/journal.py:5-9`) and not needed for 40 µs.**
   - In BootUI, `journal.offer(event)` enqueues an immutable `RuntimeEvent` under `JournalQueue`'s lock, and a background daemon thread drains batches of up to 512 events to compute `estimatedBytes(dictionary)`, intern strings in `JournalDictionary`, and append to `EvidenceRing`.
   - In sharpit, spawning a background daemon thread per installed `SharpitContext` was deliberately avoided (`journal.py:5-9`, verified by `tests/engine/capture/test_journal.py::test_journal_off_allocates_nothing` and thread-count assertions), and `dispatch._journal_event` already precomputes `size` and `started` in `O(1)` (`_SQL_EVENT_BYTES + len(text) + ...`). With Cut 5 (`offer_flat` fast path), `offer_flat` takes `< 1.0 µs` synchronously under the GIL without a background thread.
3. **What DOES apply from BootUI `SqlTraceRecorder.capture` (`SqlTraceRecorder.java:875-956`):**
   - **Single admission & correlation pass per statement:** BootUI's `SqlTraceRecorder.capture` checks `boolean panel = capturesForPanel(); boolean toJournal = journal.records(JournalSource.SQL); if (!panel && !toJournal) return null;` up front, reads correlation (`correlation.current()`), `timestamp`, `completedNanos`, `truncatedSql`, and `ApplicationFrames` **once**, and shares them between the panel entry (`CapturedStatement`) and the journal event (`sqlEvent`).
   - In sharpit today, `REQUEST.get()`, `time.time_ns()`, dialect verification (`engine_dialect` + `event_dialect`), and `_truncate(shape.text)` are repeated across `before_cursor_execute`, `_emit`, `_record`, `_trace_text`, `SqlTraceRecorder.record`, `_journal_event`, and `RuntimeJournal._append`. Consolidating those repeated per-statement reads (Cuts 1–7 above) directly ports BootUI's single-pass `capture()` structure without changing sharpit's synchronous journal design.

---

## 6. What lane S2 should do first

1. **Apply Cuts 1–7 in order of size (no behaviour change, all existing unit and safety tests green):**
   - **Step 1 (Cut 1 — `dialect_source.py`, `listeners.py`, `dispatch.py`):** Verify `conn.dialect` and `conn.engine.dialect` once per statement in `_emit` (calling `_candidate` once when `conn.dialect is conn.engine.dialect`), and fast-path `type(event) is SqlEvent` in `event_dialect` so `_attribute(event, "context")` never raises `AttributeError` on `SqlEvent`.
   - **Step 2 (Cut 2 — `sqltrace.py`):** In `call_site`, start at `sys._getframe(5)` when `frame is None` (with `except ValueError: current = sys._getframe(1)`) to skip sharpit's 5 internal frames in C, and move `sys.modules.get("greenlet")` / `greenlet.getcurrent().parent` inside `if current is None:`. (Keep `is_application_frame(code.co_filename)` keyed on `str`, never `CodeType`.)
   - **Step 3 (Cut 3 — `dispatch.py`):** In `_targets(engine)`, return `contexts` immediately when `info is None and len(contexts) <= 1` (skipping `EngineRegistry.holds(engine)`), and fold `recording()` into a single loop.
   - **Step 4 (Cut 4 — `sqltrace.py`, `sqltext/dialect.py`, `streams.py`):** Combine `_shape`, `_truncate(shape.text, self._max_sql_length)`, and `category_of(sql)` into one per-recorder `@functools.lru_cache(maxsize=1024)` entry, set `__hash__ = object.__hash__` on `Dialect`, skip `OrderedDict.move_to_end` when `len(self._aggregates) <= 1`, and guard `ChangeStream.signal` with `if self._subscribers:`.
   - **Step 5 (Cut 5 — `journal.py`):** In `RuntimeJournal.offer_flat`, when `size is not None and size >= 1`, bypass the lambda allocation and `self._copying.active` write/clear while keeping the `self._owned() or getattr(self._copying, "active", False)` reentrancy check.
   - **Step 6 (Cuts 6 & 7 — `listeners.py`, `dispatch.py`, `otel.py`):** Use `context.__dict__.pop("_sharpit_start", None)` in `_pop_start`, replace `any(... for c in targets)` in `dispatch._record` with a `for` loop, and short-circuit `otel.current_trace_id()` when `trace.__dict__.get("_TRACER_PROVIDER", _MISSING) is None`.
2. **Verify locally with `scripts/dev/profile_sql_listener.py`:**
   - Run `uv run python -m scripts.dev.profile_sql_listener --statements 20000 --runs 3` before and after to confirm the ~24% (~7 µs local) drop on both the default ring and the full ring.
3. **sbx measurement to run after S2 lands:**
   - Run a 10-round paired and interleaved `sbx` comparison (`sbx_ab.sh 10` on `tests/fastapi/test_sql_trace_overhead.py::test_statement_overhead_budget` and `::test_statement_overhead_budget_on_a_full_ring`) against `0.9.0` base to confirm the `sbx` median drops from **47.1–47.7 µs** to **~36–38 µs** (≤ 40 µs target).
