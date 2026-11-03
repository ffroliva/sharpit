# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — no new DTO key or route; the panel's parity tests are A-dbadv-1's and still pass (`tests/fastapi/test_database_advisor_api.py`); field map `.superpowers/sdd/0.5.0/lanes/A-dbadv-2/field-map.md` |
| 2. BootUI port citations | `tests/engine/collectors/database_advisor/test_rules_orm.py`, `tests/engine/collectors/database_advisor/test_rules_runtime.py` (`# ported:` lines; rule texts follow BootUI 2.2.0 `docs/DATABASE-ADVISOR-CHECKS.md`) |
| 3. Safety, no side effects, masking | `tests/engine/collectors/database_advisor/test_rules_orm.py` (`test_scan_never_configures_mappers`, `test_scan_leaves_a_configurable_registry_unconfigured`), `tests/engine/collectors/database_advisor/test_rules_runtime.py` (`test_runtime_001_never_emits_sql_text_or_literals`) |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/collectors/database_advisor/rules_orm.py` (no SQLAlchemy import; mappers only via `engine/models.py`), `src/sharpit/engine/collectors/database_advisor/rules_vendor.py` (duck-typed `conn`; `tests/engine/test_import_boundary.py`) |
| 5. Overhead budget | N/A — no hot-path code: the rules run only inside a POST scan |
| 6. MCP read-only | N/A — no tool added; A-dbadv-1's `test_mcp_tools_list_has_only_get` still passes |
| 7. Svelte view | N/A — no view change (rules only; Must-NOT-touch the view) |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/A-dbadv-2/wiring.patch` (its in-process e2e test drives `POST /sharpit/api/database-advisor/scan` with `models=`; see handoff §Wiring) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/A-dbadv-2/handoff.md` |
