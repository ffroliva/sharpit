# Definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/fastapi/test_mysql_api.py` (`test_report_golden_parity`); `tests/fixtures/bootui/2.2.0/mysql/nullable.json`; `.superpowers/sdd/0.5.0/lanes/A-mysql/field-map.md` |
| 2. BootUI port citations | `tests/engine/collectors/mysql/test_sections.py` (`# ported: MySqlValuesTests.*`, `MySqlRowLimitsTests.*`, `MySqlMariaDbTests.*`, `MySqlComparisonTests.*`) |
| 3. Safety, no side effects, masking | `tests/safety/test_a_mysql_safety.py`; `tests/masking/test_a_mysql_masking.py` |
| 4. Optional dependency gatekeeper | N/A — SQLAlchemy gatekeeper `sharpit.engine.sqla` (untouched); pymysql in test extra |
| 5. Overhead budget | N/A — no hot path: computed on explicit POST / GET, bounded by timeouts |
| 6. MCP read-only | `tests/fastapi/test_mysql_api.py` (`test_mcp_tools_list_has_only_get`) |
| 7. Svelte view | `ui/src/views/MySql.svelte`; `ui/tests/component/MySql.test.ts` |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs; lane run in `.superpowers/sdd/0.5.0/lanes/A-mysql/handoff.md` |
| 9. Live check | NOT RUN by the lane (no MySQL server here). The coordinator runs `tests/fastapi/test_mysql_leased.py` (both tests) on the leased MySQL 8.4; until then this item is open. Non-leased full-read coverage: `tests/fastapi/test_mysql_report_read.py` |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/A-mysql/handoff.md` |
