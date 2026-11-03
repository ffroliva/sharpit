# Handoff: lane A-dbadv-1 (0.5.0)

Implementer: Claude Code (claude-opus-5-5)
Branch `lane/0.5.0-A-dbadv-1` from `24c72b7` (release/0.5.0). Status: DONE_WITH_CONCERNS (leased PG/MySQL tests and the
post-scan golden are unverified here; see Open questions).

## Done

| Task | Red SHA | Fix SHA | What |
|---|---|---|---|
| 1 contract | — | `31bce50` (docs, nullable) | Controller route list copied (below); `docs/database-advisor-checks.md` (48 rows, 33 P); `nullable.json`; field map |
| 2 bounded catalog | `dbe78b8` | `110f166` | `sqla.inspect.catalog(conn, CatalogBounds)`: 300 tables / 300 columns / 100 indexes / 500 vendor rows / cooperative 20 s; server limits by name |
| 3 rules | `f534c99` | `f9d6006` | DB-SCHEMA-001..007, DB-DRIVER-007/008, DB-POOL-001..004 |
| 4 panel | `31bce50` | `f2e1e23` | report on F5a's core with the scope hook, routes, MCP reads + CLI-only scan, safety rows, flag on |
| 5 view | `3a282ef` (vitest) | `2c5e546` | `DatabaseAdvisor.svelte` on `AdvisorPanel`, datasource and diagnostic lists; bundle rebuilt |

Red tables: `findings.md` (53 pytest reds, 4 vitest reds, 7 mutation-proven pins).

## Contract surface inventory (BootUI 2.2.0 `DatabaseAdvisorController`, read from `boot-ui-ref` @ v2.2.0)

- `GET {api}/database-advisor` → `report()`; `POST {api}/database-advisor/scan` → `scan()`;
  `GET {api}/database-advisor/rules/{ruleId}/violations?scanId&offset&limit` (`AdvisorViolationsEndpoint`).
- **There is no changes route and no rule-detail route** in the 2.2.0 controller (nor in `AdvisorViolationsEndpoint`).
  Changes travel in `violationDetails.changes`; a rule's detail is its violations page.
  `test_changes_and_rule_detail_routes` pins exactly this: the violations page works (and answers the contract 400
  without `scanId`), `violationDetails.changes` is present, `/changes` and `/rules/{id}` are 404.
- MCP: `get_database_advisor_report`, `get_database_advisor_rule_violations`; `database_advisor_scan` CLI-only (§14).
  CLI paths from BootUI `CliCommandPaths`: `db scan`, `db report`, `db violations`.

## Must-cover

| Test | Exists | Passes |
|---|---|---|
| tests/fastapi/test_database_advisor_api.py::test_report_golden_parity | yes | yes |
| tests/fastapi/test_database_advisor_api.py::test_post_scan_golden_parity | yes | skips: `post-scan golden absent (G0)` |
| tests/engine/test_sqla_inspect.py::test_table_bound_truncates | yes | yes |
| tests/engine/test_sqla_inspect.py::test_index_bound_per_table | yes | yes |
| tests/engine/test_sqla_inspect.py::test_catalog_inside_read_only_wrapper | yes | yes |
| tests/fastapi/test_database_advisor_api.py::test_dbadv_read_uses_verified_read_only_path | yes | yes |
| tests/fastapi/test_database_advisor_api.py::test_autocommit_engine_is_unavailable | yes | yes |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_password_never_read | yes | yes (pin) |
| tests/fastapi/test_database_advisor_api.py::test_query_string_secret_never_read_or_emitted | yes | yes |
| tests/masking/test_a_database_advisor_masking.py::test_driver_error_dsn_password_masked | yes | yes |
| tests/masking/test_a_database_advisor_masking.py::test_statement_text_masked | yes | yes |
| tests/fastapi/test_database_advisor_api.py::test_read_only_blocks_scan | yes | yes |
| tests/fastapi/test_database_advisor_api.py::test_inactive_database_advisor_paths_404 | yes | yes (pin) |
| tests/safety/test_a_database_advisor_safety.py::test_database_advisor_get_no_side_effects | yes | yes |
| tests/fastapi/test_database_advisor_api.py::test_mcp_tools_list_has_only_get | yes | yes |
| tests/fastapi/test_database_advisor_api.py::test_changes_and_rule_detail_routes | yes | yes |
| tests/fastapi/test_database_advisor_leased.py::test_read_only_wrapper_rejects_write[postgresql] | yes | skips without `SHARPIT_TEST_POSTGRES_URL` (leased) |
| tests/fastapi/test_database_advisor_leased.py::test_read_only_wrapper_rejects_write[mysql] | yes | skips without `SHARPIT_TEST_MYSQL_URL` (leased; MySQL may stay unverified) |

Also: `tests/engine/test_sqla_inspect.py::test_catalog_timeout_is_a_diagnostic`, `tests/test_database_advisor_docs_table.py::test_docs_table_matches_registry`.

## Decisions

