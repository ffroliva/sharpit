# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_report.py` (pre-scan parity + enum values; post-scan skips `post-scan golden absent` until G0); `.superpowers/sdd/0.5.0/lanes/C-fastapi/field-map.md` (no `nullable.json` needed) |
| 2. BootUI port citations | `tests/fastapi/test_fastapi_advisor_api.py` (`# ported: SpringScannerTests.scanReportsFindingsAcrossCategories`), `tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_report.py` (`# ported: SpringScannerTests.initialReportIsNotScanned`) |
| 3. Safety, no side effects, masking | `tests/fastapi/test_fastapi_advisor_api.py` (`test_fastapi_get_no_side_effects`, `test_get_after_scan_opens_no_source_file`, `test_read_only_blocks_scan`, `test_inactive_fastapi_paths_404`, `test_scan_reads_only_app_package`); `tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_app.py` (`test_violation_never_contains_literal_secret`); `tests/safety/test_c_fastapi_safety.py` |
| 4. Optional dependency gatekeeper | N/A — no optional or network library imported (stdlib `ast`/`inspect` only) |
| 5. Overhead budget | N/A — no hot-path code (the scan runs on an explicit POST/CLI call only) |
| 6. MCP read-only | `tests/fastapi/test_fastapi_advisor_api.py` (`test_mcp_tools_list_has_only_get`); `src/sharpit/engine/tools04/fastapi.py` (`fastapi_scan` action, CLI-only) |
| 7. Svelte view | `ui/src/views/Fastapi.svelte`, `ui/tests/component/Fastapi.test.ts` (`npm run check`, vitest 285 passed, `npm run build` committed) |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/C-fastapi/handoff.md` (§Live check: in-process on `examples/fastapi_sqla`) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/C-fastapi/handoff.md` |
