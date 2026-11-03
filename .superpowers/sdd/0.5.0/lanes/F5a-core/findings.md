# Findings: lane F5a-core

Every red ran through `scripts/dev/red_check.py` before its `test:` commit: all `RED (assertion under tests/)`.

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| assert_parity checks keys and types only; `FAILED` passes it (spec §5, R2-H8) | tests/engine/advisors/test_scan.py::test_enum_values_checked_against_golden | 4517a91801df63ea7ce87824707c92bf6addbdb1 | `assert 'results[].status' in ''` (skeleton `assert_enum_values` raised nothing) | Fixed in 3fdb8917b41fb3d2d59231d31c0514fefca9bc81 |
| rule results emit `FAILED`, no `sampleLocations` (spec §4.3, Review Focus 3) | tests/engine/advisors/test_scan.py::test_advisor_core_matches_rest_api_post_scan_golden | 4517a91801df63ea7ce87824707c92bf6addbdb1 | `assert 'FAILED' == 'VIOLATION'` | Fixed in 3fdb8917b41fb3d2d59231d31c0514fefca9bc81 |
| no shared advisor core: pre-scan shape of the four 0.5.0 advisors | tests/engine/advisors/test_scan.py::test_advisor_core_pre_scan_shape_all_four_goldens | 0470e2df9afc737f4470a2025240a377b50c45dc | `<id>/captured.json parity: localOnly: missing from payload; ...` (all four) | Fixed in 7027c61224c2035ea055705d0ba02ac6431af7a0 |
| core single flight | tests/engine/advisors/test_scan.py::test_advisor_core_single_flight | 0470e2df9afc737f4470a2025240a377b50c45dc | `assert None == 'sharpit action already in progress'` | Fixed in 7027c61224c2035ea055705d0ba02ac6431af7a0 |
| core violations paging | tests/engine/advisors/test_scan.py::test_advisor_core_violations_paged | 0470e2df9afc737f4470a2025240a377b50c45dc | `assert [] == ['v 1', 'v 2']` | Fixed in 7027c61224c2035ea055705d0ba02ac6431af7a0 |
| core unknown rule 404 | tests/engine/advisors/test_scan.py::test_advisor_core_unknown_rule_404 | 0470e2df9afc737f4470a2025240a377b50c45dc | `assert None == 404` | Fixed in 7027c61224c2035ea055705d0ba02ac6431af7a0 |
| core masks every advisor-supplied string | tests/engine/advisors/test_scan.py::test_advisor_core_masks_every_string | 0470e2df9afc737f4470a2025240a377b50c45dc | `assert [] == [['message password=******']]` | Fixed in 7027c61224c2035ea055705d0ba02ac6431af7a0 |
| 0.5.0 advisors own nothing (`owns=lambda _: False`, spec §4.4) | tests/engine/advisors/test_scan.py::test_registry_owns_by_prefix | 3da97c96f8631666e321edd1ac24909cf8ede63f | `assert None == '<advisor>'` (all five cases) | Fixed in a3f953100f3981ee794a095d00d36e6ab6f5fc3a |
| pytest plugin hard-wires rest-api `assess` (spec §4.4) | tests/engine/advisors/test_scan.py::test_pytest_plugin_discovers_advisors_from_registry | 3da97c96f8631666e321edd1ac24909cf8ede63f | `assert [] == ['rest-api', 'security']` | Fixed in a3f953100f3981ee794a095d00d36e6ab6f5fc3a |

No pins: every new test was red at its red SHA.

## Existing tests changed (they encoded the old status or DTO)

| Test | Change | Reason |
|---|---|---|
| tests/engine/advisors/test_advisor_rules.py (2 tests) | `FAILED`→`VIOLATION`, `PASSED`→`PASS`, `sampleLocations` appended to the DTO key list | N/A — test encoded the old status |
| tests/engine/advisors/test_advisor_report.py `_result`, `_report` | `FAILED`→`VIOLATION`, `PASSED`→`PASS` | N/A — test encoded the old status |
| tests/engine/advisors/test_dismissals.py:243,282 | `FAILED`→`VIOLATION`, `PASSED`→`PASS` | N/A — test encoded the old status |
| tests/engine/restapi/test_restapi_rules.py (2 tests) | `PASSED`→`PASS`, `FAILED`→`VIOLATION` | N/A — test encoded the old status |
| tests/engine/restapi/test_restapi_report.py | `FAILED`→`VIOLATION`; `RESULT_KEYS` + `sampleLocations`; the failed-build test patches `sharpit.engine.advisors.scan.build_report` (builder moved into the core; same assertion) | N/A — old status / moved symbol |
| tests/engine/restapi/test_restapi_findings.py::test_panel_dto_shape_unchanged | `sampleLocations` appended | N/A — BootUI 2.2.0 result DTO has it |

## Mutation proofs of the new rules (scratch worktree of a3f9531, removed after)

Each run: tests/engine/advisors/test_scan.py.

| Mutation | Result |
|---|---|
| M1 `RuleResult.evaluate` emits `FAILED` | 2 failed: post-scan golden, masks |
| M2 `sampleLocations` dropped from `to_dto` | 1 failed: post-scan golden |
| M3 `locationNotes` dropped from violationDetails | 5 failed: post-scan golden, pre-scan x4 |
| M4 scope lists not masked | 1 failed: masks |
| M5 limitations not masked | 1 failed: masks |
| M6 extra sections not masked | 1 failed: masks |
| M7 scan message not masked | 1 failed: masks |
| M8 findings not masked at intake | 1 failed: masks |
| M9 scan bypasses single flight | 1 failed: single flight |
| M10 prefix `owns` always False | 5 failed: owns by prefix x5 |
| M11 prefix fingerprint None | 5 failed: owns by prefix x5 |
| M12 discovery reads only the first registry row | 1 failed: discovers from registry |
| M13 `assert_enum_values` checks nothing | 1 failed: enum values |
