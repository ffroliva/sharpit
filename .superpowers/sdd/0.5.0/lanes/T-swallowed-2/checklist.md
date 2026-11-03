# T-swallowed-2 checklist (0.4.0 spec §6.1)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity, nullable.json, field map | N/A — not a panel lane: no BootUI DTO (`.superpowers/sdd/0.5.0/lanes/T-swallowed-2/field-map.md`) |
| 2 | `# ported:` citations | N/A — no BootUI test ported; the twins come from the sharpit benchmark cases |
| 3 | Safety: no_side_effects, env flags, guard, masking | N/A — no route, panel or output field added; the rule keeps no source text, local or message |
| 4 | Gatekeeper | `tests/engine/test_import_boundary.py` (passes; only stdlib `ast` used) |
| 5 | Overhead budget | N/A — the AST rule is cached per code object and offset (`tests/engine/testsession/test_swallowed.py::test_ast_cache_is_per_code_object`); the sys.monitoring hook is untouched |
| 6 | MCP read-only | N/A — no MCP tool added |
| 7 | Svelte view | N/A — no UI |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9 | Live check | N/A — pytest-plugin rule, exercised end to end by `tests/pytest_plugin/test_plugin_swallowed_bench.py` (`pytest --sharpit` in a pytester subprocess) |
| 10 | handoff current | `.superpowers/sdd/0.5.0/lanes/T-swallowed-2/handoff.md` |
