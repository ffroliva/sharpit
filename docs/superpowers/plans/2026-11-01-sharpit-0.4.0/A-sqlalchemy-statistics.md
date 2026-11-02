# Lane A-sqlalchemy-statistics: `sqlalchemy-statistics` (BootUI `hibernate-statistics`)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `A-sqlalchemy-statistics` (worktree `...\0.4.0-A-sqlalchemy-statistics`, branch `lane/0.4.0-A-sqlalchemy-statistics`) |
| **Goal** | BootUI's `HibernateStatisticsReport` filled from what SQLAlchemy really measures (the SQL recorder), every other counter `null` with a reason, plus N+1 per route for request-correlated statements. |
| **Spec** | §4 ("A counter Python cannot measure is `null` with a reason"), §6.1, §6.2 (id rename, `ids.json`), §7 row `sqlalchemy-statistics`, §11 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §3; BootUI `HibernateStatisticsReport`, `HibernateStatisticsDto`, `HibernateCacheRegionStatisticsDto`, `HibernateStatisticsService.java` |
| **Worker** | M/L, judgement-heavy (what is honest) → codex |
| **Depends on** | F (PLAN.md). Not on A-transactions (rule 3: no collector imports another). Consumes these rows of F's consumer interface table (`F-foundation.md`): `sharpit.fastapi.routes.<id>` (`routes/sqlalchemy_statistics.py`), "implemented flag files" (`engine/panels04/<id>.py` + `ui/src/lib/panels04/<id>.ts`, O4, here `sqlalchemy_statistics`), `sharpit.engine.tools04.<id>` (`engine/tools04/sqlalchemy_statistics.py`, `TOOLS = ()` until this lane fills it, R3), `tests.golden.assert_parity` (O2) + `ids.json`, the `ui/src/views/SqlalchemyStatistics.svelte` placeholder; F's `examples/fastapi_sqla` wiring (O3: a list route that lazy-loads a relationship per row). `tests/safety/` + `tests/masking/` are F-rest: if absent, the lane creates its own two files without shared helpers. T-n-plus-one-message depends on this lane (both extend the SQL recorder). |
| **May touch** | `src/sharpit/engine/collectors/sqlastats.py` (new), `src/sharpit/engine/capture/sqltrace.py` (**only** the lifetime-totals addition in Task 2), `src/sharpit/fastapi/routes/sqlalchemy_statistics.py` (F stub), `src/sharpit/engine/panels04/sqlalchemy_statistics.py` and `ui/src/lib/panels04/sqlalchemy_statistics.ts` (flag flip only, O4), `src/sharpit/engine/tools04/sqlalchemy_statistics.py` (the two tools replace F's `TOOLS = ()`), `ui/src/views/SqlalchemyStatistics.svelte` (replace F's placeholder) + `.test.ts`, `tests/engine/test_sqlastats.py`, `tests/engine/capture/test_sqltrace_totals.py`, `tests/fastapi/test_sqlalchemy_statistics_api.py`, `tests/safety/test_a_sqlalchemy_statistics_safety.py`, `tests/masking/test_a_sqlalchemy_statistics_masking.py`, `tests/fixtures/bootui/2.2.0/sqlalchemy-statistics/nullable.json` (O2), the implementer files in the lane folder (C2) plus `docs.md` (O3) |
| **Must NOT touch** | §10.3 protected files; `BUDGET_NS` in `tests/fastapi/test_sql_trace_overhead.py:25` (it must stay green **unchanged**); `engine/sqla.py` (O1); `engine/tools.py` (R3); `engine/sources/dispatch.py`; `PANELS`, `nav.ts`, `App.svelte`, `types.ts` (O4); `captured.json` / `provisional.json` (O2); `README.md`, `skills/sharpit/SKILL.md`, `examples/fastapi_sqla/`, `tests/test_example_app.py` (O3); other lanes' modules; `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (C5); any `review.md` or `gate/` path |

**Architecture:** The collector `engine/collectors/sqlastats.py` is pure: it reads `ctx.capture.sql_trace` (lifetime
totals + the ring) and `ctx.capture.exchanges` (request id → method, endpoint via `HttpExchangeBuffer.get`,
`engine/capture/exchanges.py`). `SqlTraceRecorder.record` (`sqltrace.py:443`) gains three in-lock updates for lifetime
totals; nothing else on the hot path. Statistics follow SQL Trace's recording switch; `POST /enable` is accepted and
changes nothing (statistics are always on while SQL Trace records), logged §11.

