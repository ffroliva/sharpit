# D4 checklist (spec 6.1, in order)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity | `tests/engine/vulns/test_service.py`, `tests/fastapi/test_mcp_api.py`, `tests/engine/restapi/test_restapi_report.py`, `.superpowers/sdd/0.5.0/lanes/D4/field-map.md` |
| 2 | Ported tests cite their BootUI source | `tests/engine/test_tools.py`, `tests/engine/test_mcp.py`, `tests/engine/vulns/test_service.py` |
| 3 | Safety and masking | `tests/safety/test_d4_safety.py`, `tests/masking/test_d4_masking.py` |
| 4 | Gatekeeper / import boundary | `tests/engine/test_import_boundary.py` |
| 5 | Overhead budget (checked, never raised) | N/A — no capture middleware or SQL listener hot path touched; the existing budget tests ran in the full suite |
| 6 | MCP read-only | `tests/safety/test_d4_safety.py` |
| 7 | Svelte 5 view | N/A — DTO/protocol/rule drift on existing panels; no view changed |
| 8 | Four gates + lowest-direct + no-SQLAlchemy | N/A — coordinator gate logs |
| 9 | Live check | N/A — the coordinator records live-verify.md in the integration worktree |
| 10 | Handoff | `.superpowers/sdd/0.5.0/lanes/D4/handoff.md` |
