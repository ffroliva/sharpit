# Findings: lane F5-gate (gated as `F`)

Each row is a rule the 0.5.0 gate lacked; the red test proves the old gate accepted (or mis-read) it.

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| release hard-coded to 0.4.0 | `tests/scripts/test_lane_gate.py::test_lane_gate_release_is_a_parameter` | `9512fbf2bb9d67f622d02dee67e39786377cabad` | evidence read from 0.4.0 under `release="0.5.0"` | Fixed in 1abf414 |
| reviewer-owned paths only for 0.4.0 | `tests/scripts/test_lane_gate.py::test_reviewer_owned_paths_follow_release` | `9512fbf2bb9d67f622d02dee67e39786377cabad` | a 0.5.0 `review.md` in the lane diff accepted | Fixed in 1abf414 |
| unresolvable release not refused | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_unresolvable_release` | `32c16040231d6a955d06be130491c023c6ea555f` | detached integration HEAD accepted | Fixed in 1abf414 |
| protected files by `lane == "F"` only | `tests/scripts/test_lane_gate.py::test_protected_allowed_per_lane` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | no `PROTECTED_ALLOWED` table | Fixed in afc74ec |
| dependency lists by `F` only | `tests/scripts/test_lane_gate.py::test_dependency_change_allowed_per_lane` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | F5a-harness refused | pin: split by lane in fix round 2 (5dbd83c), so its red at e6390d0 no longer replays; mutant `if lane in DEPENDENCY_ALL:` becomes `if True:` kills it (handoff Pin). Fixed in afc74ec |
| baseline re-key by `F` only | `tests/scripts/test_lane_gate.py::test_baseline_rekey_only_for_foundation_lanes` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | F5a-core re-key refused | Fixed in afc74ec |
| leased check by bare name, A-postgresql only | `tests/scripts/test_lane_gate.py::test_leased_check_uses_full_node_ids` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | no `LEASED` mapping | Fixed in afc74ec ; re-red for council round 1, fixed in 311fec1 |
| no council check | `tests/scripts/test_lane_gate.py::test_council_required_read_per_lane_from_plan_table` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | missing `council.md` accepted | Fixed in 4f348db ; re-red for council round 1, fixed in 311fec1 |
| shallow council accepted | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_shallow_council_file` | `5fe96709b191d87ab35bf800ebbd21466506b228` | no verdict / one family / no SHA accepted | Fixed in 4f348db |
| no must-cover check | `tests/scripts/test_lane_gate.py::test_must_cover_uses_full_node_ids_and_refuses_skips` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | absent must-cover test accepted | pin: fix round 2 (ea8a3e1) adds the plan's golden mark to its golden-skip cases; mutant golden skip accepted without --accept-unverified kills it (handoff Pin). Fixed in 4f348db and 311fec1 |
| pin and N/A findings rows refused | `tests/scripts/test_lane_gate.py::test_findings_accept_pin_and_na_rows` | `4a4b4c81c5624af92ab1a9502dab8224711f194a` | `pin:` row reported unresolved | Fixed in 57903d5 |
| council 1: council.md accepted from the lane tree | `tests/scripts/test_lane_gate.py::test_council_md_in_the_lane_tree_is_refused` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | lane-committed council.md accepted | Fixed in 311fec1 |
| council 1: first APPROVE wins, WITH CHANGES approves, families named in prose count | `tests/scripts/test_lane_gate.py::test_council_reads_the_final_verdict_and_only_reviewers_that_ran` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | later BLOCK / WITH CHANGES / `not run` family accepted | Fixed in 311fec1 |
| council 1: a later APPROVE round and NITS | `tests/scripts/test_lane_gate.py::test_council_accepts_a_later_approve_round_and_nits` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | council in the integration tree refused as missing | Fixed in 311fec1 |
| council 1/7a: named commit followed by code changes | `tests/scripts/test_lane_gate.py::test_council_head_must_be_followed_only_by_lane_evidence` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | integration-tree council refused as missing | Fixed in 311fec1 |
| council 12: any Council cell other than required means not required | `tests/scripts/test_lane_gate.py::test_council_cell_must_be_required_not_required_or_a_dash` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | `**required**`, `yes`, blank accepted | Fixed in 311fec1 |
| council 2: golden skip passes without --accept-unverified | `tests/scripts/test_lane_gate.py::test_golden_skip_of_a_must_cover_test_needs_accept_unverified` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | golden skip not refused | pin: fix round 2 (ea8a3e1) adds the plan's golden mark; same mutant kills it (handoff Pin). Fixed in 311fec1 |
| council 3: plan files unprotected | `tests/scripts/test_lane_gate.py::test_plan_files_are_protected_in_every_lane_diff` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | lane edit of PLAN.md accepted | Fixed in 311fec1 |
| council 4: --plan-index/--plan outside the integration worktree | `tests/scripts/test_lane_gate.py::test_plan_index_and_plan_must_be_in_the_integration_worktree` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | lane-tree PLAN.md accepted | Fixed in 311fec1 |
| council 5a: F5b leased map misses a test | `tests/scripts/test_lane_gate.py::test_f5b_leased_log_needs_both_leased_tests` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | `LEASED["F5b"]` has one node id | Fixed in 311fec1 |
| council 6: dependency lanes may change every list | `tests/scripts/test_lane_gate.py::test_dependency_lanes_change_only_the_test_extra` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | F5a-harness runtime dependency accepted | pin: split by lane in fix round 2 (eacaa35, 60 s timeout); mutant (i) DEPENDENCY_ALLOWED lanes treated as DEPENDENCY_ALL kills it (handoff Pin). Fixed in 311fec1 |
| council 8: pin/N/A skips reds in handoff.md; pin row without a test | `tests/scripts/test_lane_gate.py::test_pin_and_na_rows_skip_reds_only_in_findings_md` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | handoff pin row skipped | Fixed in 311fec1 |
| council 9: --release not validated | `tests/scripts/test_lane_gate.py::test_release_name_is_validated` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | `..` accepted as a release | Fixed in 311fec1 |
| council 11: case-sensitive path checks | `tests/scripts/test_lane_gate.py::test_protected_and_reviewer_owned_paths_compare_case_insensitively` | `aa61040caa74a1c311cd8917a12010acc5c3c0a7` | `Tests/conftest.py` accepted | Fixed in 311fec1 |
| council R2-2: a golden skip passes for any must-cover test under --accept-unverified | `tests/scripts/test_lane_gate.py::test_golden_skip_is_accepted_only_for_a_test_the_plan_marks` | `ea8a3e10c0545950b11af29d93c00b0a1564e164` | unmarked `test_skip` recorded unverified, not refused | Fixed in 7ceb0f7 |
| council R2-4: `argon` model ids count no family | `tests/scripts/test_lane_gate.py::test_argon_counts_as_the_google_family` | `ea8a3e10c0545950b11af29d93c00b0a1564e164` | `assert [] == ['google']` | Fixed in 7ceb0f7 |
| council R2-5: a file at a lane folder, or another lane's folder, accepted | `tests/scripts/test_lane_gate.py::test_lane_diff_may_not_touch_another_sdd_lane_entry` | `d45eb5b9e5eeae540b2e0745f195312ebbc98ffb` | both planted paths accepted | Fixed in 7ceb0f7 |
| council R2-6: PLAN.md at the integration root unprotected | `tests/scripts/test_lane_gate.py::test_plan_index_at_the_integration_root_protects_that_file` | `ea8a3e10c0545950b11af29d93c00b0a1564e164` | lane edit of the root PLAN.md accepted | Fixed in 7ceb0f7 |
| council.md is coordinator-owned | | | the gate now reads it from the integration worktree only | Parked: the coordinator writes `council.md` there (round 1 council is in 0.5.0-integration) |

