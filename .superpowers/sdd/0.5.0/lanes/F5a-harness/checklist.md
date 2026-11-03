# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane; `.superpowers/sdd/0.5.0/lanes/F5a-harness/field-map.md` |
| 2. BootUI port citations | N/A — safety harness and settings; no BootUI behaviour ported (MySQL setting names cite WAVE-A §6 in `tests/test_settings_05.py`) |
| 3. Safety, no side effects, masking | `tests/test_side_effect_guard.py`, `tests/engine/test_import_boundary.py`, `tests/test_surface_05.py` |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/models.py` imports no SQLAlchemy; `tests/engine/test_import_boundary.py` |
| 5. Overhead budget | N/A — no hot-path code; the open spy is installed only by `watch_sources` (test-only: the shared GET and MCP sweeps and the guard's own tests) |
| 6. MCP read-only | `tests/test_safety_matrix.py` (`test_cli_action_tools_gated` with `postgresql_read`) |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | N/A — no new route or panel surface |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/F5a-harness/handoff.md` |
