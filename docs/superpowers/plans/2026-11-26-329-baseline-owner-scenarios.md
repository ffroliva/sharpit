# Scenario: a baseline entry is fixed only when its owner proved it (#329)

Plan: [2026-11-26-329-baseline-owner.md](2026-11-26-329-baseline-owner.md). Reason numbers (R1-R6) are the plan's
*Reasons* table: R1 recorded without its owner, R2 the run's evidence is incomplete, R3 its test did not run, R4 its
test did not complete, R5 its test has a new finding of the same rule, R6 its test still shows it outside the gate.

## Coverage map

| Dimension | Active | Why |
|---|---|---|
| D1 Safe mode fails closed | yes, as the gate's fail-closed rule | The console's activation is not touched; the pytest gate's rule "unproven is never fixed" is the subject of this change |
| D2 Activation and access guard | no | No request, route or guard step changes |
| D3 Secret masking | yes | The baseline gains an `owner` value derived from the node id; the report gains `inconclusiveFindings` |
| D4 Contract parity | yes | Report keys added inside `sharpit-report/1`; baseline key added inside `sharpit-baseline/1`; BootUI counterpart in run comparison |
| D5 Introspection drift | no | No FastAPI or Starlette internals are read |
| D6 No side effects on reads | yes, narrowly | Only the existing `--sharpit-write-baseline` path writes; nothing new opens a socket or file |
| D7 OSV/EPSS failures | no | Vulnerability findings are not baselined, unchanged |
| D8 Host-app integration | no | The pytest plugin's interaction with the host app is unchanged |
| D9 Scale and limits | yes | Session-end re-evaluation of facts; capture caps |
| D10 MCP and CLI parity | no | No MCP or CLI tool reads the baseline |

## Worst-case trace

Input: a baselined N+1 entry whose owner test now runs two subtests; the first fails before the route is called, the
second passes. pytest exits 1.

1. `src/sharpit/pytest_plugin/session.py:72`: each subtest's report has `when == "call"`, so the non-call branch
   (lines 72-77) is skipped.
2. `session.py:78`: `test.outcome = report_obj.outcome` runs once per call report. The failing subtest sets `failed`,
   the last report sets `passed`. The test's facts end with `outcome == "passed"`.
3. `session.py:91-99`: `evaluate_test` sees a call phase with no N+1 group (the route was never called), so the test
   has no finding for the entry.
4. `src/sharpit/pytest_plugin/report_io.py:108-118`: `_apply_baseline` calls `compare()` with the report's findings
   only; no test facts reach it.
5. `src/sharpit/engine/testsession/baseline.py:100`: the entry's fingerprint is not in `seen`, so it is `unseen`.
6. `baseline.py:101`: `ran` contains `test-runtime`, so the entry is not carried; `partial` is false.
7. `baseline.py:115`: the entry is returned in `fixed`; the report says `fixed: 1`.

Finding: even a rule that reads `outcome == "passed"` would report this entry fixed, because the outcome is the last
subtest's. The plan records completion per call report and keeps a failure sticky (`record_call_completion`, Task 3),
and reads it on the deciding attempt (R4, Task 4). Must-cover row 11.

## Scenario table

Severity: High where the run would report `fixed` for an entry it did not prove (the report's claim is wrong, and a
rewrite with both flags drops the entry); Critical where test-id text could reach a committed file; Medium where a real
fix would read as inconclusive, or a documented limit; Low for wording.

