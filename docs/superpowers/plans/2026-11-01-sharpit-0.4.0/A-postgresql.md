# Lane A-postgresql: the `postgresql` panel (catalog reads through the app's engine)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `A-postgresql` (worktree `...\0.4.0-A-postgresql`, branch `lane/0.4.0-A-postgresql`) |
| **Goal** | `POST /sharpit/api/postgresql/read` reads BootUI's PostgreSQL catalog sections through each registered PostgreSQL engine inside a fail-closed read-only transaction; `GET /sharpit/api/postgresql` returns the cached `PostgresInsightReport`. |
| **Spec** | §4, §6.1 (esp. 3 masking of `pg_stat_statements`/`pg_stat_activity`, 9 leased database), §6.3, **§6.4 entire**, §7 row `postgresql`, §11 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §5; BootUI `engine/postgres/*` (`PostgresInsightService.java`, `PostgresQuery.java`, the eight `*Collector.java`, `PostgresSectionIds.java`), DTOs `Postgres*Dto` |
| **Worker** | L, judgement-heavy (transaction safety) → codex; reviewer from another family + `ponytail-review` (touches `sqla.py`) |
| **Depends on** | F (PLAN.md; F adds `psycopg[binary]` to the test extra, F1d — see Task 0). Consumes F's F1a table (`F-foundation.md`): `fastapi/routes/postgresql.py`, the `implemented` flag, the MCP stub module, `tests/golden.py::assert_parity`, the `ui/src/views/Postgresql.svelte` placeholder, the `tests/safety/` + `tests/masking/` helpers |
| **May touch** | `src/sharpit/engine/sqla.py` (**only** `run_db_read` keyword-only parameters and the new `bounded_read_only`; this lane owns these edits), `src/sharpit/engine/collectors/postgresql/` (new package), `src/sharpit/fastapi/routes/postgresql.py` (F stub), this panel's `src/sharpit/engine/panels04/postgresql.py` and `ui/src/lib/panels04/postgresql.ts` implemented flags only, `ui/src/views/Postgresql.svelte` (replace F's placeholder) + `.test.ts`, `tests/engine/test_sqla_read_only.py`, `tests/engine/postgresql/`, `tests/fastapi/test_postgresql_api.py`, `tests/safety/test_a_postgresql_safety.py`, `tests/masking/test_a_postgresql_masking.py`, `tests/fixtures/bootui/2.2.0/postgresql/*`, the implementer files in the lane folder (C2) |
| **Must NOT touch** | §10.3 protected files (no dependency edit: a missing driver is a coordinator `Ruling:`); `bounded` (`sqla.py:352-380`) and its callers `collectors/alembic.py`, `collectors/health.py` — **unchanged**; `examples/fastapi_sqla/`, `tests/test_example_app.py`, `README.md`, `skills/sharpit/SKILL.md` (F owns shared wiring; user text goes in lane `docs.md`); other lanes' modules; `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (C5); any `review.md` or `gate/` path |

**Architecture:** `async def run_db_read` (`sqla.py:383`) gains `*, wall_timeout: float | None = None, statement_timeout: float |
None = None, read_only: bool = False` (both timeouts default to today's `timeout`, so alembic/health are byte-for-byte
the same). With `read_only=True` it calls the new sibling `bounded_read_only(conn, fn, statement_timeout,
lock_timeout)`, which owns the transaction. The panel package ports BootUI's collectors as SQL text + row mappers;
every optional query runs in `conn.begin_nested()`. State (last report, previous metrics for `changes`) is in
`ctx.lazy("postgresql", PostgresState)`, never persisted. Single-flight like `refresh_alembic`
(`collectors/alembic.py:411`).

## Global Constraints

- §6.4 verbatim: **POST only**, through the existing `run_db_read`; nothing re-implements it. PostgreSQL order:
  `SET TRANSACTION READ ONLY` (first statement of the transaction), `SET LOCAL statement_timeout`, `SET LOCAL
  lock_timeout`, then the panel's queries. **AUTOCOMMIT fails closed**: after setup check `conn.in_transaction()` and
  `current_setting('transaction_read_only') = 'on'`; if either fails no catalog SQL runs → `unavailableReason`. In
  SQLAlchemy 2 `in_transaction()` is True even on an AUTOCOMMIT connection (the `Connection` still tracks its
  `begin()`), so the `current_setting` check is the real guard; both are kept.
