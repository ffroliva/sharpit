# Definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/engine/collectors/architecture/test_architecture_report.py` (`test_report_golden_parity`); `tests/fixtures/bootui/2.2.0/architecture/nullable.json`; `.superpowers/sdd/0.5.0/lanes/C-architecture/field-map.md` |
| 2. BootUI port citations | `tests/engine/collectors/architecture/test_architecture_report.py` (`# ported: ArchitectureScannerTests.*`) |
| 3. Safety, no side effects, masking | `tests/safety/test_c_architecture_safety.py` |
| 4. Optional dependency gatekeeper | N/A — no external library imported (uses stdlib ast and tomllib) |
| 5. Overhead budget | N/A — on-demand scan action, no hot-path request middleware |
| 6. MCP read-only | `tests/fastapi/test_architecture_api.py` (`test_mcp_tools_list_has_only_get`) |
| 7. Svelte view | `ui/src/views/Architecture.svelte`; `ui/tests/component/Architecture.test.ts` |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/C-architecture/handoff.md` (§Live check) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/C-architecture/handoff.md` |