1. **The 33 portable checks** (the contract's count, not reconstructable from it): SCHEMA 001-007, 010; HIB 002-007,
   009, 010; RUNTIME-001; PG 001-005; MYSQL 001-003; DRIVER 007, 008; POOL 001-004; SERVER 001, 002. Dropped (15,
   each with its reason in the doc): ORACLE 001-003 (no verified read-only path), DRIVER 001-006 and 009 (JDBC
   driver properties with no Python analogue, or outside the URL allow-list), SERVER 003-007 (server-wide
   maintenance/observability the postgresql/mysql panels already show). DB-SCHEMA-010 and SERVER-001/002 need vendor
   catalog reads, so they are listed `planned (A-dbadv-2)` (vendor rules).
2. **Driver/pool on SQLAlchemy:** DB-DRIVER-007 = engine `echo`; DB-DRIVER-008 = no `connect_timeout` URL key on
   psycopg/psycopg2/pg8000 (other drivers `SKIPPED`: they have their own default). Pool: `pool_recycle` is the
   lifetime, `pool_pre_ping` settles DB-POOL-001 as covered; max size = `pool_size + max_overflow`, an overflow of
   -1 is unbounded (fires DB-POOL-002); NullPool/StaticPool have no fixed maximum (`SKIPPED`); SQLite `SKIPPED`.
   Pool numbers are read from the pool object's attributes (`_recycle`, `_pre_ping`, `_max_overflow`, `size()`),
   defensively.
3. **URL allow-list** `connect_timeout`, `charset`, `sslmode`: key names only (`key in query`), never a value, never
   `url.password` (pinned by `test_password_never_read`, `test_query_string_values_are_never_kept`).
   `pool_pre_ping`/`pool_recycle` are engine arguments, so they come from the pool, not the URL.
4. **Single-flight:** `run_scan` holds `singleflight:database-advisor-scan` (409) across the async reads and any worker
   a timeout left running (`Flight`); the core gets its own uncontended `SingleFlight`.
5. **Error text:** a datasource failure keeps only the error's first line (`sqla.inspect.error_text`): SQLAlchemy puts
   the statement and parameters on the following lines. The core then masks it (DSN userinfo, key=value).
6. **Rules** take a `Source` (catalog dict + engine facts) and return findings or a skip reason; a rule that can judge
   no datasource is `SKIPPED` (counted in `rulesSkipped`, `INFO` diagnostic), never a fabricated `PASS`. The rule
   registration list is `database_advisor/__init__.py::RULES`, which A-dbadv-2 extends.
7. **The engine's sqla gatekeeper:** only `engine/sqla/inspect.py` changed inside `engine/sqla/`; collectors call it.
8. `results[].suppressedCount` is not emitted and `sampleLocations` is (shared core `RuleResult.to_dto`, outside this
   lane's May-touch); `suppression` is always `none()`. Post-scan parity will show it when G0 lands.
9. Task 3's red commit was amended before its fix (formatting/E501 of the new test files only; re-red-checked).

## Live check (in-process)

`test_scan_reports_schema_findings_on_sqlite` and `test_cli_scan_and_commands` install sharpit on a FastAPI app with
a real SQLite engine and drive `POST /scan`, `GET`, the violations page and the CLI tool through `TestClient`. No
port was bound (COMMON: no dev servers on shared ports).

## Gates (at head)

At `305cbbe` (evidence commit; code unchanged since `2c5e546`): `ruff check` clean, `ruff format --check` clean,
`pyright` 0 errors, vitest (DatabaseAdvisor + panels04) 18 passed, `tsc --noEmit` clean, `npm run build` committed.
Full suite `pytest -q -n 4`: **4898 passed, 16 skipped, 1 failed** — `tests/engine/advisors/test_registry.py::
test_0_4_advisor_specs_are_registered_and_gated` (Open question 3). Lane gate evidence check (`--accept-unverified`):
the only refusals are the coordinator's (`review.md`, `gate/lowest-direct.log`, `gate/no-sqlalchemy.log`, the leased
logs); nothing about findings.md, handoff.md or reds.

## Open questions for the coordinator

1. Run `tests/fastapi/test_database_advisor_leased.py` on leased PostgreSQL and MySQL (`gate/leased-pg.log`,
   `gate/leased-mysql.log`). The MySQL server-settings read uses `SHOW SESSION VARIABLES ... WHERE` without a
   savepoint; the PostgreSQL one runs in a savepoint inside the read-only transaction.
2. The rebuilt UI bundle (`src/sharpit/ui/static/`) is outside the plan's May-touch list; the brief asks for it.
3. `tests/engine/advisors/test_registry.py::test_0_4_advisor_specs_are_registered_and_gated` (F5a-core, outside this
   lane's May-touch) asserts `advisor_for("DB-TEST-001") is None`, which holds only while the `database-advisor` flag
   is off: the registry's `_prefixed` spec owns every `DB-...` id once the flag is on. It fails as soon as this lane
   flips the flag (the same will happen to `SEC-`/`ARCH-`/`FASTAPI-` when B-security, C-architecture, C-fastapi flip
   theirs). Suggested fix (coordinator): `assert advisor_for("DB-TEST-001") is (by_id["database-advisor"] if
   IMPLEMENTED["database-advisor"] else None)`, or pick an id under a prefix no advisor owns. Not edited here.

## How to resume

All work is committed. Next: A-dbadv-2 adds `rules_orm/rules_runtime/rules_vendor.py` to `RULES` and flips the doc's
status column.
