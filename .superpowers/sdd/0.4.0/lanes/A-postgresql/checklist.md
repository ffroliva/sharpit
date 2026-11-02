# Lane A-postgresql spec §6.1 checklist

| # | Spec §6.1 item | Evidence path / status |
|---|---|---|
| 1 | Golden parity | Pending Task 5 (`tests/fixtures/bootui/2.2.0/postgresql/nullable.json`, `tests/fastapi/test_postgresql_api.py::test_report_dto_parity`) |
| 2 | Ported behavior tests | Pending Tasks 1–5 (`tests/engine/test_sqla_read_only.py`, `tests/engine/postgresql/test_*.py`, `tests/fastapi/test_postgresql_api.py`) |
| 3 | Safety and masking | Pending Task 5 (`tests/safety/test_a_postgresql_safety.py`, `tests/masking/test_a_postgresql_masking.py`) |
| 4 | Gatekeeper | `src/sharpit/engine/sqla.py` is the only SQLAlchemy gatekeeper; `psycopg` is imported nowhere in `src/sharpit/` (`tests/engine/test_import_boundary.py`) |
| 5 | Hot-path overhead | N/A — `postgresql` is an on-demand action panel (`POST /sharpit/api/postgresql/read`); it installs no request middleware or SQL statement listener |
| 6 | MCP read-only surface | Pending Task 5 (`src/sharpit/engine/tools04/postgresql.py`: `get_postgresql_report` on MCP, `postgresql_read` CLI-only `action=True`) |
| 7 | Svelte view | Pending Task 6 (`ui/src/views/PostgreSql.svelte`, `ui/tests/component/PostgreSql.test.ts`) |
| 8 | Four gates | Pending Task 7 (`ruff check`, `ruff format --check`, `pyright`, `pytest -q -n 4`) |
| 9 | Live check | N/A in lane worktree — coordinator runs `leased-pg.log` and live verification in integration (`F-foundation.md` Task 4) |
| 10 | Handoff | `.superpowers/sdd/0.4.0/lanes/A-postgresql/handoff.md` |
