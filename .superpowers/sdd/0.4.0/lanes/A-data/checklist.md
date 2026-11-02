# A-data checklist (spec §6.1)

1. Golden parity, nullable.json, field map: `tests/fixtures/bootui/2.2.0/data/nullable.json`; `test_repositories_golden_parity` (skips until G0a's captured fixture merges); `field-map.md`.
2. `# ported:` citations: `tests/engine/test_data.py`, `tests/fastapi/test_data_api.py`.
3. Safety: `test_get_never_configures_mappers` (no_side_effects), `tests/safety/test_a_data_safety.py` (cross-site 403, inactive 404), `test_panel_disabled_403`; masking N/A (class and table names only).
4. Gatekeeper: the collector imports no SQLAlchemy; `tests/engine/test_import_boundary.py` green.
5. Overhead budget: N/A, no hot path.
6. MCP read-only: `test_mcp_lists_read_tool_only`.
7. Svelte view: `ui/src/views/Data.svelte`, `ui/tests/component/data.test.ts` (vitest 262 pass, tsc clean).
8. Four gates: `handoff.md` section "Gates". lowest-direct and no-SQLAlchemy: coordinator (not run here).
9. Live check: `handoff.md` section "Live check".
10. `handoff.md` current.
