# D4 findings

Implementer: Claude Code subagent (claude-opus-5-5)

Every red below was checked with `scripts/dev/red_check.py` before its `test:` commit: all `RED (assertion under tests/)`.

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/test_tools.py::test_mcp_vulnerabilities_compacts_dependencies_and_advisories | 130bda0a9e313d0c77af27728af93a36a9896048 | default limit 10, vulnerable dependencies only | Fixed in f3975137ca95859ce472f24a8df2fba47bae1191 |
| tests/engine/test_tools.py::test_mcp_vulnerabilities_query_includes_clean_dependencies | 130bda0a9e313d0c77af27728af93a36a9896048 | `[] == ['clean-1']` (query refused as an unexpected argument) | Fixed in f3975137ca95859ce472f24a8df2fba47bae1191 |
| tests/engine/test_tools.py::test_get_threads_default_limit_is_25 | 130bda0a9e313d0c77af27728af93a36a9896048 | absent limit: 25, capped by the via's max results; an explicit limit is kept | Fixed in f3975137ca95859ce472f24a8df2fba47bae1191 |
| tests/engine/vulns/test_service.py::test_vulnerabilities_new_keys_present | 130bda0a9e313d0c77af27728af93a36a9896048 | `None == {'available': False, ...}` (no `runtimeReach`) | Fixed in f3975137ca95859ce472f24a8df2fba47bae1191 |
| tests/engine/vulns/test_service.py::test_vulnerabilities_golden_parity_after_drift | 130bda0a9e313d0c77af27728af93a36a9896048 | vulnerabilities/captured.json parity: missing keys (`runtimeReach`, coverage first-party keys) | Fixed in f3975137ca95859ce472f24a8df2fba47bae1191 |
| tests/masking/test_d4_masking.py::test_mcp_compaction_masks | 130bda0a9e313d0c77af27728af93a36a9896048 | `'hunter2sharpitd4' not in ...` | Fixed in f3975137ca95859ce472f24a8df2fba47bae1191 |
| tests/safety/test_d4_safety.py::test_d4_drift_reads_have_no_side_effects | 130bda0a9e313d0c77af27728af93a36a9896048 | query and limit are accepted on get_vulnerabilities_report | Fixed in f3975137ca95859ce472f24a8df2fba47bae1191 |
| tests/engine/test_mcp.py::test_mcp_negotiates_2026_07_28_and_tracks_cancellations_and_progress_dropped | 2068bf7d4f30c987d08b27300776958cee7cc53e | a supported revision is echoed | Fixed in 9fe30d510d0d2b13651845003fbe54e02fa27879 |
| tests/engine/test_mcp.py::test_mcp_progress_token_in_meta_is_accepted | 2068bf7d4f30c987d08b27300776958cee7cc53e | `None == 0` (no `progressDropped`) | Fixed in 9fe30d510d0d2b13651845003fbe54e02fa27879 |
| tests/fastapi/test_mcp_api.py::test_mcp_server_golden_parity_after_drift | 2068bf7d4f30c987d08b27300776958cee7cc53e | mcp-server/captured.json parity: missing `supportedProtocolVersions`, `cancellations`, `progressDropped` | Fixed in 9fe30d510d0d2b13651845003fbe54e02fa27879 |
| tests/engine/restapi/test_restapi_rules.py::test_rest_api_new_rules_fire[RAPI-RESP-010] | 7fcebfe31cc76d912cd88ea1d866e4b103597bed | RAPI-RESP-010 is registered as skipped with a reason | Fixed in 2eb2b6ac81ccedf78d5204ba9d9710c9cbd8d40e |
| tests/engine/restapi/test_restapi_rules.py::test_rest_api_new_rules_fire[RAPI-RESP-011] | 7fcebfe31cc76d912cd88ea1d866e4b103597bed | `[] == ['app.pets:read_pet [GET /v1/pets/{id}] — Optional return ...']` | Fixed in 2eb2b6ac81ccedf78d5204ba9d9710c9cbd8d40e |
| tests/engine/restapi/test_restapi_rules.py::test_rest_api_new_rules_fire[RAPI-VALID-006] | 7fcebfe31cc76d912cd88ea1d866e4b103597bed | RAPI-VALID-006 is registered as skipped with a reason | Fixed in 2eb2b6ac81ccedf78d5204ba9d9710c9cbd8d40e |
| tests/engine/restapi/test_restapi_rules.py::test_rest_api_new_rules_fire[RAPI-VER-007] | 7fcebfe31cc76d912cd88ea1d866e4b103597bed | RAPI-VER-007 is registered as skipped with a reason | Fixed in 2eb2b6ac81ccedf78d5204ba9d9710c9cbd8d40e |
| tests/engine/restapi/test_restapi_registry.py::test_registry_lists_bootui_2_2_0_rules | 7fcebfe31cc76d912cd88ea1d866e4b103597bed | `[] == ['RAPI-RESP-010', ...]` (ids not in the fixture) | Fixed in 2eb2b6ac81ccedf78d5204ba9d9710c9cbd8d40e |
| tests/engine/restapi/test_restapi_report.py::test_rest_api_golden_parity_after_drift | 7fcebfe31cc76d912cd88ea1d866e4b103597bed | `None == 'VIOLATION'` (no RAPI-RESP-011 result) | Fixed in 2eb2b6ac81ccedf78d5204ba9d9710c9cbd8d40e |

