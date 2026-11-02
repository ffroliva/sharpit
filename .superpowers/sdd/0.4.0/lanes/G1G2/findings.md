# G1G2 findings

## Real red tests

| tests/<path>.py::<test> | Red SHA | Assertion |
|---|---|---|
| `tests/engine/testsession/test_gates.py::test_fails_excludes_existing_and_info` | `2cbbcadb67e99f715238773bf45438f64998ce46` | `assert fails(... baselineState='existing' ...) is False` |
| `tests/engine/advisors/test_findings.py::test_failed_run_with_incomplete_scan_has_unknown_reason` | `2cbbcadb67e99f715238773bf45438f64998ce46` | `assert run.reason == "one rule errored"` |
| `tests/engine/testsession/test_outcome.py::test_session_status_reports_unknown_reasons_when_fail` | `2cbbcadb67e99f715238773bf45438f64998ce46` | `assert _status(...) == ("fail", fail_reasons, unknown_reasons)` |
