# A-data checklist (spec §6.1)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity, nullable.json, field map | `tests/fixtures/bootui/2.2.0/data/nullable.json` and `.superpowers/sdd/0.4.0/lanes/A-data/field-map.md`; parity test skips until G0a's fixture merges |
| 2 | `# ported:` citations | `tests/fastapi/test_data_api.py` and `tests/engine/test_data.py` |
| 3 | Safety: no_side_effects, env flags, guard, masking | `tests/safety/test_a_data_safety.py` (masking of warnings covered in `tests/engine/test_data.py`) |
| 4 | Gatekeeper | `tests/engine/test_import_boundary.py` |
| 5 | Overhead budget | N/A — no hot path |
| 6 | MCP read-only | `tests/fastapi/test_data_api.py` |
| 7 | Svelte view | `ui/src/views/Data.svelte` and `ui/tests/component/data.test.ts` |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9 | Live check | `.superpowers/sdd/0.4.0/lanes/A-data/handoff.md` (section "Live check") |
| 10 | handoff current | `.superpowers/sdd/0.4.0/lanes/A-data/handoff.md` |
