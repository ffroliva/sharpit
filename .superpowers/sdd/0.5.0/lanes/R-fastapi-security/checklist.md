# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/fastapi/test_fastapi_security_api.py` (`test_report_golden_parity`, `test_endpoints_golden_parity`), `tests/fixtures/bootui/2.2.0/fastapi-security/nullable.json`, `.superpowers/sdd/0.5.0/lanes/R-fastapi-security/field-map.md` |
| 2. BootUI port citations | `tests/fastapi/test_fastapi_security_api.py` (`# ported: SpringSecurityControllerTests.*`) |
| 3. Safety, no side effects, masking | `tests/safety/test_b_fastapi_security_safety.py`, `tests/masking/test_b_fastapi_security_masking.py`, `tests/fastapi/test_introspection_trap.py` |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/collectors/appsecurity.py` (stdlib + engine DTOs only; `tests/engine/test_import_boundary.py`) |
| 5. Overhead budget | N/A — no hot-path code; introspection runs per GET only |
| 6. MCP read-only | `tests/fastapi/test_fastapi_security_api.py` (`test_mcp_read_tool_only`) |
| 7. Svelte view | `ui/src/views/FastapiSecurity.svelte`, `ui/tests/component/fastapiSecurity.test.ts` |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/R-fastapi-security/handoff.md` (§Live check, in-process) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/R-fastapi-security/handoff.md` |
