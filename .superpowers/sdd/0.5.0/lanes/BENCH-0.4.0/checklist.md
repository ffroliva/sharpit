# Definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane |
| 2. BootUI port citations | N/A — no BootUI behavior ported; the tests cite bench rows U1/U2, U6, U8 |
| 3. Safety, no side effects, masking | `tests/pytest_plugin/test_plugin_bench_pins.py` (the lazy-load message adds a file:line only; the masked statement is unchanged) |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/sqla/orm.py` (SQLAlchemy read through the relationship property only); `tests/engine/test_import_boundary.py` |
| 5. Overhead budget | `tests/engine/test_n_plus_one_overhead.py` (constant unchanged, green; paired head/base numbers in findings.md) |
| 6. MCP read-only | N/A — no MCP tool or GET route |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs; lane run in `.superpowers/sdd/0.5.0/lanes/BENCH-0.4.0/handoff.md` |
| 9. Live check | N/A — test-session feature; `tests/pytest_plugin/test_plugin_swallowed_bench.py` and `tests/pytest_plugin/test_plugin_bench_pins.py` run the bench twins end to end |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/BENCH-0.4.0/handoff.md` |
