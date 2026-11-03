# Lane A-database-advisor: the `database-advisor` panel

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `A-database-advisor` (worktree `C:\development\github\sharpit-wt\0.5.0-A-database-advisor`, branch `lane/0.5.0-A-database-advisor`) |
| **Goal** | BootUI's database advisor: 33 portable checks over a bounded, read-only POST scan of the app's engines plus the mapped models and the SQL Trace ring; GET serves the cached report; paged violations. |
| **Spec** | §5, §5.8; 0.4.0 spec §6.4 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §4; BootUI `docs/DATABASE-ADVISOR-CHECKS.md` and `engine/databaseadvisor/` (rule texts); golden `database-advisor/captured.json` (pre-scan) + G0's `scanned.captured.json` if present |
| **Worker** | codex gpt-6-luna, high; reviewer Opus |
| **Council** | not required (database access rules are 0.4.0 §6.4, unchanged); `ponytail-review` mandatory (touches `engine/sqla/`) |
| **Depends on** | F5; R-transactions merged (R0: `engine/sqla/`); A-mysql merged (leased MySQL, vendor SQL conventions) |
| **May touch** | `src/sharpit/engine/sqla/inspect.py` (F5's empty module: `inspect()`-based catalog reads, bounded), `src/sharpit/engine/collectors/database_advisor/` (new: `catalog.py` (DTOs from the inspector rows), `rules_schema.py`, `rules_orm.py`, `rules_runtime.py`, `rules_driver_pool.py`, `rules_vendor.py`, `report.py`), `src/sharpit/fastapi/routes/database_advisor.py` (F stub), the flag files, `src/sharpit/engine/tools04/database_advisor.py`, `ui/src/views/DatabaseAdvisor.svelte` + test, `docs/database-advisor-checks.md`, `tests/engine/collectors/database_advisor/`, `tests/engine/test_sqla_inspect.py`, `tests/fastapi/test_database_advisor_api.py`, `tests/fastapi/test_database_advisor_leased.py`, `tests/safety/test_a_database_advisor_safety.py`, `tests/masking/test_a_database_advisor_masking.py`, `tests/test_database_advisor_docs_table.py`, `tests/fixtures/bootui/2.2.0/database-advisor/nullable.json`, the lane folder |
| **Must NOT touch** | `engine/sqla/` modules other than `inspect.py`; `engine/capture/sqltrace.py` (read its report only); `engine/collectors/data.py` (call its model walker, never edit); `settings.py` |

**Architecture:** POST → `run_db_read(read_only=True)` → `sqla.inspect.catalog(conn, bounds)` returns plain dicts
(tables ≤ 300, columns ≤ 300 per table, indexes ≤ 100 per table, vendor rows ≤ 500), cooperative 20 s budget →
rules (pure functions over the catalog, the mapped models from `install(models=...)` read without configuring mappers,
the SQL Trace report, the engine's pool class and URL query parameters; the password is never read). Dialect gating:
`DB-PG-*` on PostgreSQL, `DB-MYSQL-*` on MySQL/MariaDB, `DB-ORACLE-*` dropped ([vendor], listed); others `SKIPPED`
with a reason.

## Review Focus

1. A GET runs no SQL and configures no mapper.
2. Truncation is reported (`truncated: true`, diagnostic), never silent.
3. Driver/pool rules read the URL query and pool class only; `url.password` never touched (spy).

## Tasks

### Task 1: contract and catalogue
- [ ] Red commit: `test_report_golden_parity` (pre-scan; post-scan if G0), `test_docs_table_matches_registry` (33 P,
  the rest dropped with reason), field map, `nullable.json`.

### Task 2: bounded catalog reads (`engine/sqla/inspect.py`)
- [ ] Red commit on sqlite + the leased PostgreSQL: `test_table_bound_truncates` (1,000 tables → 300,
  `truncated`), `test_index_bound_per_table`, `test_catalog_inside_read_only_wrapper` (a write attempted by a test
  hook inside the scan is rejected), `test_catalog_timeout_is_a_diagnostic`. Implement. Commit
  `feat: bounded catalog reads for the database advisor`.

### Task 3: rules (one commit per family)
- [ ] Red commits, one test per check (`# ported: DatabaseAdvisorAuditRulesTests.<method>` where present):
  schema (FK without index, table without PK, nullable FK, duplicate index, wide varchar PK, ...), orm (relationship
  without `lazy` choice on a hot path, missing `index=True` on a filtered column seen in SQL Trace, ...), runtime
  (`DB-RUNTIME-001` from the SQL Trace ring), driver/pool (`pool_pre_ping` off, `NullPool` under a server, no
  `pool_recycle` on MySQL, ...), vendor (`DB-PG-*`, `DB-MYSQL-*`). `test_unsupported_dialect_skips_vendor_rules`.
  `test_password_never_read` (spy on `URL.password`).

### Task 4: routes, MCP, safety
- [ ] Red commit: `test_autocommit_engine_is_unavailable`, `test_read_only_blocks_scan`,
  `test_inactive_database_advisor_paths_404`, `test_database_advisor_get_no_side_effects` (no SQL, no mapper
  configuration: 0.4.0's `test_get_never_configures_mappers` pattern), `test_mcp_tools_list_has_only_get`
  (`get_database_advisor_report`, `get_database_advisor_rule_violations`; `database_advisor_scan` CLI-only),
  `test_statement_text_masked` (violation previews from SQL Trace masked). Flag on. Commit
  `feat: database advisor panel`.

### Task 5: leased databases, view, live check
- [ ] `tests/fastapi/test_database_advisor_leased.py` on PostgreSQL and MySQL (coordinator runs;
  `gate/leased-pg.log`, `gate/leased-mysql.log`). Svelte view (reference `views/DatabaseAdvisor.vue`), vitest; live
  check on `examples/fastapi_sqla`. Commit `feat: database advisor view`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/A-database-advisor/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