The pin `test_existing_protections_still_refuse` (mutation guard) is in `handoff.md`.

## Council finding 7: mutants now killed (fix round 1)

Each mutant applied to a scratch copy of `scripts/dev/lane_gate.py` at `311fec1` (`mutants.py` in the implementer's
scratchpad), then only the named test run. Every one fails with the mutant and passes without it.

| Mutant | Killing test | Result |
|---|---|---|
| (a) `_council_names_head` returns True for any ancestor | `tests/scripts/test_lane_gate.py::test_council_head_must_be_followed_only_by_lane_evidence` | killed: 1 failed: council naming the red commit accepted |
| (b) `if not names:` becomes `if names is None:` (empty Must-cover accepted) | `tests/scripts/test_lane_gate.py::test_lane_plan_without_must_cover_tests_is_refused` | killed: 1 failed (the empty-section case) |
| (c) bare names resolve among every test file at the head (`git ls-tree`) | `tests/scripts/test_lane_gate.py::test_bare_must_cover_name_resolves_only_in_the_lane_diff` | killed: 1 failed: `test_old` resolved outside the diff |
| (d) the `<lane id>:` owner filter off (`if owner:` becomes `if False:`) | `tests/scripts/test_lane_gate.py::test_multi_lane_plan_counts_only_the_lanes_own_paragraphs` | killed: 1 failed: `test_absent` from lane y counted |
| (e) `main`'s no-single-PLAN.md refusal off | `tests/scripts/test_lane_gate.py::test_main_refuses_a_real_lane_without_a_single_plan_index` | killed: 2 failed (0 and 2 PLAN.md) |
