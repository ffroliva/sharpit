# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/fastapi/test_database_advisor_api.py` (`test_report_golden_parity`; `test_post_scan_golden_parity` skips until G0), `tests/fixtures/bootui/2.2.0/database-advisor/nullable.json`, `.superpowers/sdd/0.5.0/lanes/A-dbadv-1/field-map.md` |
| 2. BootUI port citations | `tests/engine/collectors/database_advisor/test_rules_schema.py` (`# ported: DatabaseAdvisorSchemaRulesTests.*`), `tests/engine/collectors/database_advisor/test_rules_driver_pool.py` (`# ported: DatabaseAdvisorPoolRulesTests.*`) |
| 3. Safety, no side effects, masking | `tests/safety/test_a_database_advisor_safety.py`, `tests/masking/test_a_database_advisor_masking.py`, `tests/fastapi/test_database_advisor_api.py` (`test_dbadv_read_uses_verified_read_only_path`, `test_autocommit_engine_is_unavailable`, `test_query_string_secret_never_read_or_emitted`) |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/sqla/inspect.py` (the only SQLAlchemy use; `tests/engine/test_import_boundary.py`) |
| 5. Overhead budget | N/A — no hot-path code: the scan runs only on POST |
| 6. MCP read-only | `tests/fastapi/test_database_advisor_api.py` (`test_mcp_tools_list_has_only_get`, `test_cli_scan_and_commands`) |
| 7. Svelte view | `ui/src/views/DatabaseAdvisor.svelte`, `ui/tests/component/DatabaseAdvisor.test.ts` |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/A-dbadv-1/handoff.md` (§Live check, in-process) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/A-dbadv-1/handoff.md` |