| # | Dimension | Scenario | Severity | Expected behaviour | Task | Test |
|---|---|---|---|---|---|---|
| 1 | D1 | Owner test deleted (the issue's reproduction) | High | inconclusive, R3 | 4, 5 | `test_deleted_owner_is_not_fixed`, `test_issue_329_deleted_test_is_not_fixed` |
| 2 | D1 | Owner test renamed | High | inconclusive, R3 | 4 | `test_renamed_owner_is_not_fixed` |
| 3 | D1 | Parametrize id of the owner changed | High | inconclusive, R3 (another node id, as a rename) | 4 | `test_renamed_owner_is_not_fixed` |
| 4 | D1 | Skip marker on the owner | High | inconclusive, R4 (no call report) | 4, 5 | `test_skipped_owner_is_not_fixed`, `test_skip_marker_on_the_owner_is_not_fixed` |
| 5 | D1 | `pytest.skip` in the owner's body, before or after the SQL | High | inconclusive, R4 (the call report did not pass) | 4 | `test_xfailed_owner_is_not_fixed` |
| 6 | D1 | Owner marked xfail | High | inconclusive, R4 | 4 | `test_xfailed_owner_is_not_fixed` |
| 7 | D1 | Setup error in the owner | High | inconclusive, R4 | 4 | `test_owner_with_setup_error_is_not_fixed` |
| 8 | D1 | Owner fails before it reaches the code | High | inconclusive, R4 | 4 | `test_owner_that_fails_before_the_code_is_not_fixed` |
| 9 | D1 | Teardown error after a passed call | Medium | fixed (the call completed) | 4 | `test_teardown_error_after_a_passed_call_is_fixed` |
| 10 | D1 | Owner fixed, but failed by another rule's new finding | Medium | fixed (completion is read before the gates) | 3, 4 | `test_completed_is_read_before_a_gate_fails_the_test`, `test_owner_failed_by_another_rule_is_fixed` |
| 11 | D1 | A failing subtest (built-in `subtests` or `unittest.subTest`), later ones pass | High | inconclusive, R4 (failure is sticky) | 3, 4 | `test_a_failing_report_keeps_completed_false`, `test_owner_with_a_failing_subtest_is_not_fixed` |
| 12 | D1 | `pytest.importorskip` skips the owner's module at collection | High | inconclusive, R3 (no facts) | 4 | `test_deleted_owner_is_not_fixed` |
| 13 | D1 | Collection error under `--continue-on-collection-errors` | High | inconclusive, R3 | 4 | `test_deleted_owner_is_not_fixed` |
| 14 | D1 | A conftest drops the owner item silently | High | inconclusive, R3 | 4 | `test_deleted_owner_is_not_fixed` |
| 15 | D1 | `--setup-only` or `--setup-plan` | High | inconclusive, R4 (no call report, `completed` is null) | 4 | `test_skipped_owner_is_not_fixed` |
| 16 | D1 | `-k`, `--lf`, `--deselect`, a node id: a partial run | Medium | `fixed`, `inconclusive` and `inconclusiveFindings` are null, `fixedReason: "partial run"` | 5 | `test_partial_run_keeps_inconclusive_null`, `test_partial_xdist_report_keeps_fixed_null` |
| 17 | D1 | `-n 2`, `--dist each`, loadgroup | Medium | same result as serial; node id unchanged | 5 | `test_fixed_for_a_real_fix_serial_and_xdist` |
| 18 | D1 | xdist worker crashes | High | inconclusive, R2 (unknown reason) | 5 | `test_crashed_xdist_worker_is_not_fixed` |
| 19 | D1 | Swallowed-exception capture not attached in a process | High | inconclusive, R2 | 5 | `test_unknown_reason_marks_every_rule_incomplete` |
| 20 | D1 | A session hook fails and drops SQL events | High | inconclusive, R2 (hook-failure warning) | 5 | `test_dropped_sql_events_are_not_fixed`, `test_hook_failure_warning_marks_every_rule_incomplete`, `test_hook_failure_warnings_start_with_the_prefix` |
| 21 | D1 | unbounded-read without `sharpit.install(app)` | High | unbounded-read entries inconclusive, R2; other rules unaffected | 4, 5 | `test_unbounded_read_limitation_withholds_only_its_rule`, `test_unbounded_read_without_install_is_not_fixed` |
| 22 | D1 | `allow_n_plus_one` added to the owner, the group still at 20 | High | inconclusive, R6 | 4 | `test_allow_n_plus_one_is_not_fixed` |
| 23 | D1 | N+1 threshold raised | High | inconclusive, R6 (re-evaluated at threshold 2) | 4 | `test_raised_threshold_is_not_fixed` |
| 24 | D1 | `max_exceptions` raised | High | inconclusive, R6 | 4 | `test_raised_max_exceptions_is_not_fixed` |
| 25 | D1 | `--sharpit-max-queries` dropped, count still at or above the baselined value | High | inconclusive, R6 | 4 | `test_dropped_max_queries_is_not_fixed`, `test_count_at_the_baselined_value_is_still_shown` |
| 26 | D1 | `allow_swallowed`: the finding is still listed (INFO) | Low | existing, as today | - | existing tests in `tests/pytest_plugin/test_plugin_swallowed_baseline.py`, unchanged |
| 27 | D1 | SQL text of the statement edited (identity drift) | High | inconclusive, R5 | 4 | `test_changed_statement_is_not_fixed` |
| 28 | D1 | Exception rule: lines moved, so the target changes | High | inconclusive, R5 (same mechanism, any rule) | 4 | `test_changed_statement_is_not_fixed` |
| 29 | D1 | SQLite identity key changed between runs | High | inconclusive, R5 | 4 | `test_changed_statement_is_not_fixed` |
| 30 | D1 | Request moved into a setup or teardown fixture | High | inconclusive, R6 (every phase re-evaluated) | 4, 5 | `test_finding_moved_to_setup_phase_is_not_fixed`, `test_request_moved_to_a_fixture_is_not_fixed` |
| 31 | D1 | Rerun: attempt 1 shows it and fails, attempt 2 is clean | High | inconclusive, R6 (every attempt examined) | 4 | `test_finding_in_an_earlier_rerun_attempt_is_not_fixed` |
| 32 | D1 | Flaky rerun with the code fixed | Medium | fixed (`completed` read on the deciding attempt) | 4 | `test_flaky_rerun_with_the_code_fixed_is_fixed` |
| 33 | D1 | The owner's body no longer calls the route | Medium | fixed: accepted limit, no route evidence per test | 8 | documented in `docs/decisions/baseline-owner.md` |
| 34 | D1 | N+1 moved to a thread no test owns, under the unattributed limit | Medium | fixed: accepted limit | 8 | documented in `docs/decisions/baseline-owner.md` |
| 35 | D4 | Entry from a baseline written before this change (no `owner`) | High | inconclusive, R1; kept on rewrite; gains `owner` when the finding is seen and written again | 2, 4 | `test_legacy_entry_reads_without_owner`, `test_entry_without_owner_is_not_fixed` |
| 36 | D6 | `--sharpit-write-baseline` with `--sharpit-baseline`: an inconclusive entry | High | kept with its `owner`; fixed entries dropped | 4, 5 | `test_inconclusive_entry_is_carried`, `test_write_keeps_an_inconclusive_entry` |
| 37 | D4 | Advisor entry (for example `rest-api`) not seen | Medium | current rule: fixed when the advisor ran in full; `owner` ignored | 2, 4 | `test_advisor_entry_is_written_without_owner`, `test_advisor_entry_keeps_the_current_rule` |
| 38 | D1 | A real fix: owner ran, completed, clean | Medium | fixed | 4, 5 | `test_completed_clean_owner_is_fixed`, `test_fixed_for_a_real_fix_serial_and_xdist` |
| 39 | D3 | Parametrize id carries a secret-looking value | Critical | `owner` is a 16-hex digest; the id text is not in it | 2 | `test_written_owner_has_no_node_id_text` |
| 40 | D3 | `inconclusiveFindings` content | High | fingerprint and a fixed reason string only, no application text | 5 | `test_report_lists_inconclusive_with_reason` |
| 41 | D4 | Written entry names its owner | High | `owner == sha256(node id)[:16]` | 2 | `test_written_entry_names_its_owner` |
| 42 | D4 | `owner` read back from a file | High | kept on the entry | 2 | `test_read_keeps_the_owner` |
| 43 | D4 | `owner` of a wrong type in the file | High | malformed baseline (`ValueError`), an unknown reason | 2 | `test_read_rejects_an_owner_that_is_not_a_string` |
| 44 | D4 | Rewrite of its own output | Medium | byte-identical | 2 | `test_rewrite_of_own_output_is_byte_identical`, `test_baseline_schema_and_sorted_bytes` |
| 45 | D4 | `completed` across the worker JSON round trip | High | kept | 3 | `test_completed_survives_the_worker_round_trip` |
| 46 | D4 | `completed` missing from a worker's facts | High | `None`, so R4 | 3 | `test_completed_missing_from_a_worker_is_none` |
| 47 | D1 | A rerun that reuses the facts of an attempt that recorded no event | High | `completed` reset at each setup report | 3 | `test_setup_report_resets_completed` |
| 48 | D1 | xpass | Medium | fixed | 4 | `test_xpass_owner_is_fixed` |
| 49 | D1 | `allow_n_plus_one`, group gone to 1 statement | Medium | fixed | 4 | `test_relaxed_gate_with_the_finding_gone_is_fixed` |
| 50 | D1 | Every rule withheld when the run is incomplete; two owners, one ran | High | the one that ran is fixed, the other R3; under incomplete evidence none is fixed | 4 | `test_gone_only_where_its_owner_ran_again`, `test_evidence_not_recorded_whole_withholds_and_fixes_nothing`, `test_incomplete_evidence_is_not_fixed` |
| 51 | D4 | Report keys present and typed | High | `inconclusive` integer or null; `inconclusiveFindings` list or null; not in `required` | 5 | `test_report_schema_accepts_inconclusive_keys`, `test_report_schema_accepts_a_report_without_inconclusive_keys` |
| 52 | D4 | Summary line | Low | `, inconclusive N` after the fixed count; unchanged for an older report | 6 | `test_summary_prints_inconclusive`, `test_summary_without_inconclusive_is_unchanged` |
| 53 | D9 | `unbounded_read_factor` raised: facts above it are never kept | Medium | fixed: accepted limit | 8 | documented in `docs/decisions/baseline-owner.md` |
| 54 | D9 | A loosened gate whose count falls but stays above the old limit (the old limit is not stored) | Medium | fixed: accepted limit | 8 | documented in `docs/decisions/baseline-owner.md` |
| 55 | D9 | A statement loses its identity (unsupported dialect, unreadable text): it joins no N+1 group | Medium | fixed: accepted limit; a missing SQLite identity key is an unknown reason (R2) | 8 | documented in `docs/decisions/baseline-owner.md` |
| 56 | D9 | Capture caps (unattributed statements, statement sites, N+1 rows per test) | Low | no finding is dropped by a cap; no change | - | none needed |
| 57 | D4 | An older sharpit rewrites a new baseline | Low | drops `owner`; entries then read R1, never fixed | 8 | CHANGELOG entry |

## Must-cover before merge

Every Critical and High row. Full node ids, so no name is ambiguous across files.

- `tests/engine/testsession/test_baseline.py::test_written_entry_names_its_owner`
- `tests/engine/testsession/test_baseline.py::test_read_keeps_the_owner`
- `tests/engine/testsession/test_baseline.py::test_read_rejects_an_owner_that_is_not_a_string`
- `tests/engine/testsession/test_baseline.py::test_written_owner_has_no_node_id_text`
- `tests/engine/testsession/test_baseline.py::test_legacy_entry_reads_without_owner`
- `tests/engine/testsession/test_sink.py::test_completed_survives_the_worker_round_trip`
- `tests/engine/testsession/test_sink.py::test_completed_missing_from_a_worker_is_none`
- `tests/pytest_plugin/test_plugin_session_completed.py::test_a_failing_report_keeps_completed_false`
- `tests/pytest_plugin/test_plugin_session_completed.py::test_setup_report_resets_completed`
- `tests/engine/testsession/test_baseline.py::test_entry_without_owner_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_incomplete_evidence_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_unbounded_read_limitation_withholds_only_its_rule`
- `tests/engine/testsession/test_baseline.py::test_deleted_owner_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_renamed_owner_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_skipped_owner_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_xfailed_owner_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_owner_that_fails_before_the_code_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_owner_with_setup_error_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_owner_with_a_failing_subtest_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_changed_statement_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_allow_n_plus_one_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_raised_threshold_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_raised_max_exceptions_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_dropped_max_queries_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_count_at_the_baselined_value_is_still_shown`
- `tests/engine/testsession/test_baseline.py::test_finding_moved_to_setup_phase_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_finding_in_an_earlier_rerun_attempt_is_not_fixed`
- `tests/engine/testsession/test_baseline.py::test_inconclusive_entry_is_carried`
- `tests/engine/testsession/test_baseline.py::test_gone_only_where_its_owner_ran_again`
- `tests/engine/testsession/test_baseline.py::test_evidence_not_recorded_whole_withholds_and_fixes_nothing`
- `tests/engine/testsession/test_baseline.py::test_unknown_reason_marks_every_rule_incomplete`
- `tests/engine/testsession/test_baseline.py::test_hook_failure_warning_marks_every_rule_incomplete`
- `tests/engine/testsession/test_baseline.py::test_unbounded_read_without_install_is_not_fixed`
- `tests/engine/testsession/test_finish.py::test_hook_failure_warnings_start_with_the_prefix`
- `tests/pytest_plugin/test_plugin_baseline.py::test_issue_329_deleted_test_is_not_fixed`
- `tests/pytest_plugin/test_plugin_baseline.py::test_skip_marker_on_the_owner_is_not_fixed`
- `tests/pytest_plugin/test_plugin_baseline.py::test_crashed_xdist_worker_is_not_fixed`
- `tests/pytest_plugin/test_plugin_baseline.py::test_dropped_sql_events_are_not_fixed`
- `tests/pytest_plugin/test_plugin_baseline.py::test_request_moved_to_a_fixture_is_not_fixed`
- `tests/pytest_plugin/test_plugin_baseline.py::test_write_keeps_an_inconclusive_entry`
- `tests/pytest_plugin/test_plugin_baseline.py::test_report_lists_inconclusive_with_reason`
- `tests/test_report_schema.py::test_report_schema_accepts_inconclusive_keys`

Medium guards that the merge also requires, because each is the proof that a real fix still reads as fixed:
`test_completed_clean_owner_is_fixed`, `test_fixed_for_a_real_fix_serial_and_xdist`,
`test_teardown_error_after_a_passed_call_is_fixed`, `test_owner_failed_by_another_rule_is_fixed`,
`test_completed_is_read_before_a_gate_fails_the_test`, `test_flaky_rerun_with_the_code_fixed_is_fixed`,
`test_xpass_owner_is_fixed`, `test_relaxed_gate_with_the_finding_gone_is_fixed`,
`test_advisor_entry_keeps_the_current_rule`, `test_partial_run_keeps_inconclusive_null`.

## Deferred

Rows 33, 34, 53, 54 and 55 are accepted limits, recorded in the decision record (plan Task 8). Route evidence per test
would close row 33; it needs a per-test route capture on the capture path and its own predict and council.

## Known-issues cross-reference

The change does not touch activation, the guard, the masking of findings or the OSV scan. `/sharpit:known-issues` runs
before Task 3, and any open entry on the pytest gate's unknown reasons is linked from the PR: rows 18-20 read the unknown
reasons as they are and change none of them.
