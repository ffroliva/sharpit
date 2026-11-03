# Findings: lane F5-gate (gated as `F`)

Each row is a rule the 0.5.0 gate lacked; the red test proves the old gate accepted (or mis-read) it.

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| release hard-coded to 0.4.0 | `tests/scripts/test_lane_gate.py::test_lane_gate_release_is_a_parameter` | `9512fbf2bb9d67f622d02dee67e39786377cabad` | evidence read from 0.4.0 under `release="0.5.0"` | Fixed in 1abf414 |
| reviewer-owned paths only for 0.4.0 | `tests/scripts/test_lane_gate.py::test_reviewer_owned_paths_follow_release` | `9512fbf2bb9d67f622d02dee67e39786377cabad` | a 0.5.0 `review.md` in the lane diff accepted | Fixed in 1abf414 |
| unresolvable release not refused | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_unresolvable_release` | `32c16040231d6a955d06be130491c023c6ea555f` | detached integration HEAD accepted | Fixed in 1abf414 |
| protected files by `lane == "F"` only | `tests/scripts/test_lane_gate.py::test_protected_allowed_per_lane` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | no `PROTECTED_ALLOWED` table | Fixed in afc74ec |
| dependency lists by `F` only | `tests/scripts/test_lane_gate.py::test_dependency_change_allowed_per_lane` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | F5a-harness refused | Fixed in afc74ec |
| baseline re-key by `F` only | `tests/scripts/test_lane_gate.py::test_baseline_rekey_only_for_foundation_lanes` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | F5a-core re-key refused | Fixed in afc74ec |
| leased check by bare name, A-postgresql only | `tests/scripts/test_lane_gate.py::test_leased_check_uses_full_node_ids` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | no `LEASED` mapping | Fixed in afc74ec |
| no council check | `tests/scripts/test_lane_gate.py::test_council_required_read_per_lane_from_plan_table` | `5fe96709b191d87ab35bf800ebbd21466506b228` | missing `council.md` accepted | Fixed in 4f348db |
| shallow council accepted | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_shallow_council_file` | `5fe96709b191d87ab35bf800ebbd21466506b228` | no verdict / one family / no SHA accepted | Fixed in 4f348db |
| no must-cover check | `tests/scripts/test_lane_gate.py::test_must_cover_uses_full_node_ids_and_refuses_skips` | `5fe96709b191d87ab35bf800ebbd21466506b228` | absent must-cover test accepted | Fixed in 4f348db |
| pin and N/A findings rows refused | `tests/scripts/test_lane_gate.py::test_findings_accept_pin_and_na_rows` | `4a4b4c81c5624af92ab1a9502dab8224711f194a` | `pin:` row reported unresolved | Fixed in 57903d5 |
| council.md not written | | | codex out of quota until 2026-11-04 15:41 | Parked: the coordinator runs the three-family council and checks it by hand (lane plan) |

The pin `test_existing_protections_still_refuse` (mutation guard) is in `handoff.md`.
