# T-suite-speed findings

Lane `lane/0.5.0-T-suite-speed`, protocol `skills/optimize` -> `~/.agents/skills/pytest-speed/SKILL.md` + `causes.md`.
Box: 22 logical cores, Windows 11, shared with other agents. Raw rows: `C:\t\speed\round2\mx`, `mx3`, `mx4`, `mxb`
(`matrix.jsonl`), `C:\t\speed\round2\ab2`.

## Result

| Run | Wall s | Summed s | Note |
|---|---|---|---|
| Baseline b3ded65, `-n auto` (22 workers), loaded box | 444 | 5503 | owner baseline |
| Base b3ded65, `-n 8`, quiet box | 275 | | 1 run |
| Lane + P2/P3, `-n 8`, quiet box | 169-178 | 1084-1167 | 3 runs, no failure: the reliable setting |
| Lane + P2/P3, `-n 12`, quiet box | 139-161 | 1333-1559 | 7 runs, 2 with a budget failure; best green 144 s |

The owner's ~2 min target is met at `-n 12` only on some runs, and not reliably: `-n 8` is 170-178 s. To reach 120 s
at `-n 8`, the summed time must fall from 1084 s to about 900 s. See "What stands between this and 2 minutes".

## Red table

| Test | Red SHA | Assertion | Disposition |
|---|---|---|---|
| tests/scripts/test_lane_gate.py::test_lane_gate_shares_reads_across_copies_of_a_repo | 9f5b4fa9c2ae1fe895d5c2b55ea309cf0cad8efb | `assert shows == []`: left contains 17 more items | Fixed in fe3c3f8295a76df364d544a9d28e00b0c3af736c |
| tests/scripts/test_lane_gate.py::test_lane_gate_reads_only_what_a_new_commit_changed | 9f5b4fa9c2ae1fe895d5c2b55ea309cf0cad8efb | `assert reads == [...]`: left contains 6 more items | Fixed in fe3c3f8295a76df364d544a9d28e00b0c3af736c |

`red_check.py` on 9f5b4fa: `RED (assertion under tests/)` for both.

## Superseded reds and pins

These went red by assertion at their commit, seen with `red_check.py`, but a later commit in this lane changed the test
or a helper it references, so the gate's replay cannot use them. Each has a mutation proof.

| Test | Historical SHA | Red output | Why superseded | Mutation proof |
|---|---|---|---|---|
| tests/test_patch_targets.py::test_uses_walks_each_source_file_once | fbb23b67bcbf0871cdad5906dd0cb79d2fb9c5d7 | `assert 380 == 190` | helper `uses` is the fix itself (9a9b4a8) | planted `from sharpit.engine.sqla import unavailable_reason` in `collectors/data.py`: `test_patch_targets_are_defined_where_called` FAILED (`C:\t\speed\mut-pt.txt`) |
| tests/scripts/test_lane_gate.py::test_lane_gate_reads_a_file_at_a_commit_once | a976f03d46f4ee400f89431352f200a5ab654678 | `assert 25 == 17` | P2 made it start from a cold cache | fe3c3f8's repo-free cache is what `test_lane_gate_shares_reads_across_copies_of_a_repo` pins; `C:\t\speed\mut-lg.txt`: `return []` on a protected path fails 18 of 27 `-k protected` |
| tests/scripts/test_lane_gate.py::test_lane_gate_prunes_only_a_replay_tree_it_could_not_remove | a976f03d46f4ee400f89431352f200a5ab654678 | `assert 'prune' not in [...]` | `def` line reformatted (122 columns failed ruff) | `_temp_tree` back to an unconditional prune: FAILED |
| tests/scripts/test_red_check.py::test_workers_share_one_verdicts_build | 1279712effe6a631fa3c600aaf3a12c0819fe179 | assertion in `_built_once` (red_check RED) | helper `_built_once` changed in 1b65374 | deleting `claim.unlink()`: `test_a_failed_verdicts_build_leaves_the_next_worker_to_build` FAILED (`C:\t\speed\round2\mut-rc-claim.txt`) |
| tests/scripts/test_red_check.py::test_a_waiter_retries_a_verdicts_file_windows_still_holds | 1b65374dcb427224083dc776a28f0165fb4a6516 | red_check RED (`C:\t\speed\round2\red-rc-perm.txt`) | helper `_built_once` changed | as above; defect found live at `-n 12` (`PermissionError`) |
| tests/scripts/test_lane_gate.py::test_lane_fixture_copy_leaves_the_objects_in_the_template | 48d00fb6aa64bd4ba619fbafd569791ba5e2eead | red_check RED (`C:\t\speed\round2\red-lg-objects.txt`) | helper `_fixture` changed | `_fixture` returning the template: `test_lane_fixture_commit_stays_in_its_own_copy` FAILED (`C:\t\speed\round2\mut-lg-copy.txt`) |
| tests/scripts/test_lane_gate.py::test_lane_gate_sha_read_in_one_repo_stays_absent_in_another | pin, passes at 9f5b4fa | n/a: a guard on the repo-free key | n/a | caching `_resolve` across repos: FAILED (`C:\t\speed\round2\mut-p2-resolve.txt`); making an absent path read as empty fails 5 tests (`mut-p3-absent.txt`) |