- Every optional catalog query inside `begin_nested()`, always; one failing query never aborts the transaction.
- No driver imported by sharpit; SQL through the app's engine (async engines via `run_sync`, `sqla.py:402-408`).
- BootUI bounds: statement 5 s, lock 2 s, overall 15 s; statement text ≤ 400 chars; curated settings allow-list;
  row limits `postgresql_max_sessions=100, max_statements=100, max_indexes=500, max_tables=200,
  max_vacuum_tables=200, max_replicas=10, max_settings=40` (env `SHARPIT_POSTGRESQL_*`, 1..2147483646, invalid →
  default + warning). Constants `STATEMENT_TIMEOUT = 5.0`, `LOCK_TIMEOUT = 2.0`, `READ_BUDGET = 15.0`.
- Statement and session query text masked (`normalize_sql` from `capture/sqltrace.py:280`, then
  `ctx.masker.mask_text`, then 400-char cut); client addresses follow the exposure policy; setting values withheld
  under `METADATA_ONLY`.
- Errors strings from BootUI with `BootUI`→`sharpit`. Ported tests cite `# ported:`. Red is an assertion. PT018.

## Review Focus

1. **AUTOCOMMIT engine** (`engine.execution_options(isolation_level="AUTOCOMMIT")`): `SET TRANSACTION READ ONLY` is a
   no-op outside a server transaction, yet SQLAlchemy 2 still reports `in_transaction()` True. Expect **zero** catalog
   statements issued and `unavailableReason`. Pinned in Task 1 (canonical, PLAN.md Review Focus 4):
   `test_autocommit_engine_is_unavailable` (leased PG), plus the fake-connection tests
   `test_autocommit_fails_closed_without_catalog_sql` (`in_transaction()` False) and
   `test_read_only_setting_off_fails_closed` (`in_transaction()` True, `current_setting('transaction_read_only')` →
   `'off'`).
2. **A write inside the wrapper.** `fn` runs `CREATE TEMP TABLE` / `INSERT`. Expect PostgreSQL's read-only error, the
   app's table untouched. Pinned in Task 1 (canonical): `test_read_only_wrapper_rejects_write` (leased PG).
3. **`pg_stat_statements` absent, not preloaded, or permission denied** after an earlier section succeeded. Expect
   `statements` section `SKIPPED` with BootUI's hint, every later section still `AVAILABLE`. Pinned in Task 3:
   `test_failed_query_does_not_poison_later_sections` (`# ported: PostgresCollectorsTests.aFailedQueryDoesNotPoisonTheSectionsReadAfterIt`).
4. **Secrets in catalog text.** `pg_stat_activity.query` holding `password='...'`, a dollar-quoted body, an
   `E'..\'..'` string; a DSN with a password in an error. Expect masked. Pinned in Task 2 (`querytext` tests) and Task 5
   rows in `tests/masking/test_a_postgresql_masking.py`.
5. **A non-PostgreSQL engine and no engine.** sqlite registered → diagnostic `"Skipped: this datasource is SQLite,
   not PostgreSQL."`, no read; nothing registered → `DISABLED` with BootUI's "No PostgreSQL datasource was found…".
   Pinned in Task 4: `test_non_postgres_engine_is_skipped`, `test_no_engine_is_disabled`.

---

### Task 0: Pre-flight

- [ ] **Step 1:** `uv run --no-sync python -c "import psycopg"` succeeds (F1d: `psycopg[binary]` in the test extra). If not, record it in
  `handoff.md` and ask the coordinator for a `Ruling:`; the lane cannot edit dependency lists.
- [ ] **Step 2:** `agentctl.py lease database` → the reference compose's Postgres; export
  `SHARPIT_TEST_POSTGRES_URL=postgresql+psycopg://...` (tests read it; absent → skip with reason, and the lane counts
  **unverified**, §6.1.9). Record the lease id in `handoff.md`. A Task 1–7 red is an assertion; a skip is not a red.

### Task 1: `run_db_read(read_only=True)` and `bounded_read_only` in `engine/sqla.py`

**Files:** Modify `src/sharpit/engine/sqla.py:383-424`; add `bounded_read_only` after `bounded`; Test
`tests/engine/test_sqla_read_only.py`.

