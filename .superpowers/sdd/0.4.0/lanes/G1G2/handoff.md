# G1G2 handoff

Implementer: Codex / GPT-6

## Status

- Current head: `8d3ffda60830b558757517cbec913cdba77ee85a` (SKIPPED advisor regression red commit).
- Done: report-only, baseline lifecycle, xdist partial-run detection, baseline-aware gates, fail/unknown precedence, and per-finding dismissal matching. Targeted engine and plugin integration tests pass.
- Next: commit the implementation, run the final four detached gates without modifying the worktree, then update the gate table and handoff.
- Decisions: follow council-r3 R1/R6/R8; use `report.finding_fails` for terminal/JUnit. Dismissal key is `(rule_id, identity or target)`; identities may contain spaces.
- Red commit `2cbbcad9eef91c2e7a2c27230b09014864284095` pins the shared failure predicate and incomplete failed advisor reason; the status-helper test is historical because its helper changed for the tuple return contract.
- Red commit `59c0ef017879221c9b87a26612d5323861f9e535` pins baseline validation, stable serialization, comparison and partial fixed semantics.
- Red commits `6ec00ff885aa897da820e1ed5cf768492673e19f`, `54d3de134b1e33c0497766d103009953079f52d0`, `a78d9948b89bcd1f167e0ad354963f0804b1a46d`, `4421b4fc0a8623c6a9c5ec2f31d3c984fad9aa70`, `b7e0ee593c1f71133652a2778f2152e7897da778`, `827fa397ff43fd86133ae34a09ddea27410ed23d`, `df9baa1fc01809c6aab839b6b8faa6660d4c595f`, `3999ad510ac6cdec747eeb57298396d0635c6609`, `2b1b59dbdc478ac333b5d4de53b1e47c8f35de81`, and `71f0936c29b54b784cecafc89cc5795cd329b347` cover partial runs, report-only exits/JUnit, gate and advisor baseline states, pair matching, vulnerability exclusion, and failed advisor unknown reasons.

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/testsession/test_gates.py::test_fails_excludes_existing_and_info` | `2cbbcad9eef91c2e7a2c27230b09014864284095` | existing finding incorrectly fails |
| `tests/engine/advisors/test_findings.py::test_failed_run_with_incomplete_scan_has_unknown_reason` | `2cbbcad9eef91c2e7a2c27230b09014864284095` | incomplete failed run drops reason |
| `tests/engine/testsession/test_baseline.py::test_baseline_schema_and_sorted_bytes` | `59c0ef017879221c9b87a26612d5323861f9e535` | baseline document shape and sorting were wrong |
| `tests/engine/testsession/test_baseline.py::test_baseline_rejects_bad_schema` | `59c0ef017879221c9b87a26612d5323861f9e535` | invalid schema accepted |
| `tests/engine/testsession/test_baseline.py::test_baseline_rejects_duplicate_fingerprint` | `59c0ef017879221c9b87a26612d5323861f9e535` | duplicate fingerprint accepted |
| `tests/engine/testsession/test_baseline.py::test_compare_existing_new_and_fixed` | `59c0ef017879221c9b87a26612d5323861f9e535` | finding states omitted |
| `tests/engine/testsession/test_baseline.py::test_partial_unseen_is_null_with_reason` | `59c0ef017879221c9b87a26612d5323861f9e535` | partial run marked a finding fixed |
| `tests/engine/testsession/test_baseline.py::test_count_gate_increase_is_new` | `59c0ef017879221c9b87a26612d5323861f9e535` | count increase stayed existing |
| `tests/engine/testsession/test_partial.py::test_partial_when_deselected` | `7df1123d2f64b00ab482319d223fe1bfa542eeaf` | deselection was missed |
| `tests/engine/testsession/test_partial.py::test_partial_when_keyword_or_nodeid_selected` | `7df1123d2f64b00ab482319d223fe1bfa542eeaf` | selected run was missed |
| `tests/engine/testsession/test_partial.py::test_partial_when_last_failed_or_deselect_used` | `7df1123d2f64b00ab482319d223fe1bfa542eeaf` | selection fact was missed |
| `tests/engine/testsession/test_partial.py::test_partial_when_maxfail_or_shouldstop` | `7df1123d2f64b00ab482319d223fe1bfa542eeaf` | controller stop was missed |
| `tests/engine/testsession/test_partial.py::test_partial_when_interrupted` | `7df1123d2f64b00ab482319d223fe1bfa542eeaf` | interrupt was missed |
| `tests/engine/testsession/test_partial.py::test_xdist_partial_facts_merged` | `7df1123d2f64b00ab482319d223fe1bfa542eeaf` | worker facts were ignored |
| `tests/pytest_plugin/test_plugin_baseline.py::test_write_baseline_refused_on_partial_xdist_run` | `6ec00ff885aa897da820e1ed5cf768492673e19f` | complete-looking selected run wrote a baseline |
| `tests/engine/testsession/test_outcome.py::test_report_only_still_fails_on_unknown_reason_when_status_is_fail` | `54d3de134b1e33c0497766d103009953079f52d0` | report-only dropped unknown reason under fail status |
| `tests/engine/testsession/test_gates.py::test_per_finding_dismissal_reaches_gate` | `a78d9948b89bcd1f167e0ad354963f0804b1a46d` | fixed dismissed pair did not reach gate |
| `tests/engine/testsession/test_outcome.py::test_failed_advisor_preserves_unknown_reason_when_status_fails` | `4421b4fc0a8623c6a9c5ec2f31d3c984fad9aa70` | failed incomplete advisor reason was omitted |
| `tests/engine/testsession/test_gates.py::test_baselined_query_count_increase_is_new` | `b7e0ee593c1f71133652a2778f2152e7897da778` | count increase remained existing |
| `tests/engine/testsession/test_gates.py::test_unlisted_finding_is_new` | `b7e0ee593c1f71133652a2778f2152e7897da778` | unlisted finding did not get new state |
| `tests/engine/advisors/test_advisor_report.py::test_dismissed_pair_matches_identity_with_spaces` | `827fa397ff43fd86133ae34a09ddea27410ed23d` | space-containing identity pair did not remove occurrence |
| `tests/engine/advisors/test_findings.py::test_existing_baseline_finding_does_not_fail_advisor_run` | `df9baa1fc01809c6aab839b6b8faa6660d4c595f` | existing baseline finding still failed advisor run |
| `tests/engine/testsession/test_partial.py::test_partial_selection_detects_last_failed_and_deselect_args` | `3999ad510ac6cdec747eeb57298396d0635c6609` | `--lf` selection was missed |
| `tests/engine/testsession/test_baseline.py::test_vulnerability_findings_excluded_from_baseline` | `2b1b59dbdc478ac333b5d4de53b1e47c8f35de81` | vulnerability finding was written to baseline |
| `tests/engine/testsession/test_report.py::test_report_only_junit_fails_status_only_for_unknown_reason` | `71f0936c29b54b784cecafc89cc5795cd329b347` | report-only JUnit failed status for a finding with no unknown reason |
| `tests/engine/testsession/test_outcome.py::test_merge_keeps_incomplete_reason_when_another_failed_run_is_complete` | `001f151a64a0aa40a9843f7d7905c78893f1e018` | merged failed runs dropped the incomplete advisor reason |
| `tests/engine/testsession/test_outcome.py::test_skipped_advisor_reason_does_not_make_capture_unknown` | `8d3ffda60830b558757517cbec913cdba77ee85a` | ordinary skipped advisor reason incorrectly made the run unknown |

The older `test_session_status_reports_unknown_reasons_when_fail` row from `2cbbcad9eef91c2e7a2c27230b09014864284095` is historical: its helper changed for the SessionStatus tuple shape. The direct replacement is `test_failed_advisor_preserves_unknown_reason_when_status_fails`.
| `tests/engine/testsession/test_baseline.py::test_baseline_schema_and_sorted_bytes` | `59c0ef017879221c9b87a26612d5323861f9e535` | baseline document shape/sort incorrect |
| `tests/engine/testsession/test_baseline.py::test_baseline_rejects_bad_schema` | `59c0ef017879221c9b87a26612d5323861f9e535` | invalid schema accepted |
| `tests/engine/testsession/test_baseline.py::test_baseline_rejects_duplicate_fingerprint` | `59c0ef017879221c9b87a26612d5323861f9e535` | duplicate fingerprint accepted |
| `tests/engine/testsession/test_baseline.py::test_compare_existing_new_and_fixed` | `59c0ef017879221c9b87a26612d5323861f9e535` | finding comparison omitted states |
| `tests/engine/testsession/test_baseline.py::test_partial_unseen_is_null_with_reason` | `59c0ef017879221c9b87a26612d5323861f9e535` | partial run marks fixed incorrectly |
| `tests/engine/testsession/test_baseline.py::test_count_gate_increase_is_new` | `59c0ef017879221c9b87a26612d5323861f9e535` | increased count remains existing |

## Gates

Full gates are running / pending final frozen-worktree pass. Logs stay outside this worktree.

## Needs from coordinator

- Update `tests/test_foundation_round2.py::test_reserved_options_help_promises_no_behaviour`: G1G2 must replace F's reserved/no-effect option help with real descriptions, but this test is outside G1G2's May-touch list. It currently asserts the old help strings and will need new assertions for report-only and baseline behavior.
- Update `tests/test_foundation_review_fixes.py::test_report_only_options_leave_the_sharpit_report_unchanged`: it passes a nonexistent `baseline.json` with the now-active baseline option and expects an `options.json` report. The new session-start validation correctly exits before writing that report. This test is outside G1G2's May-touch list; update it with a valid baseline fixture and report-only expectations.