## Global Constraints

- No fabricated counter: a key with no SQLAlchemy analogue is `null` and listed in `nullable.json` with its reason.
- No GET/MCP side effects; statistics computed from in-memory buffers only.
- Statement text only as stored by the recorder: normalised, or masked when `capture_parameters` (`sqltrace.py:464`).
- The existing SQL Trace overhead budget (`test_sql_trace_overhead.py`, 50 µs) passes unchanged; never raised.
- Keys verbatim; `ids.json` maps `hibernate-statistics` → `sqlalchemy-statistics`; API path, MCP names
  (`get_sqlalchemy_statistics`) and golden folder use the sharpit id.
- Ported tests cite `# ported:`. PT018. Conventional commits, no attribution.
- Red is an assertion (R2): each task's red is a **red commit** (subject starts `test:`) with the failing tests plus the
  minimal stubs that make them import; a stub returns a wrong value, never raises `NotImplementedError`. Record its SHA
  per red test in `findings.md` and `handoff.md`; `lane_gate.py` replays each test at that SHA (needs `AssertionError`)
  and at the lane head (must pass). Every "FAIL" step below means this red commit.

## Review Focus

1. **Parameter capture on** (`SHARPIT_SQL_TRACE_CAPTURE_PARAMETERS=true`): ring rows then hold masked raw SQL, so
   `queryExecutionMaxTimeQueryString` and N+1 grouping must use `normalize(row["sql"]).fingerprint`, never the raw
   text. Expect no literal from a WHERE clause in the report. Pinned in Task 3: `test_max_time_query_is_normalised`.
2. **Evicted ring vs lifetime totals.** 500 statements through a 200-row ring. Expect `queryExecutionCount == 500`
   (lifetime), N+1 computed over retained rows only with the extra key `nPlusOneWindow` saying so. Pinned in Task 3:
   `test_counts_are_lifetime_n_plus_one_is_window`.
3. **Statements outside a request** (startup, background task, test client without capture). Expect them counted in
   totals and never in `nPlusOne`. Pinned in Task 3: `test_uncorrelated_statements_not_in_n_plus_one`.
4. **HTTP exchanges disabled or evicted.** The request id has no exchange row. Expect the N+1 entry kept with
   `method`/`route` `null` and `routeReason` set, not dropped. Pinned in Task 3: `test_route_unknown_when_exchange_gone`.
5. **SQL Trace disabled / SQLAlchemy absent.** Expect `available:false` with the SQL Trace reason
   (`tools.sql_trace_unavailable_reason`, `engine/tools.py:253`), all counters still emitted. Pinned in Task 4:
   `test_unavailable_mirrors_sql_trace_reason`.

## Field map

| BootUI key | Python source |
|---|---|
| `available` | `ctx.capture.sql_trace is not None` and `sql_trace_unavailable_reason(ctx) is None` |
| `enableAvailable` | `false` (nothing to enable: always on while SQL Trace records) |
| `unavailableReason` | SQL Trace's reason, else `null` |
| `queryExecutionCount` | lifetime SELECT statements (`category == "SELECT"`) |
| `queryExecutionMaxTime` | lifetime max `durationMillis` over all statements |
| `queryExecutionMaxTimeQueryString` | normalised, masked SQL of that statement; `null` before any |
| `queryCacheEnabled`, `secondLevelCacheEnabled` | `false` (SQLAlchemy has no result/2nd-level cache; true fact) |
| `queryCache*Count`, `secondLevelCache*Count` | `0` (cache disabled ⇒ zero, as Hibernate reports) |
| `secondLevelCacheRegions` | `[]` |
| `sessionOpenCount`, `sessionCloseCount`, `flushCount`, `connectCount`, `transactionCount`, `successfulTransactionCount`, `entityLoad/Fetch/Insert/Update/DeleteCount`, `collectionLoad/Fetch/Recreate/Update/RemoveCount` | `null`; reason `"SQLAlchemy reports SQL statements, not ORM session or entity operations"` (transactions live in the `transactions` panel) |
| extra `statementCount` | lifetime statements, all categories |
| extra `nPlusOne` | `[{method, route, routeReason, sql, executionsPerRequest, requests, threshold}]` sorted by `executionsPerRequest` desc then `sql`; at most 20 |
| extra `nPlusOneWindow` | `"retained SQL Trace window (<n> statements)"` |

---

