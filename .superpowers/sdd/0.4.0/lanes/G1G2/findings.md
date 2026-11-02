# G1G2 findings

## Real red tests

| Test | Red SHA | Assertion | Disposition |
|---|---|---|---|
| tests/engine/testsession/test_gates.py::test_fails_excludes_existing_and_info | 2cbbcad9eef91c2e7a2c27230b09014864284095 | assert fails(existing finding) is False | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/advisors/test_findings.py::test_failed_run_with_incomplete_scan_has_unknown_reason | 2cbbcad9eef91c2e7a2c27230b09014864284095 | assert run.reason == "one rule errored" | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_baseline.py::test_baseline_schema_and_sorted_bytes | 59c0ef017879221c9b87a26612d5323861f9e535 | assert payload["schema"] == "sharpit-baseline/1" | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_baseline.py::test_baseline_rejects_bad_schema | 59c0ef017879221c9b87a26612d5323861f9e535 | pytest.raises(ValueError, match="schema") | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_baseline.py::test_baseline_rejects_duplicate_fingerprint | 59c0ef017879221c9b87a26612d5323861f9e535 | pytest.raises(ValueError, match="duplicate fingerprint") | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_baseline.py::test_compare_existing_new_and_fixed | 59c0ef017879221c9b87a26612d5323861f9e535 | assert baseline states equal existing and new | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_baseline.py::test_partial_unseen_is_null_with_reason | 59c0ef017879221c9b87a26612d5323861f9e535 | assert result.fixed is None | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_baseline.py::test_count_gate_increase_is_new | 59c0ef017879221c9b87a26612d5323861f9e535 | assert result finding is new | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_partial.py::test_partial_when_deselected | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_partial.py::test_partial_when_keyword_or_nodeid_selected | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_partial.py::test_partial_when_last_failed_or_deselect_used | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_partial.py::test_partial_when_maxfail_or_shouldstop | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_partial.py::test_partial_when_interrupted | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_partial.py::test_xdist_partial_facts_merged | 7df1123d2f64b00ab482319d223fe1bfa542eeaf | assert partial_run(...) is True | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_refused_on_partial_xdist_run | 6ec00ff885aa897da820e1ed5cf768492673e19f | assert result.ret == 4 | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_outcome.py::test_report_only_still_fails_on_unknown_reason_when_status_is_fail | 54d3de134b1e33c0497766d103009953079f52d0 | assert exit_fails(...) is True | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_gates.py::test_per_finding_dismissal_reaches_gate | a78d9948b89bcd1f167e0ad354963f0804b1a46d | assert fails(finding.to_dto()) is False | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_outcome.py::test_failed_advisor_preserves_unknown_reason_when_status_fails | 4421b4fc0a8623c6a9c5ec2f31d3c984fad9aa70 | assert advisor limitation is in unknown_reasons | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_gates.py::test_baselined_query_count_increase_is_new | b7e0ee593c1f71133652a2778f2152e7897da778 | assert increased.baseline_state == "new" | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_gates.py::test_unlisted_finding_is_new | b7e0ee593c1f71133652a2778f2152e7897da778 | assert finding.baseline_state == "new" | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/advisors/test_advisor_report.py::test_dismissed_pair_matches_identity_with_spaces | 827fa397ff43fd86133ae34a09ddea27410ed23d | assert pair dismissal removes one occurrence | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/advisors/test_findings.py::test_existing_baseline_finding_does_not_fail_advisor_run | df9baa1fc01809c6aab839b6b8faa6660d4c595f | assert run.status == "PASSED" | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_partial.py::test_partial_selection_detects_last_failed_and_deselect_args | 3999ad510ac6cdec747eeb57298396d0635c6609 | assert selection_requested(["--lf"]) is True | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_baseline.py::test_vulnerability_findings_excluded_from_baseline | 2b1b59dbdc478ac333b5d4de53b1e47c8f35de81 | assert baseline.read(path).entries == {} | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_report.py::test_report_only_junit_fails_status_only_for_unknown_reason | 71f0936c29b54b784cecafc89cc5795cd329b347 | assert clean status has no failure in report-only mode | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_outcome.py::test_merge_keeps_incomplete_reason_when_another_failed_run_is_complete | 001f151a64a0aa40a9843f7d7905c78893f1e018 | assert merged unknown reasons retain incomplete run limitation | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |
| tests/engine/testsession/test_outcome.py::test_skipped_advisor_reason_does_not_make_capture_unknown | 8d3ffda60830b558757517cbec913cdba77ee85a | assert ordinary SKIPPED reason stays non-failing | Fixed in e57a5e4e8ca71cbebc76ab26ded75501145df000 |

