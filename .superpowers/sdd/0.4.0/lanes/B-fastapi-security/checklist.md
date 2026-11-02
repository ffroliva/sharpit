# Lane B-fastapi-security checklist (spec §6.1)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity | `tests/fastapi/test_fastapi_security_api.py` (`test_report_golden_parity`, `test_endpoints_golden_parity`), `tests/fixtures/bootui/2.2.0/fastapi-security/nullable.json`, `.superpowers/sdd/0.4.0/lanes/B-fastapi-security/field-map.md` |
| 2 | `# ported:` citations | `tests/engine/test_appsecurity.py`, `tests/fastapi/test_introspector_security.py`, `tests/fastapi/test_fastapi_security_api.py` |
| 3 | Safety and masking | `tests/safety/test_b_fastapi_security_safety.py`, `tests/masking/test_b_fastapi_security_masking.py` |
| 4 | Gatekeeper | N/A — fastapi is imported only in `sharpit/fastapi/`; `tests/engine/test_import_boundary.py` green |
| 5 | Overhead budget | N/A — no hot path (GET-time reads only) |
| 6 | MCP read tools only | `tests/fastapi/test_fastapi_security_api.py` (`test_mcp_read_tool_only`) |
| 7 | Svelte view | `ui/src/views/FastapiSecurity.svelte`, `ui/tests/component/fastapiSecurity.test.ts` |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs (implementer results in `.superpowers/sdd/0.4.0/lanes/B-fastapi-security/handoff.md`) |
| 9 | Live check | `.superpowers/sdd/0.4.0/lanes/B-fastapi-security/handoff.md` (section Live check) |
| 10 | Handoff current | `.superpowers/sdd/0.4.0/lanes/B-fastapi-security/handoff.md` |
