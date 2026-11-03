# Lanes A-dbadv-1 and A-dbadv-2: the `database-advisor` panel

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.
> Two lanes, run in order; each has its own worktree, evidence folder and gate run.

| | A-dbadv-1 | A-dbadv-2 |
|---|---|---|
| **Worktree / branch** | `C:\development\github\sharpit-wt\0.5.0-A-dbadv-1`, `lane/0.5.0-A-dbadv-1` | `...\0.5.0-A-dbadv-2`, `lane/0.5.0-A-dbadv-2` |
| **Goal** | Bounded read-only catalog reads, schema and driver/pool rules, the panel (routes, tools, view) on F5a's core | ORM rules (configured-gate), `DB-RUNTIME-001`, vendor rules (`DB-PG-*`, `DB-MYSQL-*`) |
| **Worker** | codex gpt-6-luna, high; reviewer Opus; `ponytail-review` mandatory (touches `engine/sqla/`) | codex or claude-flavio; reviewer the other |
| **Council** | not required (0.4.0 §6.4 + F5b's council) | not required |
| **Depends on** | F5a-core, F5b (R0 `engine/sqla/`: it owns `sqla/inspect.py`, a different file from R-transactions' `events.py`, so no edge to R-transactions). Lease scheduling: after A-mysql frees the MySQL lease; with no lease, PostgreSQL + SQLite only and MySQL `unverified` | A-dbadv-1 merged |
| **May touch** | `tests/engine/advisors/test_registry.py` (`test_0_4_advisor_specs_are_registered_and_gated`: replace the unowned sample id `DB-TEST-001` with one no registered prefix owns; A-dbadv-1 only), `src/sharpit/ui/static/` (rebuilt bundle); coordinator amendment 2026-11-03; `src/sharpit/engine/sqla/inspect.py`, `src/sharpit/engine/collectors/database_advisor/{__init__,catalog,rules_schema,rules_driver_pool,report}.py`, `src/sharpit/fastapi/routes/database_advisor.py`, `src/sharpit/engine/panels04/database_advisor.py`, `ui/src/lib/panels04/database_advisor.ts`, `src/sharpit/engine/tools04/database_advisor.py`, `ui/src/views/DatabaseAdvisor.svelte`, `ui/tests/component/DatabaseAdvisor.test.ts`, `docs/database-advisor-checks.md`, `tests/engine/collectors/database_advisor/`, `tests/engine/test_sqla_inspect.py`, `tests/fastapi/test_database_advisor_api.py`, `tests/fastapi/test_database_advisor_leased.py`, `tests/safety/test_a_database_advisor_safety.py` (declares `database_advisor_scan`), `tests/masking/test_a_database_advisor_masking.py`, `tests/test_database_advisor_docs_table.py`, `tests/fixtures/bootui/2.2.0/database-advisor/nullable.json`, the lane folder | `src/sharpit/engine/collectors/database_advisor/{rules_orm,rules_runtime,rules_vendor}.py`, the rule registration list in `database_advisor/__init__.py`, `docs/database-advisor-checks.md` (status column), `tests/engine/collectors/database_advisor/test_rules_{orm,runtime,vendor}.py`, the lane folder |
| **Must NOT touch** | `engine/sqla/` except `inspect.py`; `engine/capture/sqltrace.py` (report API only); any collector (rule 3: the mapper walk is `engine/models.py`, F5a-harness); `settings.py` | `engine/sqla/`, `engine/models.py` (calls it, never edits it), routes, tools, view |

**Architecture (A-dbadv-1):** POST → `run_db_read(read_only=True)` (F5b's verified path on PostgreSQL, MySQL/MariaDB,
SQLite; other dialects → `unavailableReason`) → `sqla.inspect.catalog(conn, bounds)` returns plain dicts (tables ≤ 300,
columns ≤ 300 per table, indexes ≤ 100 per table, vendor rows ≤ 500; cooperative 20 s) → rules → F5a's core with the
database-advisor scope hook (`dataSourceNames`, `dataSources`, `diagnostics`, `tablesAnalyzed`, `rulesSkipped`,
`rulesErrored`, `suppression`, `truncated`). Driver/pool rules read the pool class and an **allow-list of URL query
keys** (`pool_pre_ping`, `pool_recycle`, `connect_timeout`, `charset`, `sslmode` presence only); never a value, never
`url.password`.

**Architecture (A-dbadv-2):** ORM rules read mappers only through `engine/models.py`'s configured-gate: an
unconfigured registry makes those rules `SKIPPED` with a reason, never `configure_mappers()` (`mapper.relationships`
would configure). `DB-RUNTIME-001` reads the SQL Trace report. Vendor rules run on their dialect, `SKIPPED` elsewhere;
`DB-ORACLE-*` dropped (vendor), listed.

**Contract surface inventory** (WAVE-A §4, `DatabaseAdvisorController`): `GET {api}/database-advisor`,
`POST {api}/database-advisor/scan`, `GET {api}/database-advisor/rules/{id}/violations`, the changes route and the
rule-detail route (exact suffixes copied from the controller in Task 1, built, not omitted); MCP
`get_database_advisor_report`, `get_database_advisor_rule_violations`; `database_advisor_scan` CLI-only (§14).

## Must-cover

A-dbadv-1: `test_report_golden_parity`, `test_post_scan_golden_parity` (asserts `scanned.captured.json`/`violations.captured.json` with `assert_parity` and
`assert_enum_values`; skips with reason `post-scan golden absent` until G0 lands, which the gate reports as
`unverified`), `test_table_bound_truncates`, `test_index_bound_per_table`,
`test_catalog_inside_read_only_wrapper`, `test_dbadv_read_uses_verified_read_only_path`, `test_autocommit_engine_is_unavailable`,
`test_password_never_read`, `test_query_string_secret_never_read_or_emitted`, `test_driver_error_dsn_password_masked`,
`test_statement_text_masked`, `test_read_only_blocks_scan`, `test_inactive_database_advisor_paths_404`,
`test_database_advisor_get_no_side_effects`, `test_mcp_tools_list_has_only_get`, `test_changes_and_rule_detail_routes`,
`test_read_only_wrapper_rejects_write` (leased PG + MySQL).

A-dbadv-2: `test_scan_never_configures_mappers`, `test_unconfigured_registry_skips_orm_rules`,
`test_unsupported_dialect_skips_vendor_rules`, one test per ORM/runtime/vendor rule.

## A-dbadv-1 tasks

### Task 1: contract and catalogue
- [ ] Copy the controller's route list into this file's inventory. Red commit: `test_report_golden_parity` (pre-scan:
  a pin with the scope hook; post-scan red if G0), `test_docs_table_matches_registry` (33 P, the rest dropped with
  reason), field map, `nullable.json`.

### Task 2: bounded catalog reads (`engine/sqla/inspect.py`)
- [ ] Red commit (skeleton `catalog` returns `{}`; assertions on counts and flags): `test_table_bound_truncates`
  (1,000 sqlite tables → 300, `truncated is True`), `test_index_bound_per_table`, `test_catalog_inside_read_only_wrapper`
  (sqlite: a write attempted from a test hook inside the scan fails with "readonly database"),
  `test_catalog_timeout_is_a_diagnostic`. Implement. Commit `feat: bounded catalog reads for the database advisor`.

### Task 3: schema and driver/pool rules
- [ ] Red commits, one test per check (`# ported: DatabaseAdvisorAuditRulesTests.<method>` where present), plus
  `test_password_never_read` (spy on `URL.password`), `test_query_string_secret_never_read_or_emitted`
  (`?password=x&sslpassword=y&token=z`: no value in the report or MCP output). Commit per family.

### Task 4: routes, MCP, safety
- [ ] Red commit: `test_dbadv_read_uses_verified_read_only_path` (spy: `bounded` never called),
  `test_autocommit_engine_is_unavailable`, `test_driver_error_dsn_password_masked`, `test_statement_text_masked`,
  `test_read_only_blocks_scan`, `test_inactive_database_advisor_paths_404`, `test_database_advisor_get_no_side_effects`,
  `test_mcp_tools_list_has_only_get`, `test_changes_and_rule_detail_routes`. Flag on. Commit `feat: database advisor panel`.

### Task 5: leased databases, view, live check
- [ ] `tests/fastapi/test_database_advisor_leased.py` on PostgreSQL and MySQL (coordinator; `gate/leased-pg.log`,
  `gate/leased-mysql.log`). Svelte view (reference `views/DatabaseAdvisor.vue`), vitest; live check. Commit
  `feat: database advisor view`.

## A-dbadv-2 tasks

### Task 1: ORM rules
- [ ] Red commit: `test_scan_never_configures_mappers` (an unconfigured registry with a relationship whose target is
  a string: after the scan `registry.configured is False`), `test_unconfigured_registry_skips_orm_rules`, one test per
  `DB-HIB-*` analogue. Implement. Commit `feat: database advisor ORM rules`.

### Task 2: runtime and vendor rules
- [ ] Red commit: `DB-RUNTIME-001` from a seeded SQL Trace ring; `DB-PG-*` on PostgreSQL (leased), `DB-MYSQL-*` on
  MySQL (leased; skip = unverified), `test_unsupported_dialect_skips_vendor_rules`. Implement. Commit
  `feat: database advisor runtime and vendor rules`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/A-dbadv-1/` and `.../A-dbadv-2/`: `handoff.md`, `findings.md`, `field-map.md`,
`checklist.md`.
