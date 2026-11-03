# Lane A-mysql handoff

Implementer: agy-flavio, Gemini 3.8

## Status

DONE (Tasks 1–5 complete: contract, sections, panel service/routes/MCP/safety, leased tests, Svelte view and component tests).

## Head SHA

`e9f89645467c6f7d72a991b8724705ac935d0220` (plus docs evidence commit)

## Red SHAs

- Task 1: `0637bf5965d2f0ae18a081749f338829413b771b`
- Task 2: `9106ba29db4557e7f67d89289d2f171e030440b0`
- Task 3: `fcecb89547d7c66dc8b0933580e608070b471cb7`
- Task 5 (UI vitest): `e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3`

## Tasks

| Task | Commit | What it proved |
|---|---|---|
| 1 red | `0637bf5965d2f0ae18a081749f338829413b771b` (`test:`) | `test_report_golden_parity` failed cleanly on empty skeleton report with AssertionError under tests/ |
| 1 fix | `465813a6b62ae251535f3a3419be79713d5e571a` (`feat:`) | `mysql_report` returns complete `NOT_READ` report matching `tests/fixtures/bootui/2.2.0/mysql/captured.json` |
| 2 red | `9106ba29db4557e7f67d89289d2f171e030440b0` (`test:`) | 6 section/collector tests failed cleanly with AssertionErrors under tests/ |
| 2 fix | `eb696f8f522d15940e6d0bb7c082456470c29a09` (`feat:`) | MySQL capability probe, sessions, statements, indexes, tables, lock-waits, replication, settings, metrics, and changes |
| 3 red | `fcecb89547d7c66dc8b0933580e608070b471cb7` (`test:`) | 8 service/route/MCP/safety tests failed cleanly with AssertionErrors under tests/ |
| 3 fix | `06806ab8ee43ec751cebe9a0ca8c5d26394beff5` (`feat:`) | MySQL panel service, verified read-only read execution, routes, MCP/CLI tools, panel flag on |
| 4 test | `04f441fe51cb1f357599cb5e638da062f6b3cfc2` (`test:`) | MySQL leased acceptance tests: skip cleanly without `SHARPIT_TEST_MYSQL_URL` |
| 5 red | `e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3` (`test:`) | 5 component tests failed cleanly with AssertionErrors on placeholder view |
| 5 fix | `e9f89645467c6f7d72a991b8724705ac935d0220` (`feat:`) | MySQL Svelte view and rebuilt `src/sharpit/ui/static/` bundle |

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| tests/fastapi/test_mysql_api.py::test_report_golden_parity | 0637bf5965d2f0ae18a081749f338829413b771b | `mysql/captured.json parity: localOnly: missing from payload; ...` |
| tests/engine/collectors/mysql/test_sections.py::test_statement_text_masked | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.statements) == 1`: 0 statements returned |
| tests/engine/collectors/mysql/test_sections.py::test_session_current_statement_masked | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.sessions) == 1`: 0 sessions returned |
| tests/engine/collectors/mysql/test_sections.py::test_row_limits_truncate_and_flag | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert section["rowCount"] == 2`: was 0 |
| tests/engine/collectors/mysql/test_sections.py::test_mariadb_capabilities_differ | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert maria_data.capabilities["isMariaDb"] is True`: was False |
| tests/engine/collectors/mysql/test_sections.py::test_performance_schema_off_is_a_diagnostic | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.diagnostics) >= 1`: no diagnostics returned |
| tests/engine/collectors/mysql/test_sections.py::test_changes_between_reads | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(second_changes) == 1`: 0 changes returned |
| tests/fastapi/test_mysql_api.py::test_mysql_read_uses_verified_read_only_path | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) |
| tests/fastapi/test_mysql_api.py::test_autocommit_engine_is_unavailable | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) |
| tests/fastapi/test_mysql_api.py::test_unknown_driver_unavailable | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) |
| tests/fastapi/test_mysql_api.py::test_read_only_blocks_read | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) |
| tests/fastapi/test_mysql_api.py::test_inactive_mysql_paths_404 | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) |
| tests/fastapi/test_mysql_api.py::test_mcp_tools_list_has_only_get | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert [] == ['get_mysql_report', 'mysql_read']` |
| tests/masking/test_a_mysql_masking.py::test_driver_error_dsn_password_masked | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 'could not connect to mysql' in shown` |
| tests/safety/test_a_mysql_safety.py::test_mysql_get_no_side_effects | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) |

## UI red tests (vitest)

