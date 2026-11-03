# Lane A-mysql: the `mysql` panel

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `A-mysql` (worktree `C:\development\github\sharpit-wt\0.5.0-A-mysql`, branch `lane/0.5.0-A-mysql`) |
| **Goal** | BootUI's `MySqlInsightReport` from an explicit, bounded, read-only POST through the app's own engine; GET serves the last result. |
| **Spec** | §5, §5.7; 0.4.0 spec §6.4 (database access rules) |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §6; golden `mysql/captured.json` (`NOT_READ` shape only; a post-read golden needs a MySQL datasource in a capture app, spec §13 O1) |
| **Template** | A-postgresql: `src/sharpit/engine/collectors/postgresql/` (`limits.py`, `queries.py`, `querytext.py`, `sections.py`, `service.py`) and its tests; mirror the structure, not the SQL |
| **Worker** | agy-flavio, Gemini 3.8; reviewer codex |
| **Council** | not required |
| **Depends on** | F5 |
| **May touch** | `src/sharpit/engine/collectors/mysql/` (new, mirroring `postgresql/`), `src/sharpit/fastapi/routes/mysql.py` (F stub), the flag files `engine/panels04/mysql.py` + `ui/src/lib/panels04/mysql.ts`, `src/sharpit/engine/tools04/mysql.py`, `ui/src/views/MySql.svelte` + test, `tests/engine/collectors/mysql/`, `tests/fastapi/test_mysql_api.py`, `tests/fastapi/test_mysql_leased.py` (skips without `SHARPIT_TEST_MYSQL_URL`), `tests/safety/test_a_mysql_safety.py`, `tests/masking/test_a_mysql_masking.py`, `tests/fixtures/bootui/2.2.0/mysql/nullable.json`, the lane folder |
| **Must NOT touch** | `engine/sqla/` (the MySQL/MariaDB branch of `bounded_read_only` exists; a needed change stops the lane and joins the `engine/sqla/` R0 chain), `settings.py` (F5 pre-created `mysql_max_*`), `engine/collectors/postgresql/` |

**Architecture:** `service.read(ctx)` → `run_db_read(read_only=True, statement_timeout=5, wall_timeout=15)` → one
function per section, each inside `begin_nested()`, each bounded by its `mysql_max_*` setting and `LIMIT`. Capability
probe first (`SELECT @@version, @@version_comment, @@performance_schema`), so MariaDB and a disabled
`performance_schema` become section diagnostics. Statement digest text goes through the SQL normaliser and the masker,
cut at 400 chars.

## Review Focus

1. AUTOCOMMIT engine or a driver that cannot set read-only → `unavailableReason`, no statement sent.
2. A write inside the wrapper is rejected by the server (leased MySQL).
3. Digest text never carries a literal.

## Tasks

### Task 1: contract first
- [ ] Red commit: `test_report_golden_parity` (`NOT_READ` shape, every key, nulls), field map in `field-map.md` (every
  `MySql*Dto` key → Python source or `null` + reason), `nullable.json`.

### Task 2: sections (engine, no I/O in unit tests)
- [ ] Red commit with row-shaping tests per section (`# ported: MySqlValuesTests.*`, `MySqlRowLimitsTests.*`,
  `MySqlMariaDbTests.*`, `MySqlComparisonTests.*`): `test_statement_text_masked`, `test_row_limits_truncate_and_flag`,
  `test_mariadb_capabilities_differ`, `test_performance_schema_off_is_a_diagnostic`, `test_changes_between_reads`.
  Implement. Commit `feat: mysql insight sections`.

### Task 3: service, routes, MCP, safety
- [ ] Red commit: `test_autocommit_engine_is_unavailable`, `test_unknown_driver_unavailable` (a dialect name outside
  `mysql`/`mariadb` → reason names it), `test_read_only_blocks_read` (403), `test_inactive_mysql_paths_404`,
  `test_mysql_get_no_side_effects` (GET after a read runs no SQL: statement spy), `test_mcp_tools_list_has_only_get`
  (`get_mysql_report`; `mysql_read` CLI-only). Implement; flag on. Commit `feat: mysql panel`.

### Task 4: leased MySQL (coordinator runs; lane writes the tests)
- [ ] `tests/fastapi/test_mysql_leased.py`: `test_read_only_wrapper_rejects_write` (`INSERT` inside the wrapper →
  `ER_CANT_EXECUTE_IN_READ_ONLY_TRANSACTION`), `test_full_read_against_mysql_84`, `test_pymysql_and_mysqlclient`
  (parametrised on installed drivers; absent driver → skip with reason). Coordinator: `agentctl lease database`, MySQL
  8.4 container, `gate/leased-mysql.log`; skipped = unverified.

### Task 5: view and live check
- [ ] Svelte view (reference `views/MySql.vue`; layout from `PostgreSql.svelte`), vitest. Commit `feat: mysql view`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/A-mysql/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
