# findings: g1g2-red-audit

Every row was replayed at its Red SHA in a detached worktree (PYTHONPATH = that tree's `src`, the tree, `tests/scripts`) and failed with the AssertionError shown; each passes at the head.

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| one red rule under tests/ (review F2) | `tests/scripts/test_lane_gate.py::test_lane_gate_exposes_the_one_accept_rule` | `d758b55bfff9450c0cf32ba8cb9221e791b82dec` | `AssertionError: lane_gate exposes no public is_red for red_check to share` | Fixed in 9da7938 |
| one red rule under tests/ (review F2) | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_failure_with_teardown_error` | `d758b55bfff9450c0cf32ba8cb9221e791b82dec` | `AssertionError: assert False` | Fixed in 9da7938 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_assert_in_a_helper_under_tests_is_red` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 'ERROR (collection)' == 'RED (assertion under tests/)'` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_assert_inside_scripts_is_refused` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: ERROR (collection)` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_assert_inside_src_is_refused` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: ERROR (collection)` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_did_not_raise_from_the_test_file_is_red` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 'ERROR (collection)' == 'RED (assertion under tests/)'` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_exit_code_zero_only_when_every_test_is_red` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 1 == 0` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_ids_are_normalised_to_rootdir_relative_posix` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert {'tests\\test...(collection)'} == {'tests/test_...nder tests/)'}` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_one_passing_parametrisation_makes_the_id_not_a_red` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 'ERROR (collection)' == 'PASS (not a red)'` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_output_shows_pytest_tail_for_a_crash_and_is_ascii` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: ERROR (collection)  tests/test_mod.py::test_crash_stub` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_passing_test_is_not_a_red` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 'ERROR (collection)' == 'PASS (not a red)'` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_red_with_teardown_error_is_not_a_clean_red` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 'ERROR (collection)' == 'ERROR (fixtu...tup/teardown)'` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_setup_error_is_a_fixture_error` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 'ERROR (collection)' == 'ERROR (fixtu...tup/teardown)'` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_type_error_stub_is_crash` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: ERROR (collection)` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_unknown_id_is_a_collection_error_and_does_not_poison_the_batch` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 'ERROR (collection)' == 'RED (assertion under tests/)'` | Fixed in ec22257 |
| red_check usability (review F3/F4/F6) | `tests/scripts/test_red_check.py::test_valid_assertion_red_is_red` | `f853441da6f9500e22c0a275b9c343082cb4a630` | `AssertionError: assert 'ERROR (collection)' == 'RED (assertion under tests/)'` | Fixed in ec22257 |
| round 2: no-frame fails closed, helper DID NOT RAISE, collection timeout | `tests/scripts/test_lane_gate.py::test_lane_gate_accepts_did_not_raise_from_a_helper_under_tests` | `45b2c09061a142b25ccdcaf3d4ffe484b7804106` | `AssertionError: assert ['red tests/t...play refused'] == []` | Fixed in e95b53f |
| round 2: no-frame fails closed, helper DID NOT RAISE, collection timeout | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_assertion_without_a_traceback_frame` | `45b2c09061a142b25ccdcaf3d4ffe484b7804106` | `AssertionError: assert False` | Fixed in e95b53f |
| round 2: no-frame fails closed, helper DID NOT RAISE, collection timeout | `tests/scripts/test_red_check.py::test_assertion_without_a_traceback_frame_is_not_red` | `45b2c09061a142b25ccdcaf3d4ffe484b7804106` | `AssertionError: RED (assertion under tests/)` | Fixed in e95b53f |
| round 2: no-frame fails closed, helper DID NOT RAISE, collection timeout | `tests/scripts/test_red_check.py::test_collection_timeout_is_reported_not_raised` | `45b2c09061a142b25ccdcaf3d4ffe484b7804106` | `AssertionError: assert {'tests/test_...eoutExpired>'} == {'tests/test_...ion timeout)'}` | Fixed in e95b53f |
| round 2: no-frame fails closed, helper DID NOT RAISE, collection timeout | `tests/scripts/test_red_check.py::test_did_not_raise_from_a_helper_under_tests_is_red` | `45b2c09061a142b25ccdcaf3d4ffe484b7804106` | `AssertionError: assert 'CRASH (Faile...ng-value stub' == 'RED (assertion under tests/)'` | Fixed in e95b53f |

### Historical SHA

Tests that pass at their commit by design, or whose red no longer satisfies red integrity at the head. Each is
mutation-proven on the head code (mutation applied, single test run, reverted, passes again).

| Test | Historical SHA | Reason |
|---|---|---|
| `tests/engine/testsession/test_baseline.py::test_vulnerability_advisor_excluded_whatever_the_rule_id` | `3e57653` | mutation-proven: baseline.py:118 drop the advisor clause -> AssertionError a vulnerability-advisor finding was written to the baseline |
| `tests/engine/testsession/test_baseline.py::test_vuln_rule_id_excluded_whatever_the_advisor` | `3e57653` | mutation-proven: baseline.py:120 drop the VULN- clause -> AssertionError a VULN- rule finding was written to the baseline |
| `tests/engine/testsession/test_baseline.py::test_compare_leaves_vulnerability_advisor_findings_unannotated` | `4d99d5b` | mutation-proven: baseline.py:86 compare() drops the advisor clause (and, separately, .lower()) -> AssertionError a 'vulnerability' (a 'Vulnerability') finding was compared against the baseline |
| `tests/engine/testsession/test_baseline.py::test_compare_leaves_vuln_rule_findings_unannotated` | `4d99d5b` | mutation-proven: baseline.py:86 compare() drops the VULN- clause -> AssertionError a VULN- rule finding was compared against the baseline |
| `tests/engine/testsession/test_baseline.py::test_compare_never_reports_a_vuln_entry_as_fixed` | `4d99d5b` | mutation-proven: baseline.py:102 fixed = tuple(unseen) -> AssertionError a hand-written VULN- baseline entry was reported as fixed |
| `tests/engine/testsession/test_baseline.py::test_write_excludes_vulnerability_advisor_whatever_its_case` | `4d99d5b` | mutation-proven: baseline.py:118 write() drops .lower() -> AssertionError a 'Vulnerability' finding was written to the baseline |
| `tests/scripts/test_lane_gate.py::test_lane_gate_accepts_helper_under_tests_by_absolute_path` | `d758b55` | mutation-proven: lane_gate._is_under_tests skips the root relativisation -> AssertionError assert ['red tests/t...play refused'] == [] (passes at d758b55 by design: a guard) |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_assert_raised_in_scripts` | `d758b55` | mutation-proven: lane_gate._is_under_tests accepts scripts/ -> AssertionError assert False (_refused ... not under tests/); red at d758b55, refusal wording changed in 9da7938 |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_assert_raised_in_src_by_absolute_path` | `d758b55` | mutation-proven: lane_gate._is_under_tests returns True for any frame under the root -> AssertionError assert False (_refused ... not under tests/); red at d758b55, refusal wording changed in 9da7938 |
| `tests/scripts/test_red_check.py::test_file_path_expands_to_its_node_ids` | `f853441` | mutation-proven: red_check._expand keeps no node id -> AssertionError {'tests/test_mod.py': 'ERROR (collection)'} (at f853441 it crashed with IndexError, so it is not listed as a red) |
| `tests/scripts/test_red_check.py::test_warns_about_uncommitted_files_the_tests_import` | `f853441` | mutation-proven: red_check.main skips the warning -> AssertionError (empty stderr); its helper _project changed in 45b2c09 |

The first red_check red (`f5e6311`) is history only: every test it added was rewritten in `f853441`, which is the red recorded above.
