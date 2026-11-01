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
| **Depends on** | F (incl. `psycopg[binary]` in the test extra — see Task 0), D1 |
| **May touch** | `src/sharpit/engine/sqla.py` (**only** `run_db_read` keyword-only parameters and the new `bounded_read_only`; this lane owns these edits), `src/sharpit/engine/collectors/postgresql/` (new package), `src/sharpit/fastapi/routes/postgresql.py` (F stub), the panel's pre-registered rows (flag flip), F's MCP stubs, `ui/src/views/Postgresql.svelte` (+ test), `tests/engine/test_sqla_read_only.py`, `tests/engine/postgresql/`, `tests/fastapi/test_postgresql_api.py`, `tests/fixtures/bootui/2.2.0/postgresql/*`, lane folder |
| **Must NOT touch** | §10.3 protected files (no dependency edit: a missing driver is a coordinator `Ruling:`); `bounded` (`sqla.py:352-380`) and its callers `collectors/alembic.py`, `collectors/health.py` — **unchanged**; other lanes' modules |

**Architecture:** `run_db_read` (`sqla.py:383`) gains `*, wall_timeout: float | None = None, statement_timeout: float |
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
  `current_setting('transaction_read_only') = 'on'`; if either fails no catalog SQL runs → `unavailableReason`.
- Every optional catalog query inside `begin_nested()`, always; one failing query never aborts the transaction.
- No driver imported by sharpit; SQL through the app's engine (async engines via `run_sync`, `sqla.py:402-408`).
- BootUI bounds: statement 5 s, lock 2 s, overall 15 s; statement text ≤ 400 chars; curated settings allow-list;
  row limits `postgresql_max_sessions=100, max_statements=100, max_indexes=500, max_tables=200,
  max_vacuum_tables=200, max_replicas=10, max_settings=40` (env `SHARPIT_POSTGRESQL_*`, 1..2147483646, invalid →
  default + warning). Constants `STATEMENT_TIMEOUT = 5.0`, `LOCK_TIMEOUT = 2.0`, `READ_BUDGET = 15.0`.
- Statement and session query text masked (`normalize` from `engine/capture/sqltrace.py:231`, then
  `ctx.masker.mask_text`, then 400-char cut); client addresses follow the exposure policy; setting values withheld
  under `METADATA_ONLY`.
- Errors strings from BootUI with `BootUI`→`sharpit`. Ported tests cite `# ported:`. Red is an assertion. PT018.

## Review Focus

1. **AUTOCOMMIT engine** (`engine.execution_options(isolation_level="AUTOCOMMIT")`): `SET TRANSACTION READ ONLY` is a
   no-op outside a transaction. Expect **zero** catalog statements issued and `unavailableReason`. Pinned in Task 1:
   `test_autocommit_engine_fails_closed` (leased PG) and `test_autocommit_fails_closed_without_catalog_sql` (fake conn).
2. **A write inside the wrapper.** `fn` runs `CREATE TEMP TABLE` / `INSERT`. Expect PostgreSQL's read-only error, the
   app's table untouched. Pinned in Task 1: `test_write_inside_read_only_is_rejected` (leased PG).
3. **`pg_stat_statements` absent, not preloaded, or permission denied** after an earlier section succeeded. Expect
   `statements` section `SKIPPED` with BootUI's hint, every later section still `AVAILABLE`. Pinned in Task 3:
   `test_failed_query_does_not_poison_later_sections` (`# ported: PostgresCollectorsTests.aFailedQueryDoesNotPoisonTheSectionsReadAfterIt`).
4. **Secrets in catalog text.** `pg_stat_activity.query` holding `password='...'`, a dollar-quoted body, an
   `E'..\'..'` string; a DSN with a password in an error. Expect masked. Pinned in Task 2 (`querytext` tests) and Task 5
   masking corpus rows.
5. **A non-PostgreSQL engine and no engine.** sqlite registered → diagnostic `"Skipped: this datasource is SQLite,
   not PostgreSQL."`, no read; nothing registered → `DISABLED` with BootUI's "No PostgreSQL datasource was found…".
   Pinned in Task 4: `test_non_postgres_engine_is_skipped`, `test_no_engine_is_disabled`.

---

### Task 0: Pre-flight