**Interfaces:** Produces
- `async def run_db_read[T](engine: Any, fn: Callable[[Any], T], timeout: float, *, executor: Executor | None = None,
  done: Callable[[], None] | None = None, wall_timeout: float | None = None, statement_timeout: float | None = None,
  read_only: bool = False) -> T` (today's signature at `sqla.py:383-390` plus the three keywords) —
  `asyncio.timeout(wall_timeout or timeout)`; the async branch keeps `conn.run_sync(...)` (`sqla.py:408`);
  `read_only=False` → `bounded(conn, fn, statement_timeout or timeout)` exactly as today.
- `bounded_read_only[T](conn, fn: Callable[[Any], T], statement_timeout: float, lock_timeout: float) -> T` — raises
  `ReadOnlyUnavailable(reason: str)` before `fn` when the guard fails. PostgreSQL branch per §6.4; the MySQL branch is
  **not** in this lane (stretch `mysql` adds it); other dialects → `ReadOnlyUnavailable("Read-only reads are not
  supported for <dialect>")`.
- `READ_ONLY_REFUSED = "The read-only transaction could not be established, so sharpit skipped this read"`.

- [ ] **Step 1:** Stub, then tests:
  - `test_default_path_unchanged` — a spy on `bounded`; `run_db_read(e, fn, 5)` calls it with `5`; alembic and health
    tests untouched and green (run `tests/engine/test_alembic.py tests/engine/test_health.py`).
  - `test_separate_wall_and_statement_timeouts` — statement 0.2, wall 2 → `SET LOCAL statement_timeout = 200`.
  - `test_read_only_order` — recorded `exec_driver_sql` calls on a fake PG conn are exactly
    `["SET TRANSACTION READ ONLY", "SET LOCAL statement_timeout = 5000", "SET LOCAL lock_timeout = 2000",
    "SELECT current_setting('transaction_read_only')", <fn's>]`
    (`# ported: PostgresHelpersTests.readOnlyTransactionPinRunsBeforeAnySavepoint`).
  - `test_autocommit_fails_closed_without_catalog_sql` (fake: `in_transaction()` False) → `ReadOnlyUnavailable`, `fn`
    never called (`# ported: PostgresInsightServiceTests.aRefusedReadOnlyPinStopsTheReadBeforeCollectorsRun`).
  - `test_read_only_setting_off_fails_closed` (`# derived: SQLAlchemy 2 in_transaction() is True under AUTOCOMMIT`;
    fake: `in_transaction()` True, `SELECT current_setting('transaction_read_only')` returns `'off'`) →
    `ReadOnlyUnavailable(READ_ONLY_REFUSED)`, `fn` never called, no statement after the `current_setting` read.
  - leased PG (`@pytest.mark.skipif(not URL)`): `test_read_only_wrapper_rejects_write`,
    `test_autocommit_engine_is_unavailable` (canonical names, PLAN.md Review Focus 4), `test_async_engine_read_only`
    (`postgresql+psycopg` async).
  - `test_internal_marker_kept` — SQL Trace records none of the setup statements.
- [ ] **Step 2:** FAIL on assertions. **Step 3:** Implement; transaction ends with rollback (never commit).
- [ ] **Step 4:** PASS (leased tests ran: paste output). Commit `feat: read-only bounded reads for catalog panels`.

### Task 2: Query text, formatting and row limits

**Files:** Create `src/sharpit/engine/collectors/postgresql/__init__.py`, `.../querytext.py`, `.../limits.py`; Test
`tests/engine/postgresql/test_querytext.py`, `test_limits.py`.

**Interfaces:** `query_text(masker: Masker, sql: str | None) -> str | None` (normalise, mask, collapse whitespace,
cut 400 + `"..."`); `RowLimits` dataclass from settings; `read_one_past(rows, limit) -> tuple[list, bool]`.

- [ ] **Step 1:** Tests (`# ported: PostgresHelpersTests.queryTextAppliesExposureRedactionWhitespaceAndTruncation`,
  `.queryTextMasksDollarQuotedBodies`, `.queryTextMasksEscapeStringsInsteadOfStoppingAtTheEscapedQuote`,
  `.rowsDistinguishEmptyAvailableFromFailedAndCopyRows`; `PostgresRowLimitsTests.defaultsIncreaseRowCoverageWithoutRelaxingTimeOrTextBounds`;
  `PostgresCollectorsTests.listQueriesReadOnePastTheBoundAndReportTruncation`; `PostgresInsightServiceTests.exactlyTheRowLimitIsNotReportedAsTruncated`).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: postgresql query text and row limits`.

### Task 3: Section collectors

**Files:** Create `.../postgresql/queries.py` (SQL text ported from BootUI's collectors, one constant per query,
source file cited in a comment), `.../postgresql/sections.py`; Test `tests/engine/postgresql/test_sections.py`
(fake connection returning canned rows + leased-PG variants).

**Interfaces:** `SECTION_IDS = ("vital-signs", "sessions", "statements", "indexes", "tables", "vacuum", "replication",
"settings")` (`PostgresSectionIds`); `collect(conn, masker: Masker, limits: RowLimits, budget: ReadBudget) ->
DatabaseData` — every section runs `with conn.begin_nested():`; failure → section `FAILED`/`SKIPPED` with a masked
reason (`CredentialRedaction` analogue: `masker.mask_text`). `ReadBudget(deadline: float)` with `remaining()` and
`exhausted()`; an exhausted budget marks remaining sections `SKIPPED` "The read budget ran out before this section was
read.".

- [ ] **Step 1:** Tests ported from `PostgresCollectorsTests`: `statementCollectorPicksTimingColumnsFromTheExtensionNotTheServer`,
  `missingPgStatStatementsExtensionIsSkippedWithActionableHint`, `failedCollectorQueriesKeepCredentialRedactedReason`,
  `aFailedQueryDoesNotPoisonTheSectionsReadAfterIt`, `vitalSignsReportTheSessionBreakdownAsUnknownWhenBackendsAreHidden`,
  `sessionClientAddressFollowsTheExposurePolicy`, `replicaClientAddressFollowsTheExposurePolicy`,
  `settingValuesAreWithheldUnderMetadataOnlyButStillDriveTheRules`, `settingsExcludeTheTimeoutsOverriddenByBootui`,
  `aStandbyDoesNotPresentAnUnreadReplicaListAsAnEmptyObservation`, `theSessionListIsScopedToTheDatabaseThePanelReports`,
  `aBudgetExhaustedBeforeTheFirstRowDoesNotProduceAnAvailableEmptyList`; from `PostgresHelpersTests`:
  `vacuumDueHonoursPerTableReloptionsOverrides`, `vacuumThresholdFloorsSoTheComparisonMatchesPostgreSql`.
  Leased PG: `test_sections_on_real_server` (every section `AVAILABLE` or `SKIPPED` with a reason; DTO keys complete).
- [ ] **Step 2:** FAIL → **Step 3:** implement (version-dependent views resolved from the catalog, as BootUI) →
  **Step 4:** PASS. Commit `feat: postgresql catalog section collectors`.

### Task 4: Service: report, refresh, comparison

**Files:** Create `.../postgresql/service.py`; Test `tests/engine/postgresql/test_service.py`.

**Interfaces:** `postgresql_report(ctx) -> dict[str, Any]` (cached or initial `NOT_READ`, never connects);
`async refresh_postgresql(ctx) -> dict[str, Any]` (single-flight `"postgresql-read"`, `ActionBusy` → 409, iterates
`ctx.capture.engine_registry.engines()` with `dialect.name == "postgresql"`); `engine_registry` is optional and `engines()` yields `(name, engine)` tuples. Report keys `localOnly, disclaimer,
status, message, readAt, databasesRead, truncated, databases, diagnostics, limitations` with BootUI's `DISCLAIMER`
and messages; status `NOT_READ`/`DISABLED`/`ERROR`/`PARTIAL`/`READ` by `PostgresInsightService.java:196-207`.

- [ ] **Step 1:** Tests (`# ported: PostgresInsightServiceTests.*`): `initialReportTouchesNeitherDiscoveryNorDatabase`,
  `nonPostgresDatasourceIsReportedHonestlyWithoutADatabaseReport`, `datasourceThatRefusesConnectionsProducesErrorAndDiagnostic`,
  `aDatasourceConnectionAlreadyInManualCommitModeIsSkipped` (→ AUTOCOMMIT analogue, sharpit text `READ_ONLY_REFUSED`),
  `configuredRowLimitsReachEveryCollector`, `statementTextGoesThroughExposurePolicy`,
  `aRoleThatCannotReadOtherBackendsDegradesTheSessionListInsteadOfLookingQuiet`,
  `anAbsentStatementExtensionIsReportedAsASkippedSectionRatherThanAnEmptyOne`,
  `anExhaustedReadBudgetIsReportedInsteadOfLookingLikeACleanRead`,
  `inMemoryPreviousReadDeltaAppearsOnlyFromSecondReadAndIsNotPersisted`,
  `aPartialReadKeepsTheBaselineOfTheSectionsItCouldNotRead`; plus `test_no_engine_is_disabled`,
  `test_non_postgres_engine_is_skipped`, `test_concurrent_read_is_busy`.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: postgresql read service`.

### Task 5: Routes, MCP, safety, masking corpus

**Files:** `src/sharpit/fastapi/routes/postgresql.py` (F stub), flag flip; Tests `tests/fastapi/test_postgresql_api.py`,
`tests/safety/test_a_postgresql_safety.py`, `tests/masking/test_a_postgresql_masking.py` (rows: `pg_stat_activity.query`
with `STRIPE_KEY`, `pg_stat_statements.query` with `password=`, an error carrying a DSN password), on F's shared
helpers (C5).

**Interfaces:** `GET {api}/postgresql`, `POST {api}/postgresql/read`. MCP `get_postgresql_report` (read);
`postgresql_read` `action=True` (CLI-only). `actionCapable=True`; read-only → 403 on POST.

- [ ] **Step 1:** Tests: `test_golden_parity` (`assert_parity("postgresql", "report", body)` after a leased read; the
  `NOT_READ` report against the golden otherwise), `getReturnsTheNotReadReportBeforeAnyRead`,
  `readPerformsTheReadAndReturnsAReport`, `getReturnsTheLastReadReportAfterARead` (`# ported: PostgresqlControllerTests.*`),
  `test_get_no_side_effects` (no socket, no SQL: a `before_cursor_execute` spy sees nothing), `test_read_only_403`,
  `test_mcp_read_tool_only`, the masking rows. Fixture at `tests/fixtures/bootui/2.2.0/postgresql/report.json` +
  `nullable.json` (C3).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS + full gate (background). Commit
  `feat: postgresql panel routes and MCP read tool`.

### Task 6: Svelte view

**Files:** Replace F's placeholder `ui/src/views/Postgresql.svelte`, create `.test.ts`; flip the panel's `implemented`
in F's `ui/src/lib/nav.ts` wiring (flag only).

- [ ] **Step 1:** vitest: `NOT_READ` shows the read button and message; sections render status/reason/hint;
  `changes` render only from the second read; the read button is hidden when `readOnly`. Reference
  `views/Postgresql.vue`.
- [ ] **Step 2:** FAIL → implement → `npm --prefix ui run check` + tests PASS. Commit `feat: postgresql view`.

### Task 7: Live check and evidence

- [ ] **Step 1:** `examples/fastapi_sqla` pointed at the leased Postgres (env, no code change) and tiny-ledger-py when
  ready: GET (NOT_READ) → POST read → GET (cached). Record requests in `handoff.md` §Live check (`live-verify.md` is
  the coordinator's, C2).
- [ ] **Step 2:** lowest-direct + no-SQLAlchemy as a local pre-check (gated logs are the coordinator's); the leased-PG
  test run (no skips, head SHA on the first line) pasted in `handoff.md` §Leased run and cited by `checklist.md` item 9.
  Release the database lease. Commit `docs: postgresql lane evidence`.

## §6.1 → task (spec order; `checklist.md` adds the evidence paths)

| Item | Task |
|---|---|
| 1 golden parity (+ field map: every `Postgres*Dto` key → its catalog column or `null` + reason) | 3, 5 |
| 2 `# ported:` citations | 1–5 |
| 3 safety + masking (`pg_stat_statements`, `pg_stat_activity`) | 1, 2, 5 |
| 4 gatekeeper (SQL only through `sqla.run_db_read`) | 1 |
| 5 overhead budget | `N/A`: no hot path (POST only) |
| 6 MCP read-only | 5 |
| 7 Svelte view | 6 |
| 8 four gates + lowest-direct + no-SQLAlchemy | 5, 7 (gated logs: coordinator) |
| 9 live check + leased database (skipped ⇒ unverified) | 0, 1, 3, 7 |
| 10 handoff current | every commit |

## Leased-database evidence (council round 2)

The implementer runs the leased tests (`SHARPIT_TEST_POSTGRES_URL` from its own `agentctl lease database`) and records
the command in `handoff.md`, but **that is not the evidence**. Before the merge the coordinator runs the same tests with
its own lease and writes `gate/leased-pg.log` in the integration worktree, the lane head SHA on its first line. If the
tests skipped there, the lane is **unverified**: it may merge, but it does not meet the committed definition of done,
and the morning report says so. `test_read_only_wrapper_rejects_write` and `test_autocommit_engine_is_unavailable` must
appear as passed (not skipped) in `gate/leased-pg.log`.

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/A-postgresql/`)

- **Implementer, in the lane worktree:** `handoff.md` (last green command, next step, open findings, live-check
  requests), `findings.md` (`finding → test → red output`, each row `fixed` + red-test name or `parked` + reason),
  `field-map.md` (the field map above), `checklist.md` (the ten §6.1 items above in the spec's order, each with an evidence
  path or `N/A` + reason). `handoff.md` also holds the lease id and the leased-PG run. Review includes `ponytail-review` (touches `sqla.py`).
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`, reviewer id ≠
  implementer id, head SHA), `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path (`lane_gate.py` refuses it).
