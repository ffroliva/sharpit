# Definition of done checklist (spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/engine/collectors/security/test_contract.py` (`test_report_golden_parity`; `test_post_scan_golden_parity` skips until G0), `.superpowers/sdd/0.5.0/lanes/B-security/field-map.md` (no `nullable.json`: every key is filled) |
| 2. BootUI port citations | `tests/engine/collectors/security/test_rules_auth.py` (`# ported: SecurityRulesTests.*`), `docs/security-advisor-checks.md` |
| 3. Safety, no side effects, masking | `tests/safety/test_b_security_safety.py`, `tests/masking/test_b_security_masking.py`, `tests/fastapi/trap_surfaces_security.py`, `tests/fastapi/test_security_api.py` |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/collectors/security/__init__.py` (stdlib + engine only; `tests/engine/test_import_boundary.py`) |
| 5. Overhead budget | N/A — no hot-path code; rules run on POST scan only, GET renders the cached dict |
| 6. MCP read-only | `tests/fastapi/test_security_api.py` (`test_mcp_tools_list_has_only_get`; `security_scan` CLI-only) |
| 7. Svelte view | `ui/src/views/Security.svelte`, `ui/tests/component/security.test.ts` |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/B-security/handoff.md` (§Live check, in-process) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/B-security/handoff.md` |
