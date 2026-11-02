# Definition of done checklist (spec §6.1)

| §6.1 item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane |
| 2. BootUI test citations | N/A — no BootUI behaviour ported; the spike test is marked `# spike: F1 T4` |
| 3. Safety and masking | `src/sharpit/engine/testsession/facts.py` (SwallowedFact keeps handler location and type only, never message or locals); `tests/engine/testsession/test_gates.py`; `tests/pytest_plugin/test_plugin_swallowed.py` |
| 4. Gatekeeper | `src/sharpit/engine/testsession/swallowed.py` (stdlib `ast`/`dis`/`linecache` only); `tests/engine/test_import_boundary.py` |
| 5. Overhead budget | `tests/engine/test_swallowed_overhead.py`; 10-run measurement (0.40-0.86 us/exception, noise <= 0.40) and mutation proof in `.superpowers/sdd/0.4.0/lanes/T-swallowed-exceptions/handoff.md` |
| 6. MCP read-only | N/A — no MCP tool |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | N/A — test-session feature; the pytester spike test is the end-to-end check |
| 10. Current handoff | `.superpowers/sdd/0.4.0/lanes/T-swallowed-exceptions/handoff.md` |