## Historical SHA

| Test | Historical SHA | Why |
|---|---|---|
| tests/engine/testsession/test_outcome.py::test_session_status_reports_unknown_reasons_when_fail | 2cbbcad9eef91c2e7a2c27230b09014864284095 | Its `_status` helper changed with the SessionStatus return API; direct coverage is in `test_failed_advisor_preserves_unknown_reason_when_status_fails`. |

## Characterisation updates

| Test id | Historical SHA | Reason |
|---|---|---|
| tests/test_foundation_round2.py::test_reserved_options_help_promises_no_behaviour | c2e385d | superseded: options became real in G1G2 |
| tests/test_foundation_review_fixes.py::test_report_only_options_leave_the_sharpit_report_unchanged | 4c3828b | superseded: options became real in G1G2 |

## Review round 1 (review.md, ponytail-review.md, /code-review xhigh) — Claude Opus 5.5 subagent

| Test | Red SHA | Assertion | Disposition |
|---|---|---|---|
| tests/engine/testsession/test_outcome.py::test_fail_on_info_advisor_finding_counts_consistently | 133feb06566cd021caed5809857fb43765816c30 | assert 'fail' == 'pass' | Fixed in 9d6f2d0dc79b6f5d6c7b44a144f98c6ea18d5bb7 |
| tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_refused_on_single_process_deselection | cf77b991ea9c9987f363931a81aebb13cabe6c5e | assert ExitCode.OK == 4 | Fixed in a09b5fcab4b63729770f617e2afc9f2207e16a94 |
| tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_refused_on_single_process_marker_addopts | cf77b991ea9c9987f363931a81aebb13cabe6c5e | assert ExitCode.OK == 4 | Fixed in a09b5fcab4b63729770f617e2afc9f2207e16a94 |
| tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_refused_on_conftest_deselection | cf77b991ea9c9987f363931a81aebb13cabe6c5e | assert ExitCode.OK == 4 | Fixed in a09b5fcab4b63729770f617e2afc9f2207e16a94 |
| tests/pytest_plugin/test_plugin_baseline.py::test_single_process_keyword_addopts_keeps_fixed_null | 1a8efbf7ab92e1a09d80405fc1cdd8b8de36f1c7 | assert 1 is None | Fixed in a09b5fcab4b63729770f617e2afc9f2207e16a94 |
| tests/engine/testsession/test_partial.py::test_partial_when_controller_deselected_without_workers | 1a8efbf7ab92e1a09d80405fc1cdd8b8de36f1c7 | assert partial_run([], {"deselected": 1}) is True | Fixed in a09b5fcab4b63729770f617e2afc9f2207e16a94 |
| tests/pytest_plugin/test_plugin_bad_baseline.py::test_bad_baseline_usage_error_at_session_start | 712ce8d00ed6e17c6a58ecc404c328c956cca484 | assert ret != 4 (USAGE_ERROR) / report.json absent | Fixed in 9c5af6abe32aee84b68d451f9c07a990cb76a771 |
| tests/pytest_plugin/test_plugin_bad_baseline.py::test_unreadable_baseline_is_unknown | 712ce8d00ed6e17c6a58ecc404c328c956cca484 | assert ret != 4 (USAGE_ERROR) | Fixed in 9c5af6abe32aee84b68d451f9c07a990cb76a771 |
| tests/pytest_plugin/test_plugin_bad_baseline.py::test_bad_baseline_allowed_unknown_exits_zero | 712ce8d00ed6e17c6a58ecc404c328c956cca484 | assert report.json exists (deep nesting turned sharpit off) | Fixed in 9c5af6abe32aee84b68d451f9c07a990cb76a771 |
| tests/engine/testsession/test_outcome.py::test_unknown_app_beside_failed_app_keeps_unknown_reason | 85dd81c67db822c2af87dacb0c7e8857c7b708b8 | reason in [] | Fixed in c930333106565b245028cdfb0cacae24f7c7fc9a |
| tests/engine/testsession/test_outcome.py::test_unknown_worker_beside_failed_worker_keeps_unknown_reason | 85dd81c67db822c2af87dacb0c7e8857c7b708b8 | reason in [] | Fixed in c930333106565b245028cdfb0cacae24f7c7fc9a |
| tests/engine/testsession/test_baseline.py::test_fixed_only_for_advisors_that_ran | a5aa485c4f4a04613f36c097f8d5f6d3ce7812b8 | assert (entries...) is None | Fixed in 22ef402fc0713bfc0525eca69525a37971fcdb08 |
| tests/engine/testsession/test_baseline.py::test_write_keeps_carried_entries | a5aa485c4f4a04613f36c097f8d5f6d3ce7812b8 | fingerprint in entries | Fixed in 22ef402fc0713bfc0525eca69525a37971fcdb08 |
| tests/engine/testsession/test_baseline.py::test_dismissed_findings_not_written | a5aa485c4f4a04613f36c097f8d5f6d3ce7812b8 | assert {...} == {} | Fixed in 22ef402fc0713bfc0525eca69525a37971fcdb08 |
| tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_requires_path | 68f6cefc09f8b2e54c35b7e88a876866cc6a7a27 | assert ExitCode.OK == 4 | Fixed in 5c15cb87ade6310de742edd63a811eef858f2c59 |
| tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_ini_option_writes_nothing | 68f6cefc09f8b2e54c35b7e88a876866cc6a7a27 | assert not exists() | Fixed in 5c15cb87ade6310de742edd63a811eef858f2c59 |
| tests/engine/testsession/test_baseline.py::test_baseline_write_cleans_lone_surrogates_and_uses_lf | 54ba9dd4c5993116f6beb1fd2cdd9c4f1b25891e | assert path.exists() | Fixed in be8f0883954e625bc39c0cd34e0a2aa741a86385 |

