# Definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane; [field-map.md](field-map.md) |
| 2. BootUI port citations | N/A — no BootUI behavior ported; spike test cites F2 |
| 3. Safety, no side effects, masking | `tests/pytest_plugin/test_plugin_unbounded_read.py` (nested app request succeeds; finding integration remains unresolved) |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/sqla.py`; `tests/engine/test_import_boundary.py` passed |
| 5. Overhead budget | `tests/fastapi/test_capture_overhead.py` unchanged; load listener is test-session-only |
| 6. MCP read-only | N/A — no MCP tool |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | N/A — pytest test-session feature; pytester spike is end-to-end |
| 10. Current handoff | `.superpowers/sdd/0.4.0/lanes/T-unbounded-read/handoff.md` |