## Pins (passed before the fix; mutation-proven)

| Test | Historical SHA | Mutation proof |
|---|---|---|
| tests/engine/vulns/test_service.py::test_osv_down_releases_lock | 130bda0a9e313d0c77af27728af93a36a9896048 | `except OsvError` -> `except LookupError` in `vulns/service.py::_scan`: fails, `OsvError: ... failed (URLError)` escapes `scan()` |
| tests/engine/vulns/test_service.py::test_epss_down_keeps_osv_and_releases_lock | 130bda0a9e313d0c77af27728af93a36a9896048 | `except (OsvError, _EpssError)` -> `except _EpssError` in `vulns/epss.py`: fails, `OsvError: EPSS query failed (URLError)` escapes `scan()` |

## Existing tests updated for the 2.2.0 drift (pins extended, none weakened)

| Test | Change |
|---|---|
| tests/engine/vulns/test_interpreter.py::test_recorded_advisory_with_a_fix | DTO + `advisorySymbols`, `advisorySymbolSource`, `runtimeReach` |
| tests/engine/vulns/test_service.py shape tests | `VULN_KEYS` + 3 keys; `ADDED_2_2_0` keys over the 1.x golden (report/dependency `runtimeReach`, coverage first-party keys) |
| tests/engine/test_tools.py::test_catalogue_names_panels_actions_and_schemas, `SCHEMAS_2_2_0` | `get_vulnerabilities_report` NONE -> QUERY_LIMIT (contract drift §7) |
| tests/fastapi/test_mcp_api.py::test_mcp_server_status_shape | 2.2.0 key order with the three new keys |
| tests/engine/restapi/test_restapi_registry.py | 60 documented ids, `PORTED` + RESP-011, severity LOW |
| tests/engine/restapi/test_restapi_findings.py `CASES`, `FROZEN_TEXT`, `FROZEN_FINGERPRINTS` | + RAPI-RESP-011 rows (outside the plan's test list: required by `test_cases_cover_every_rule`; fingerprint computed independently with hashlib), d236fd8ce700a9dd395bd5447bc3b1c6a559fac6 |
| tests/test_conformance.py `NEWER_THAN_GOLDEN` | + vulnerabilities 2.2.0 keys over the 1.17.0 golden (outside May-touch; required by `test_shape_matches_golden[vulnerabilities]`), d236fd8ce700a9dd395bd5447bc3b1c6a559fac6 |
| tests/engine/restapi/test_restapi_report.py::test_shape_keys_match_bootui | `rulesEvaluated` 20 -> 21 |