### Task 1: Golden, `ids.json` row, nullable keys

**Files:** `tests/fixtures/bootui/2.2.0/sqlalchemy-statistics/nullable.json` only (one entry per null key above, path
`statistics.<key>`; O2); check `ids.json` has `"hibernate-statistics": "sqlalchemy-statistics"` (F).

- [ ] **Step 1:** The golden is G0a's `tests/fixtures/bootui/2.2.0/sqlalchemy-statistics/captured.json`; if absent, the
  coordinator has another worker write `provisional.json` (§12.11) and `checklist.md` item 1 says "unverified".
  **Step 2:** Commit `test: sqlalchemy-statistics nullable keys`.

### Task 2: Lifetime totals in `SqlTraceRecorder`

**Files:** Modify `src/sharpit/engine/capture/sqltrace.py` (`__init__` at `:389`, `record` at `:443`, `clear` at
`:521`); Test `tests/engine/capture/test_sqltrace_totals.py`.

**Interfaces:** Produces `SqlTraceRecorder.totals() -> SqlTotals`, `class SqlTotals(NamedTuple): statements: int;
selects: int; max_millis: int; max_sql: str | None`. Updated inside the existing `with self._lock:` block; `max_sql`
is the stored row's `sql`, normalised (`normalize(...).sql`). `clear()` does **not** reset totals (Hibernate counters
are lifetime; logged §11).

- [ ] **Step 1:** Tests `test_totals_count_every_statement`, `test_totals_selects_only_select_category`,
  `test_totals_max_keeps_slowest`, `test_totals_survive_clear`, `test_totals_survive_eviction`,
  `test_paused_recorder_adds_nothing`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS; run `tests/fastapi/test_sql_trace_overhead.py`
  unchanged → PASS (paste output into `checklist.md`). Commit `feat: lifetime statement totals on the SQL recorder`.

### Task 3: Collector `engine/collectors/sqlastats.py`

**Files:** Create `src/sharpit/engine/collectors/sqlastats.py`; Test `tests/engine/test_sqlastats.py`.

**Interfaces:** Consumes `SqlTraceRecorder.totals()`, `.rows()` (`sqltrace.py:532`), `normalize`
(`sqltrace.py:231`), `HttpExchangeBuffer.get(request_id)` (`engine/capture/exchanges.py:160`),
`ctx.settings.sql_trace_n_plus_one_threshold` (`settings.py:79`, default 5, min 2). Produces
`NULL_REASON` (text above), `NULL_KEYS: tuple[str, ...]`, `statistics_report(ctx: SharpitContext) -> dict[str, Any]`,
`n_plus_one(rows: list[dict[str, Any]], route_of: Callable[[str], tuple[str, str] | None], threshold: int) ->
list[dict[str, Any]]`.

