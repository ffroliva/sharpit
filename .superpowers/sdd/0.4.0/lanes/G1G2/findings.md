# G1G2 findings

## Real red tests

| Test | Red SHA | Assertion |
|---|---|---|
| tests/engine/testsession/test_gates.py::test_fails_excludes_existing_and_info | 2cbbcad9eef91c2e7a2c27230b09014864284095 | assert fails(existing finding) is False |
| tests/engine/advisors/test_findings.py::test_failed_run_with_incomplete_scan_has_unknown_reason | 2cbbcad9eef91c2e7a2c27230b09014864284095 | assert run.reason == "one rule errored" |
| tests/engine/testsession/test_baseline.py::test_baseline_schema_and_sorted_bytes | 59c0ef017879221c9b87a26612d5323861f9e535 | assert payload["schema"] == "sharpit-baseline/1" |
| tests/engine/testsession/test_baseline.py::test_baseline_rejects_bad_schema | 59c0ef017879221c9b87a26612d5323861f9e535 | pytest.raises(ValueError, match="schema") |
| tests/engine/testsession/test_baseline.py::test_baseline_rejects_duplicate_fingerprint | 59c0ef017879221c9b87a26612d5323861f9e535 | pytest.raises(ValueError, match="duplicate fingerprint") |
| tests/engine/testsession/test_baseline.py::test_compare_existing_new_and_fixed | 59c0ef017879221c9b87a26612d5323861f9e535 | assert baseline states equal existing and new |
| tests/engine/testsession/test_baseline.py::test_partial_unseen_is_null_with_reason | 59c0ef017879221c9b87a26612d5323861f9e535 | assert result.fixed is None |
| tests/engine/testsession/test_baseline.py::test_count_gate_increase_is_new | 59c0ef017879221c9b87a26612d5323861f9e535 | assert result finding is new |
| tests/engine/testsession/test_partial.py::test_partial_when_deselected | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True |
| tests/engine/testsession/test_partial.py::test_partial_when_keyword_or_nodeid_selected | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True |
| tests/engine/testsession/test_partial.py::test_partial_when_last_failed_or_deselect_used | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True |
| tests/engine/testsession/test_partial.py::test_partial_when_maxfail_or_shouldstop | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True |
| tests/engine/testsession/test_partial.py::test_partial_when_interrupted | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True |
| tests/engine/testsession/test_partial.py::test_xdist_partial_facts_merged | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True |
| tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_refused_on_partial_xdist_run | 6ec00ff885aa897da820e1ed5cf768492673e19f | assert result.ret == 4 |
| tests/engine/testsession/test_outcome.py::test_report_only_still_fails_on_unknown_reason_when_status_is_fail | 54d3de134b1e33c0497766d103009953079f52d0 | assert exit_fails(...) is True |
| tests/engine/testsession/test_gates.py::test_per_finding_dismissal_reaches_gate | a78d9948b89bcd1f167e0ad354963f0804b1a46d | assert fails(finding.to_dto()) is False |
| tests/engine/testsession/test_outcome.py::test_failed_advisor_preserves_unknown_reason_when_status_fails | 4421b4fc0a8623c6a9c5ec2f31d3c984fad9aa70 | assert advisor limitation is in unknown_reasons |
| tests/engine/testsession/test_gates.py::test_baselined_query_count_increase_is_new | b7e0ee593c1f71133652a2778f2152e7897da778 | assert increased.baseline_state == "new" |
| tests/engine/testsession/test_gates.py::test_unlisted_finding_is_new | b7e0ee593c1f71133652a2778f2152e7897da778 | assert finding.baseline_state == "new" |
| tests/engine/advisors/test_advisor_report.py::test_dismissed_pair_matches_identity_with_spaces | 827fa397ff43fd86133ae34a09ddea27410ed23d | assert pair dismissal removes one occurrence |
| tests/engine/advisors/test_findings.py::test_existing_baseline_finding_does_not_fail_advisor_run | df9baa1fc01809c6aab839b6b8faa6660d4c595f | assert run.status == "PASSED" |
| tests/engine/testsession/test_partial.py::test_partial_selection_detects_last_failed_and_deselect_args | 3999ad510ac6cdec747eeb57298396d0635c6609 | assert selection_requested(["--lf"]) is True |
| tests/engine/testsession/test_baseline.py::test_vulnerability_findings_excluded_from_baseline | 2b1b59dbdc478ac333b5d4de53b1e47c8f35de81 | assert baseline.read(path).entries == {} |
| tests/engine/testsession/test_report.py::test_report_only_junit_fails_status_only_for_unknown_reason | 71f0936c29b54b784cecafc89cc5795cd329b347 | assert clean status has no failure in report-only mode |
| tests/engine/testsession/test_outcome.py::test_merge_keeps_incomplete_reason_when_another_failed_run_is_complete | 001f151a64a0aa40a9843f7d7905c78893f1e018 | assert merged unknown reasons retain incomplete run limitation |
| tests/engine/testsession/test_outcome.py::test_skipped_advisor_reason_does_not_make_capture_unknown | 8d3ffda60830b558757517cbec913cdba77ee85a | assert ordinary SKIPPED reason stays non-failing |

## Historical SHA

| Test | Historical SHA | Why |
|---|---|---|
| tests/engine/testsession/test_outcome.py::test_session_status_reports_unknown_reasons_when_fail | 2cbbcad9eef91c2e7a2c27230b09014864284095 | Its `_status` helper changed with the SessionStatus return API; direct coverage is in `test_failed_advisor_preserves_unknown_reason_when_status_fails`. |

## Characterisation updates

| Test id | Historical SHA | Reason |
|---|---|---|
| tests/test_foundation_round2.py::test_reserved_options_help_promises_no_behaviour | c2e385d | superseded: options became real in G1G2 |
| tests/test_foundation_review_fixes.py::test_report_only_options_leave_the_sharpit_report_unchanged | 4c3828b | superseded: options became real in G1G2 |
