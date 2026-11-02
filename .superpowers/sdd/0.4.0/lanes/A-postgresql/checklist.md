# Lane A-postgresql spec §6.1 checklist

| # | Spec §6.1 item | Evidence |
|---|---|---|
| 1 | Golden parity | `tests/fastapi/test_postgresql_api.py` (`test_golden_parity`, skips until G0a's captured fixture), `tests/fixtures/bootui/2.2.0/postgresql/nullable.json`, `tests/engine/postgresql/test_service.py` (`test_report_keys_match_the_bootui_records`) |
| 2 | Ported behavior tests | `tests/engine/postgresql/test_sections.py` (and `test_sqla_read_only.py`, `test_querytext.py`, `test_limits.py`, `test_service.py`, all citing `# ported:`) |
| 3 | Safety and masking | `tests/safety/test_a_postgresql_safety.py`, `tests/masking/test_a_postgresql_masking.py` |
| 4 | Gatekeeper | `tests/engine/test_import_boundary.py` (SQL only through `src/sharpit/engine/sqla.py`; no driver import in `src/sharpit/engine/collectors/postgresql/`) |
| 5 | Hot-path overhead | N/A — on-demand POST action panel with no middleware or statement listener of its own |
| 6 | MCP read-only surface | `src/sharpit/engine/tools04/postgresql.py` (tests: `tests/fastapi/test_postgresql_api.py`) |
| 7 | Svelte view | `ui/src/views/PostgreSql.svelte`, `ui/tests/component/postgresql.test.ts` |
| 8 | Four gates | N/A — coordinator gate logs |
| 9 | Live check | N/A — coordinator leased run (`gate/leased-pg.log` in the integration worktree) |
| 10 | Handoff | `.superpowers/sdd/0.4.0/lanes/A-postgresql/handoff.md` |
