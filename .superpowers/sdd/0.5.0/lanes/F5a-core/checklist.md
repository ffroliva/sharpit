# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/engine/advisors/test_scan.py` (rest-api post-scan parity + enum values; pre-scan parity for security, architecture, fastapi, database-advisor); `tests/golden.py` (`assert_enum_values`); `tests/fixtures/bootui/2.2.0/rest-api/enums.json`; field map N/A — not a panel lane: `.superpowers/sdd/0.5.0/lanes/F5a-core/field-map.md` |
| 2. BootUI port citations | `tests/engine/advisors/test_scan.py` (`# ported: ArchitectureScannerTests.duplicateScanFailsFastAndLaterRetryRuns`) |
| 3. Safety, no side effects, masking | `tests/engine/advisors/test_scan.py` (`test_advisor_core_masks_every_string`); no new route or MCP tool |
| 4. Optional dependency gatekeeper | N/A — no optional or network library imported |
| 5. Overhead budget | N/A — no hot-path code (scan core runs on an explicit POST only) |
| 6. MCP read-only | N/A — no new MCP tool; rest-api tools unchanged (`tests/fastapi/test_rest_api_api.py` green) |
| 7. Svelte view | N/A — no UI change (the UI never reads the rule `status` value) |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | N/A — no new route or panel surface |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/F5a-core/handoff.md` |