N+1 rule (BootUI's per-statement rule applied per request): group retained `SELECT` rows by `(traceId, fingerprint)`
where `traceId` is not `null`; a group with `>= threshold` rows is one occurrence; occurrences merge per
`(method, route, fingerprint)` with `requests` = occurrences and `executionsPerRequest` = max group size.

- [ ] **Step 1:** Tests: `test_maps_totals_onto_dto` (`# ported: HibernateStatisticsServiceTests.mapsSnapshotOntoDtoWhenAvailableAndEnabled`;
  every DTO key present, `NULL_KEYS` are `None`), `test_unavailable_without_recorder`
  (`# ported: HibernateStatisticsServiceTests.reportsUnavailableWhenNoProvider`), `test_unavailable_when_tracing_off`
  (`# ported: HibernateStatisticsServiceTests.reportsUnavailableWhenStatisticsDisabled`),
  `test_n_plus_one_per_route` (6 identical SELECTs in one request, threshold 5 → one entry, `requests == 1`,
  `executionsPerRequest == 6`), `test_below_threshold_is_not_n_plus_one`, plus Review Focus 1–4 tests.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. Commit `feat: sqlalchemy-statistics collector`.

### Task 4: Routes, MCP, safety

**Files:** `src/sharpit/fastapi/routes/sqlalchemy_statistics.py` (F stub), `src/sharpit/engine/panels04/sqlalchemy_statistics.py`
`IMPLEMENTED = True` (O4); Test
`tests/fastapi/test_sqlalchemy_statistics_api.py`, `tests/safety/test_a_sqlalchemy_statistics_safety.py`, and
`tests/masking/test_a_sqlalchemy_statistics_masking.py` (a `STRIPE_KEY` literal in a slow query under
`capture_parameters=true` never appears) on F-rest's shared helpers when present (C5).

**Interfaces:** `GET {api}/sqlalchemy-statistics`, `POST {api}/sqlalchemy-statistics/enable` (returns the report,
read-only gate applies). MCP `get_sqlalchemy_statistics` (read); `enable_sqlalchemy_statistics` `action=True`.
`actionCapable=True` (BootUI).

- [ ] **Step 1:** Tests: `test_golden_parity` (`assert_parity("sqlalchemy-statistics", "report", body)`), `test_enable_returns_report_unchanged`
  (`# ported: HibernateStatisticsControllerTests.enableDelegatesToEngineService`), `test_get_delegates`
  (`# ported: HibernateStatisticsControllerTests.statisticsDelegatesToEngineServiceWhenAvailable`),
  `test_unavailable_mirrors_sql_trace_reason` (`# ported: HibernateStatisticsControllerTests.statisticsReportsUnavailableWhenStatisticsDisabled`),
  `test_get_no_side_effects`, `test_enable_read_only_403`, `test_mcp_read_tool_only`, the masking row.
- [ ] **Step 2:** FAIL on assertions (F's unimplemented panel answers 404; never an `ImportError`, C4). **Step 3:** Implement. **Step 4:** PASS + full gate (background). Commit
  `feat: sqlalchemy-statistics routes and MCP read tool`.

### Task 5: Svelte view

**Files:** Replace F's placeholder `ui/src/views/SqlalchemyStatistics.svelte`, create `.test.ts`; set
`implemented = true` in `ui/src/lib/panels04/sqlalchemy_statistics.ts` (O4; `nav.ts` untouched).

- [ ] **Step 1:** vitest: a `null` counter renders "not measured" with the reason as a tooltip (never "0"); N+1 table
  links the route to HTTP Exchanges; `enableAvailable:false` hides the enable button. Reference
  `views/HibernateStatistics.vue`.
- [ ] **Step 2:** FAIL → implement → `npm --prefix ui run check` + tests PASS. Commit `feat: sqlalchemy-statistics view`.

### Task 6: Live check and evidence

- [ ] **Step 1:** `examples/fastapi_sqla` as F wired it (O3; no edit to the example or `tests/test_example_app.py`):
  hit its list route that lazy-loads a relationship per row; the panel shows one N+1 entry for that route. If F's
  wiring lacks the route, record it as an open finding for the coordinator, not a lane edit. Record requests in `handoff.md` §Live check (`live-verify.md` is the
  coordinator's, C2).
- [ ] **Step 2:** lowest-direct + no-SQLAlchemy as a local pre-check (commands in `checklist.md` item 8; gated logs are
  the coordinator's). User-facing text (SKILL row, the `hibernate-statistics` → `sqlalchemy-statistics` rename) goes
  to the lane folder's `docs.md` (O3). Commit `docs: sqlalchemy-statistics lane evidence`.

## §6.1 → task (spec order; `checklist.md` adds the evidence paths)

| Item | Task |
|---|---|
| 1 golden parity, `nullable.json`, field map | 1, 4 `test_golden_parity`, field map |
| 2 `# ported:` citations | 3, 4 |
| 3 safety + masking (statement text) | 3 (RF1), 4 (`tests/safety/…`, `tests/masking/test_a_sqlalchemy_statistics_masking.py`) |
| 4 gatekeeper | no SQLAlchemy import in the new module; boundary test green |
| 5 overhead budget | 2 (existing SQL Trace budget re-run unchanged; the addition is on its hot path) |
| 6 MCP read-only | 4 |
| 7 Svelte view | 5 |
| 8 four gates + lowest-direct + no-SQLAlchemy | 4, 6 (gated logs: coordinator) |
| 9 live check | 6 |
| 10 handoff current | every commit |

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/A-sqlalchemy-statistics/`)

- **Implementer, in the lane worktree:** `handoff.md` (last green command, next step, open findings, live-check
  requests), `findings.md` (`finding → test → red output`, each row `fixed` + red-test name or `parked` + reason),
  `field-map.md` (the field map above), `checklist.md` (the ten §6.1 items above in the spec's order, each with an evidence
  path or `N/A` + reason). `checklist.md` item 5 carries the unchanged SQL Trace budget output.
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`, reviewer id ≠
  implementer id, head SHA), `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path (`lane_gate.py` refuses it).
