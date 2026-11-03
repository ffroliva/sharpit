# Lane A-mysql: the `mysql` panel

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `A-mysql` (worktree `C:\development\github\sharpit-wt\0.5.0-A-mysql`, branch `lane/0.5.0-A-mysql`) |
| **Goal** | BootUI's `MySqlInsightReport` from an explicit, bounded, **verified read-only** POST through the app's own engine; GET serves the last result. |
| **Spec** | §5, §5.0, §5.7; 0.4.0 spec §6.4 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §6; golden `mysql/captured.json` (`NOT_READ` only; a post-read golden needs O1) |
| **Template** | A-postgresql: `src/sharpit/engine/collectors/postgresql/` (`limits.py`, `queries.py`, `querytext.py`, `sections.py`, `service.py`) |
| **Worker** | agy-flavio, Gemini 3.8; reviewer codex |
| **Council** | not required (the read-only path is F5b's, under its council) |
| **Depends on** | F5b merged (§5.0: `run_db_read(read_only=True)` works on MySQL/MariaDB only after F5b Task 3; on `main` `bounded_read_only` refuses every non-PostgreSQL dialect, `sqla.py:612-613`) |
| **May touch** | `src/sharpit/engine/collectors/mysql/` (new), `src/sharpit/fastapi/routes/mysql.py`, `src/sharpit/engine/panels04/mysql.py`, `ui/src/lib/panels04/mysql.ts`, `src/sharpit/engine/tools04/mysql.py`, `ui/src/views/MySql.svelte`, `ui/tests/component/MySql.test.ts`, `tests/engine/collectors/mysql/`, `tests/fastapi/test_mysql_api.py`, `tests/fastapi/test_mysql_leased.py`, `tests/safety/test_a_mysql_safety.py` (declares `mysql_read` as a CLI action), `tests/masking/test_a_mysql_masking.py`, `tests/fixtures/bootui/2.2.0/mysql/nullable.json`, the lane folder |
| **Must NOT touch** | `engine/sqla/` (a needed change stops the lane: coordinator routes it to the `engine/sqla` chain), `settings.py`, `engine/collectors/postgresql/` |

**Architecture:** `service.read(ctx)` → `run_db_read(read_only=True, statement_timeout=5, wall_timeout=15)` (never
`bounded()`) → capability probe (`@@version`, `@@version_comment`, `@@performance_schema`) → one function per section,
each inside `begin_nested()`, each bounded by its `mysql_max_*` setting and `LIMIT`. **Every statement-text field**
(digest text, `PROCESSLIST_INFO`, `events_statements_current.SQL_TEXT`, lock-wait query columns) goes through the SQL
normaliser and the masker, cut at 400 chars. Driver errors pass through the masker (DSN passwords).

## Must-cover

`test_report_golden_parity`, `test_mysql_read_uses_verified_read_only_path`, `test_autocommit_engine_is_unavailable`,
`test_unknown_driver_unavailable`, `test_statement_text_masked`, `test_session_current_statement_masked`,
`test_driver_error_dsn_password_masked`, `test_read_only_blocks_read`, `test_inactive_mysql_paths_404`,
`test_mysql_get_no_side_effects`, `test_mcp_tools_list_has_only_get`, `test_read_only_wrapper_rejects_write`
(leased), `test_full_read_against_mysql_84` (leased).

## Tasks

### Task 1: contract first
- [ ] `test_report_golden_parity` (`NOT_READ` shape: red on the skeleton report `{}`), `field-map.md`, `nullable.json`.

### Task 2: sections (engine, no I/O)
- [ ] Red commit (skeleton section functions return empty rows; assertions on row values): `test_statement_text_masked`,
  `test_session_current_statement_masked` (`PROCESSLIST_INFO` holding `password='x'`), `test_row_limits_truncate_and_flag`,
  `test_mariadb_capabilities_differ`, `test_performance_schema_off_is_a_diagnostic`, `test_changes_between_reads`
  (`# ported: MySqlValuesTests.*`, `MySqlRowLimitsTests.*`, `MySqlMariaDbTests.*`, `MySqlComparisonTests.*`).
  Implement. Commit `feat: mysql insight sections`.

### Task 3: service, routes, MCP, safety
- [ ] Red commit: `test_mysql_read_uses_verified_read_only_path` (spy: `sqla.bounded` never called,
  `bounded_read_only` called once), `test_autocommit_engine_is_unavailable`, `test_unknown_driver_unavailable`,
  `test_driver_error_dsn_password_masked`, `test_read_only_blocks_read` (403), `test_inactive_mysql_paths_404`,
  `test_mysql_get_no_side_effects` (statement spy: GET runs no SQL), `test_mcp_tools_list_has_only_get`
  (`get_mysql_report`; `mysql_read` CLI-only). Implement; flag on. Commit `feat: mysql panel`.

### Task 4: leased MySQL (coordinator runs)
- [ ] `tests/fastapi/test_mysql_leased.py` (`SHARPIT_TEST_MYSQL_URL`, `pymysql` from the test extra):
  `test_read_only_wrapper_rejects_write`, `test_full_read_against_mysql_84`. Coordinator: MySQL 8.4 lease,
  `gate/leased-mysql.log`; skipped = unverified (F5-gate's leased mapping enforces it).

### Task 5: view and live check
- [ ] Svelte view (reference `views/MySql.vue`; layout from `PostgreSql.svelte`), vitest. Commit `feat: mysql view`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/A-mysql/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
