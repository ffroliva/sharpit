# Definition of done checklist

| §6.1 item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane |
| 2. BootUI test citations | N/A — no BootUI behavior ported; F5 spike test is marked `# spike: F5 T1` |
| 3. Safety and masking | `tests/engine/testsession/test_gates.py`; `tests/pytest_plugin/test_plugin_gates.py` |
| 4. Gatekeeper | `src/sharpit/engine/sqla.py`; `tests/engine/test_import_boundary.py` |
| 5. Overhead budget | `tests/engine/test_n_plus_one_overhead.py`; 10-run paired measurement and final xdist noise recorded in `.superpowers/sdd/0.4.0/lanes/T-n-plus-one-message/handoff.md` |
| 6. MCP read-only | N/A — no MCP tool |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | N/A — pytest session behavior; fixture-app pytester test is the end-to-end check |
| 10. Current handoff | `.superpowers/sdd/0.4.0/lanes/T-n-plus-one-message/handoff.md` |