### Superseded in this round

| Test | Historical SHA | Why |
|---|---|---|
| tests/pytest_plugin/test_plugin_baseline.py::test_single_process_deselection_keeps_fixed_null | cf77b991ea9c9987f363931a81aebb13cabe6c5e | its `-k x` also matched its own module name (`...fixed...`), so nothing was deselected; deleted in bacbb1e, replaced by `test_single_process_keyword_addopts_keeps_fixed_null` |

### Characterisation (pinned, no red: behaviour already correct)

- `tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_refused_on_single_process_command_line_selection` (-k, -m on the command line)
- `tests/engine/testsession/test_gates.py::test_fingerprint_stable_across_runtime_values` (worker, attempt, counts, SQL literals)
- `tests/engine/testsession/test_gates.py::test_explicit_dismissal_wins_over_baseline`

### Open (not done in the 05:35 box)

- B3/6/7 partial.py: directory args and --ignore/--ignore-glob not partial; `-W x::y` / `-o key=val.py` misread as selection; `-x/--maxfail` partial without a stop.
- B8 baseline write failure after the report is written (order, terminal line, unknown reason).
- B10 vulnerability exclusion matches dead names (`vulnerability`/`vulns`/`VULN-`); real id `vulnerabilities`; report note absent.
- B14 schema copies: new keys not in `required`.
- C11 hook-failure refresh into unknownReasons; C15 one existing/new helper (three copies; restapi copy ignores `observed`); exception findings `observed=null`; `_partial_facts` unguarded.
- review #5 xdist transport test (ini addopts -k with -n 2), #6 masking test decoration; remaining plan-named tests from review #4.
- Decision recorded: INFO findings never fail (coordinator ruling); `fails` lives in `advisors/findings.py`, re-exported by `gates`.
- Decision recorded: a malformed/unreadable baseline is no longer a usage error; it is an unknown reason `baseline unusable: <why>` (source `baseline`, not attached), `report.baseline` null, write-baseline refused by the unknown rule.
