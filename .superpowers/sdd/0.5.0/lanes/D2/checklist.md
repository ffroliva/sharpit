# D2 checklist (spec 6.1, in order)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity | `tests/fastapi/test_http_exchanges_api.py`, `tests/fastapi/test_activity_api.py`, `tests/fastapi/test_exceptions_api.py`, `tests/fastapi/test_log_tail_api.py`, `.superpowers/sdd/0.5.0/lanes/D2/field-map.md` |
| 2 | Ported tests cite their BootUI source | `tests/engine/capture/test_http_routes.py` |
| 3 | Safety and masking | `tests/safety/test_d2_safety.py`, `tests/masking/test_d2_masking.py` |
| 4 | Gatekeeper / import boundary | `tests/engine/test_import_boundary.py` |
| 5 | Overhead budget (checked, never raised) | `tests/engine/capture/test_http_routes.py` |
| 6 | MCP read-only | `tests/safety/test_d2_safety.py` |
| 7 | Svelte 5 view | N/A — additive DTO keys and new read routes; the existing capture views keep working and no view was changed |
| 8 | Four gates + lowest-direct + no-SQLAlchemy | N/A — coordinator gate logs |
| 9 | Live check | N/A — the coordinator records live-verify.md in the integration worktree |
| 10 | Handoff | `.superpowers/sdd/0.5.0/lanes/D2/handoff.md` |
