# Lane A-postgresql spec §6.1 checklist

| # | Spec §6.1 item | Evidence path / status |
|---|---|---|
| 1 | Golden parity | `tests/fastapi/test_postgresql_api.py::test_golden_parity` (skips until G0a's `tests/fixtures/bootui/2.2.0/postgresql/captured.json` exists — "Needs from coordinator"); nullable paths `tests/fixtures/bootui/2.2.0/postgresql/nullable.json`; key order pinned by `tests/engine/postgresql/test_service.py::test_report_keys_match_the_bootui_records`; field map `field-map.md` |
| 2 | Ported behavior tests | `# ported:` citations in `tests/engine/test_sqla_read_only.py`, `tests/engine/postgresql/test_querytext.py`, `test_limits.py`, `test_sections.py`, `test_service.py`, `tests/fastapi/test_postgresql_api.py` |
| 3 | Safety and masking | `tests/safety/test_a_postgresql_safety.py` (POST-only read, read-only pin first, rollback, savepoint per query, refused pin runs no catalog SQL); `tests/masking/test_a_postgresql_masking.py` (`pg_stat_activity.query` STRIPE key, `pg_stat_statements.query` password, DSN password in driver and connection errors); `tests/fastapi/test_postgresql_api.py::test_get_no_side_effects`, `::test_read_only_403` |
| 4 | Gatekeeper | SQL only through `sqla.run_db_read(read_only=True)` → `bounded_read_only`; `collectors/postgresql/` imports neither SQLAlchemy nor psycopg (`exec_driver_sql`/`begin_nested` duck-typed); `tests/engine/test_import_boundary.py` green |
| 5 | Hot-path overhead | N/A — on-demand action panel (`POST /sharpit/api/postgresql/read`), no middleware or statement listener of its own. Flipping the flag enables F's engine-discovery listener (`sqla.DISCOVERY_PANELS`); see handoff for the `test_request_overhead_budget` base comparison |
| 6 | MCP read-only surface | `src/sharpit/engine/tools04/postgresql.py`: `get_postgresql_report` (MCP read), `postgresql_read` (`action=True`, CLI-only); `tests/fastapi/test_postgresql_api.py::test_mcp_read_tool_only`, `::test_cli_read_returns_a_summary_without_rows` |
| 7 | Svelte view | `ui/src/views/PostgreSql.svelte`, `ui/tests/component/postgresql.test.ts` (4 tests); `npm --prefix ui run check` clean; static build left to the coordinator |
| 8 | Four gates | handoff.md §Gates (ruff check, ruff format --check, pyright, pytest -n 4) |
| 9 | Live check | Unverified in the lane: no database was leased or connected. Leased tests (`SHARPIT_TEST_POSTGRES_URL`): `tests/engine/test_sqla_read_only.py::test_read_only_wrapper_rejects_write`, `::test_autocommit_engine_is_unavailable`, `::test_async_engine_read_only`, `tests/engine/postgresql/test_sections.py::test_sections_on_real_server` — coordinator writes `gate/leased-pg.log` |
| 10 | Handoff | `.superpowers/sdd/0.4.0/lanes/A-postgresql/handoff.md` |
