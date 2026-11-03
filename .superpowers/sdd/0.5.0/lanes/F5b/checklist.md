# Definition of done checklist (spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane; `.superpowers/sdd/0.5.0/lanes/F5b/field-map.md` |
| 2. BootUI port citations | N/A — no BootUI behaviour ported (MySQL/SQLite read-only path is sharpit's own, spec §5.0) |
| 3. Safety, no side effects, masking | `tests/engine/test_sqla_read_only_dialects.py` (fail-closed read-only, session restored, invalidated on a failed restore); `tests/test_patch_targets.py` |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/sqla/__init__.py`; `tests/engine/test_import_boundary.py` (`sqla/` package key, planted import outside it fails) |
| 5. Overhead budget | `tests/engine/test_n_plus_one_overhead.py` (constants unchanged; base and head fail alike under machine load, paired runs in `handoff.md`) |
| 6. MCP read-only | N/A — no MCP tool added |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs; lane run in `.superpowers/sdd/0.5.0/lanes/F5b/handoff.md` |
| 9. Live check | N/A — no route or panel; the MySQL acceptance tests are leased: `tests/fastapi/test_mysql_read_only_leased.py` |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/F5b/handoff.md` |
