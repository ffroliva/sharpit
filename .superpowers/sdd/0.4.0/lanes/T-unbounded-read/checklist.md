# Definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane; `.superpowers/sdd/0.4.0/lanes/T-unbounded-read/field-map.md` |
| 2. BootUI port citations | N/A — no BootUI behavior ported; the spike tests cite F2 |
| 3. Safety, no side effects, masking | `tests/engine/test_sqla.py::test_unbounded_read_fact_drops_sql_values`; `tests/pytest_plugin/test_plugin_unbounded_read.py::test_without_install_reports_limitation_and_does_not_fire` |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/sqla.py`; `tests/engine/test_import_boundary.py` |
| 5. Overhead budget | `tests/fastapi/test_capture_overhead.py` (unchanged); test-session listener lifecycle in `tests/engine/test_sqla.py::test_mapper_load_listener_attaches_once_and_detaches` |
| 6. MCP read-only | N/A — no MCP tool |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | N/A — test-session feature; `tests/pytest_plugin/test_plugin_unbounded_read.py` runs the pytester end-to-end case |
| 10. Current handoff | `.superpowers/sdd/0.4.0/lanes/T-unbounded-read/handoff.md` |