## Causes

| File | Measured cause | Id | Resolution |
|---|---|---|---|
| tests/test_patch_targets.py | `uses()` re-walked all 190 src trees per patch (5.4 M `_scoped` calls) | TS-001 shape | one index per file, 21 s -> 4 s summed |
| tests/scripts/test_lane_gate.py | git spawns are the test time: 8329 spawns, 3671 `git show` at `-n 8` | repeated immutable reads | object-id cache without the repo, a tree listing plus changed blobs (5087 spawns, 273 `ls-tree`, 312 blob reads); summed 1136 s -> 574 s |
| tests/scripts/test_red_check.py | module fixture `verdicts` (24 pytest subprocesses) rebuilt per xdist worker | TS-001 across workers | workers share one build through a claim file under the xdist basetemp; children 105 -> 33; summed 248 s -> 143 s |
| fixture copies | `shutil.copytree` of git objects per test; 27000 files left, 10000 read-only, 15-22 s end-of-run deletion | copied data | copies read objects through `alternates`; deletion ~9 s |
| tests/test_safety_matrix.py | `install()` scan, `gc.get_referrers` per live connection (PS-007) | PS-007 | not touched: `src/`, owner decision |

The 444 s baseline was mostly contention: a matrix row costs 0.33-0.46 s alone and averaged 3.0 s in the baseline.

## Paired A/B

`-n 8`, three interleaved rounds, summed seconds, `C:\t\speed\round2\ab2`, d459bcd + P2/P3 vs base b3ded65. Every change
round beat every base round.

| File | Base median | Change median |
|---|---|---|
| tests/scripts/test_lane_gate.py | 1136 | 574 |
| tests/scripts/test_red_check.py | 248 | 143 |
| tests/test_patch_targets.py | 21 | 4 |

## Worker count (`--dist load`)

| -n | Wall s | Busy sum s | Runs with a budget failure |
|---|---|---|---|
| 8 | 169-178 | 1084-1167 | 0 of 3 |
| 10 | 160-193 | 1206-1448 | 0 of 4 |
| 12 | 139-161 | 1333-1559 | 2 of 7 |
| 14 | 151-154 | 1408-1430 | 1 of 2 |
| 16 | 159-194 | 1438-1933 | 1 of 2 |
| 22 | 156-172 | 1946-2075 | 2 of 2 |

Base at `--dist load`: `-n 8` 275 s, `-n 12` 220 and 248 s, no budget failures in 3 runs. So the failures at `-n 12` are
not shown to be noise; they may mean the faster suite gives budgets less headroom at that density.
`--dist worksteal` at `-n 8`: 190 and 176 s, no gain. Busy time grows with workers; the box has 6 P and 10 E cores,
the likely reason, but placement was not measured.

## What stands between this and 2 minutes

870 `git worktree`, 1337 `rev-parse` and 360 `commit` spawns in `test_lane_gate`; ~180 s in `test_safety_matrix` (PS-007,
`src/`); real pytest subprocess work in the plugin files, which is the code under test. `xdist_group` + `--dist loadgroup`
would free the slots `red_check` waiters hold: not measured, needs protected config.

`tests/test_durations.json` not refreshed: CI shards read `tests/shard_weights.json` from CI JUnit, the pytest-speed
baseline is not used for sharding, and a refresh needs a CI or fleet source (no CI run on a local branch).

Not checked: TS-004, TS-005 past the top six files; base `-n 12` has only 2 runs.