- [ ] **Step 1:** `uv run --no-sync python -c "import psycopg"` succeeds (F's test deps). If not, record it in
  `handoff.md` and ask the coordinator for a `Ruling:`; the lane cannot edit dependency lists.
- [ ] **Step 2:** `agentctl.py lease database` → the reference compose's Postgres; export
  `SHARPIT_TEST_POSTGRES_URL=postgresql+psycopg://...` (tests read it; absent → skip with reason, and the lane counts
  **unverified**, §6.1.9). Record the lease id in `handoff.md`.

### Task 1: `run_db_read(read_only=True)` and `bounded_read_only` in `engine/sqla.py`

**Files:** Modify `src/sharpit/engine/sqla.py:383-424`; add `bounded_read_only` after `bounded`; Test
`tests/engine/test_sqla_read_only.py`.

**Interfaces:** Produces
- `run_db_read(engine, fn, timeout, *, executor=None, done=None, wall_timeout: float | None = None,
  statement_timeout: float | None = None, read_only: bool = False) -> T` — `asyncio.timeout(wall_timeout or timeout)`;
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
  - leased PG (`@pytest.mark.skipif(not URL)`): `test_write_inside_read_only_is_rejected`,
    `test_autocommit_engine_fails_closed`, `test_async_engine_read_only` (`postgresql+psycopg` async).
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
`ctx.capture.engine_registry.engines()` with `dialect.name == "postgresql"`). Report keys `localOnly, disclaimer,
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
rows in `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (rows: `pg_stat_activity.query` with
`STRIPE_KEY`, `pg_stat_statements.query` with `password=`, an error carrying a DSN password).

**Interfaces:** `GET {api}/postgresql`, `POST {api}/postgresql/read`. MCP `get_postgresql_report` (read);
`postgresql_read` `action=True` (CLI-only). `actionCapable=True`; read-only → 403 on POST.

- [ ] **Step 1:** Tests: `test_golden_parity` (`assert_parity("postgresql", "report", body)` after a leased read; the
  `NOT_READ` report against the golden otherwise), `getReturnsTheNotReadReportBeforeAnyRead`,
  `readPerformsTheReadAndReturnsAReport`, `getReturnsTheLastReadReportAfterARead` (`# ported: PostgresqlControllerTests.*`),
  `test_get_no_side_effects` (no socket, no SQL: a `before_cursor_execute` spy sees nothing), `test_read_only_403`,
  `test_mcp_read_tool_only`, the corpus rows.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS + full gate (background). Commit
  `feat: postgresql panel routes and MCP read tool`.

### Task 6: Svelte view

**Files:** `ui/src/views/Postgresql.svelte`, `.test.ts`.

- [ ] **Step 1:** vitest: `NOT_READ` shows the read button and message; sections render status/reason/hint;
  `changes` render only from the second read; the read button is hidden when `readOnly`. Reference
  `views/Postgresql.vue`.
- [ ] **Step 2:** FAIL → implement → `npm --prefix ui run check` + tests PASS. Commit `feat: postgresql view`.

### Task 7: Live check and evidence

- [ ] **Step 1:** `examples/fastapi_sqla` pointed at the leased Postgres (env, no code change) and tiny-ledger-py when
  ready: GET (NOT_READ) → POST read → GET (cached). Record in `live-verify.md`.
- [ ] **Step 2:** lowest-direct + no-SQLAlchemy logs with head SHA; leased-PG test run log `pg-leased.log` (no skips).
  Release the database lease. Commit `docs: postgresql lane evidence`.

## §6.1 → task

| Item | Task |
|---|---|
| 1 parity (+ field map: every `Postgres*Dto` key → its catalog column or `null` + reason) | 3, 5 |
| 2 ported citations | 1–5 |
| 3 safety + masking (`pg_stat_statements`, `pg_stat_activity`) | 1, 2, 5 |
| 4 gatekeeper (SQL only through `sqla.run_db_read`) | 1 |
| 5 overhead budget | n/a: no hot path (POST only) |
| 6 MCP read-only | 5 |
| 7 Svelte | 6 |
| 8 gates | 5, 7 |
| 9 live + leased database (skipped ⇒ unverified) | 0, 1, 3, 7 |
| 10 handoff | every commit |

## Lane evidence checklist (`.superpowers/sdd/0.4.0/lanes/A-postgresql/`)

`handoff.md` (incl. lease id) · `field-map.md` · `checklist.md` · `findings.md` · `review.md` (`VERDICT: APPROVE`, reviewer
≠ implementer, head SHA, plus `ponytail-review`) · `gate/` (four gates, lowest-direct, no-SQLAlchemy logs, each naming the head SHA) · `pg-leased.log` ·
`live-verify.md`.
