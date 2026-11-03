# Definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane |
| 2. BootUI port citations | N/A — no BootUI behavior ported; the tests cite bench findings F3, F4, F5 |
| 3. Safety, no side effects, masking | `tests/engine/testsession/test_gates.py` (the message reuses the masked `sql_of` statement; the site is a file:line, the fix names a class and attribute only) |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/sqla.py` (SQLAlchemy read through the execution context only); `tests/engine/test_import_boundary.py` |
| 5. Overhead budget | `tests/engine/test_n_plus_one_overhead.py` (constant unchanged, green); `tests/engine/test_sqla.py` (one stack walk per relationship, unchanged, green) |
| 6. MCP read-only | N/A — no MCP tool |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs; lane run in `.superpowers/sdd/0.5.0/lanes/P-0.4.1/handoff.md`; code-scan ratchet N/A — no token |
| 9. Live check | N/A — test-session feature; `tests/pytest_plugin/test_plugin_bench_pins.py` runs the bench twins end to end |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/P-0.4.1/handoff.md` |