| Test | Red SHA | Assertion message |
|---|---|---|
| ui/tests/component/MySql.test.ts > NOT_READ shows the message and the read button, and nothing reads on open | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected 'mysqlThis panel\'s view is not built …' to contain 'No MySQL read has run. Run MySQL read…'` |
| ui/tests/component/MySql.test.ts > a read renders each section with its status, reason and hint | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected undefined to be defined` |
| ui/tests/component/MySql.test.ts > changes render only when the read carries them (the second read) | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected 'mysqlThis panel\'s view is not built …' to contain 'Top normalized statements'` |
| ui/tests/component/MySql.test.ts > read-only hides the read button and says why | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected 'mysqlThis panel\'s view is not built …' to contain 'No MySQL read has run. Run MySQL read…'` |
| ui/tests/component/MySql.test.ts > renders the section rows and limitations from the POST answer without a second GET | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected undefined to be defined` |

## Leased tests left for coordinator

The following acceptance tests in `tests/fastapi/test_mysql_leased.py` require a live MySQL 8.4 instance configured via `SHARPIT_TEST_MYSQL_URL` and are left for the coordinator:
- `tests/fastapi/test_mysql_leased.py::test_read_only_wrapper_rejects_write`
- `tests/fastapi/test_mysql_leased.py::test_full_read_against_mysql_84`

## Decisions

1. MySQL panel follows the PostgreSQL collector template (`src/sharpit/engine/collectors/mysql/`: `limits.py`, `queries.py`, `querytext.py`, `sections.py`, `service.py`).
2. Read-only verification uses F5b's `run_db_read(read_only=True)`: `bounded()` is never used.
3. Every statement-text field (`digest_text`, `PROCESSLIST_INFO`, `events_statements_current.SQL_TEXT`, lock-wait query columns) is normalized, masked, and truncated at 400 chars.
4. Leased tests (`tests/fastapi/test_mysql_leased.py`) require `SHARPIT_TEST_MYSQL_URL` and skip cleanly when unset.
5. Task 5 Svelte view parity with BootUI MySql.vue, tested via Vitest component tests.

## Fix round 1 (Claude subagent, after review VERDICT: CHANGES)

Merged release/0.5.0 at d8e07a6 (no duplicated top-level defs). Head: see final commit.

| Finding | Change |
|---|---|
| #1 blocker collect_all drops sections | red 9206080, fix 4eb182c: every section appended; truncation reaches the report |
| #2 blocker leased name | never a recorded red: expectation fixed in place (4eb182c), name starts `mysql+pymysql://` |
| #3 lock-wait SQL | red 747d6b0, fix 177a916: MySQL 8.0+ `performance_schema.data_lock_waits` and MariaDB `information_schema.INNODB_LOCK_WAITS`, each joined to `INNODB_TRX`; the fake now rejects undeclared aliases and tables the server lacks |
| #4 errors as AVAILABLE | red 747d6b0, fix 177a916: lock waits/replication FAILED with masked reason; metrics failure is an ERROR diagnostic `<ds>/metrics`; MariaDB replication SKIPPED with a reason |
| #5 unmasked reasons | red 747d6b0, fix 177a916: every reason via the masker (collectors default to a strict masker) |
| #6 Task 3 pins | mutation table in findings.md; `test_mysql_get_no_side_effects` survived its mutation (no SQLAlchemy imported), so pin 8df7711 added |
| #7 checklist live check | item 9 now says not run, coordinator's lease run |
| #8 seven copies | one `_read_section` helper; per-section SQL and row mapping kept |
| minors 9-13 | info/currentStatement own columns; one title table; SOURCE_UUID selected; sessions join `NESTING_EVENT_LEVEL = 0`; SECTION_IDS and RowLimits.to_dto deleted |

Not done: ReadBudget dedup with PostgreSQL (would touch collectors/postgresql/, cross-lane). Replication now needs
`SOURCE_UUID` (MySQL 8.0.22+); older 8.0 reports that section FAILED with the reason.
Leased tests for the coordinator: `tests/fastapi/test_mysql_leased.py::test_read_only_wrapper_rejects_write`,
`::test_full_read_against_mysql_84`.

Gates at fix round 1: ruff, `ruff format --check`, pyright clean (0 errors); lane + safety matrix + test_tools +
code shape + import boundary: 1178 passed, 2 skipped (leased); vitest MySql: 5 passed. Full suite `-n 4`: 4780
passed, 13 skipped, 1 failed: `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_lazy_relationship_hook_overhead_budget`
(N+1 hook budget; this lane does not touch that code). Run alone it passes (1 passed), so it fails under parallel load.
Logs: `0.5.0-integration/.superpowers/sdd/0.5.0/logs/A-mysql-fix1-*.log`.
