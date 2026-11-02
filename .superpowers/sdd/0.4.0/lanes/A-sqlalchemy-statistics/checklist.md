# Lane A-sqlalchemy-statistics checklist (spec §6.1)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity | N/A — no golden exists (tiny-ledger has no Hibernate statistics and G0a supplied neither `captured.json` nor `provisional.json`); `nullable.json` and the field map are in `tests/fixtures/bootui/2.2.0/sqlalchemy-statistics/nullable.json` and `.superpowers/sdd/0.4.0/lanes/A-sqlalchemy-statistics/field-map.md` |
| 2 | `# ported:` citations | `tests/engine/test_sqlastats.py`, `tests/fastapi/test_sqlalchemy_statistics_api.py` |
| 3 | Safety and masking | `tests/safety/test_a_sqlalchemy_statistics_safety.py`, `tests/masking/test_a_sqlalchemy_statistics_masking.py` |
| 4 | Gatekeeper | `tests/engine/test_import_boundary.py` (green; the new modules import no SQLAlchemy) |
| 5 | Overhead budget | `tests/fastapi/test_sql_trace_overhead.py` unchanged and green after the totals addition: `206 passed` for `tests/engine/capture tests/fastapi/test_sql_trace_overhead.py` |
| 6 | MCP read tools only | `tests/fastapi/test_sqlalchemy_statistics_api.py` (`test_mcp_read_tool_only`) |
| 7 | Svelte view | `ui/tests/component/sqlalchemyStatistics.test.ts`, `ui/src/views/SqlalchemyStatistics.svelte` |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs (the implementer's own results are in `.superpowers/sdd/0.4.0/lanes/A-sqlalchemy-statistics/handoff.md`) |
| 9 | Live check | `.superpowers/sdd/0.4.0/lanes/A-sqlalchemy-statistics/handoff.md` (section Live check) |
| 10 | Handoff current | `.superpowers/sdd/0.4.0/lanes/A-sqlalchemy-statistics/handoff.md` |
