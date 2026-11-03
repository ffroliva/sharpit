# Lane F5-gate (gated as lane id `F`): the merge gate learns 0.5.0

Implementer: claude-flavio-opus

Branch `lane/0.5.0-F5-gate` from `release/0.5.0` @ `bf2fc42`. Plan:
`0.5.0-plan/docs/superpowers/plans/2026-11-03-sharpit-0.5.0/F5-gate.md` (r4); spec 2026-11-03 §4.0.

## Status

DONE_WITH_CONCERNS: all four tasks done (red, then fix, each); the 12 must-cover tests exist and pass. Concern:
`council.md` is not written. The lane plan makes the council required and checked by hand by the coordinator; codex
(one of the three council families) is out of quota until 2026-11-04 15:41, and a one-family council is not one.

## Coordinator command from now on

Gate this lane with today's gate (from `release/0.5.0`, in the integration worktree):

```bash
uv run python scripts/dev/lane_gate.py F --worktree C:\development\github\sharpit-wt\0.5.0-F5-gate
```

After it merges, every 0.5.0 lane:

```bash
uv run python scripts/dev/lane_gate.py <lane id> --release 0.5.0 --worktree C:\development\github\sharpit-wt\0.5.0-<lane> \
    --plan-index C:\development\github\sharpit-wt\0.5.0-plan\docs\superpowers\plans\2026-11-03-sharpit-0.5.0\PLAN.md
```

`--plan-index` is needed until the 0.5.0 plan commits are on `release/0.5.0` (they are not at `bf2fc42`); after that
the gate finds `docs/superpowers/plans/*-sharpit-0.5.0/PLAN.md` itself. A non-fixture lane without a single PLAN.md is
refused.

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/scripts/test_lane_gate.py::test_lane_gate_release_is_a_parameter` | `9512fbf2bb9d67f622d02dee67e39786377cabad` | `assert _refused(..., "missing evidence: handoff.md (at .superpowers/sdd/0.5.0/lanes/")` |
| `tests/scripts/test_lane_gate.py::test_reviewer_owned_paths_follow_release` | `9512fbf2bb9d67f622d02dee67e39786377cabad` | `assert _refused(..., "reviewer-owned path changed: .superpowers/sdd/0.5.0/lanes/X/...")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_unresolvable_release` | `32c16040231d6a955d06be130491c023c6ea555f` | `assert _refused(fx.evaluate(), "cannot resolve the release")` |
| `tests/scripts/test_lane_gate.py::test_protected_allowed_per_lane` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | `assert table == PROTECTED_ALLOWED_05` |
| `tests/scripts/test_lane_gate.py::test_dependency_change_allowed_per_lane` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | `AssertionError: F5a-harness` (dependency list refused) |
| `tests/scripts/test_lane_gate.py::test_baseline_rekey_only_for_foundation_lanes` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | `assert ['complexity baseline entry added: ...'] == []` |
| `tests/scripts/test_lane_gate.py::test_leased_check_uses_full_node_ids` | `e6390d0e6c13415944758ba9e9dfbb2362e760f4` | `assert {} == LEASED_05` |
| `tests/scripts/test_lane_gate.py::test_council_required_read_per_lane_from_plan_table` | `5fe96709b191d87ab35bf800ebbd21466506b228` | `assert _refused(fx.evaluate(plan_index=plan), "council.md")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_shallow_council_file` | `5fe96709b191d87ab35bf800ebbd21466506b228` | `assert _refused(fx.evaluate(plan_index=plan), "council.md: ")` |
| `tests/scripts/test_lane_gate.py::test_must_cover_uses_full_node_ids_and_refuses_skips` | `5fe96709b191d87ab35bf800ebbd21466506b228` | `assert _refused(..., "must-cover test_absent: not defined")` |
| `tests/scripts/test_lane_gate.py::test_findings_accept_pin_and_na_rows` | `4a4b4c81c5624af92ab1a9502dab8224711f194a` | `assert ['findings.md: unresolved finding: ...'] == []` |

Each was `RED (assertion under tests/)` by `scripts/dev/red_check.py` before its `test:` commit.

### Superseded

| Test id | Historical SHA | Why |
|---|---|---|
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_unresolvable_release` | `9512fbf2bb9d67f622d02dee67e39786377cabad` | its second half created `release/0.4.0` while the fixture's `release` branch existed (git refuses the ref); re-red at `32c1604` with the branch deleted first, before any fix was committed |

## Pin (passes on first run, never a red)

| Test | Mutation | Failed on |
|---|---|---|
| `tests/scripts/test_lane_gate.py::test_existing_protections_still_refuse` | `_path_refusals`: the PROTECTED check replaced by `if False:` (scratch copy) | the three `protected path changed: uv.lock / tests/conftest.py / sonar-baseline.txt` cases |

## Commits

| Task | Red | Fix |
|---|---|---|
| 1 release, reviewer-owned | `9512fbf`, `32c1604` | `1abf414` |
| 2 protected/dependency/baseline/leased | `e6390d0` | `afc74ec` |
| 3 council, must-cover | `5fe9670` | `4f348db` |
| 4 findings pin/N-A (+ pin test, workflow.md) | `4a4b4c8` | `57903d5` |
| complexity ratchet (see below) | caught by the existing `tests/test_code_shape.py::test_complexity_only_goes_down` | `7e68a1d` |

## Decisions (nobody to ask; recorded here)

1. **Evidence location.** The brief said `.superpowers/sdd/0.5.0/lanes/F5-gate/`; the lane plan and PLAN.md say
   `.superpowers/sdd/0.4.0/lanes/F/` because today's gate reads lane `F` there. The plan wins (the gate would refuse
   otherwise, and May-touch lists only this folder).
2. **Release fallback.** The existing `test_lane_gate_main_exits_zero_only_when_accepted` runs `main` with an
   integration branch named `release` and no `--release`, and must keep passing unchanged. So the chain is
   `--release` → branch `release/<x>` → the only `.superpowers/sdd/<x>/lanes` folder in the integration worktree → refuse.
   Never a hard-coded default; the real integration worktree holds both 0.4.0 and 0.5.0, so it refuses there. The
   resolution is printed as a note.
3. **Reviewer-owned paths** are refused for every release folder, not only the current one (stricter than "follow the
   release", never looser).
4. **`[tool.*]` gate config** stays refused for every lane, `F` included: today's gate refuses it for `F` too, and the
   plan's "F only" would have loosened it. `--allow-path` remains the escape hatch, as today.
5. **A-postgresql leased entry** keeps 0.4.0's bare names matched as `::<name>` (the existing
   `test_lane_gate_accepts_postgresql_with_leased_db_log` uses `tests/engine/test_pg.py::...`). Every new lane uses
   full node ids, matched exactly (`(^|\s)<id>\s+PASSED`).
6. **Council file** must say `VERDICT: APPROVE` (APPROVE WITH NITS counts); BLOCK/REQUEST CHANGES are refused. Families
   by name: anthropic (claude/opus/sonnet/haiku/fable), openai (codex/gpt), google (gemini/agy/argon). `council.md`
   is committed in the lane, so it cannot name its own commit: a named SHA counts when it is an ancestor of the head
   and only the lane's evidence folder changed after it.
7. **Must-cover run** reads skip reasons from the replay's junit (`<skipped message=...>`), the same runner as the red
   replay, instead of `-rs` text. Must-cover only runs when PLAN.md is known (`Options.plan_index`); `main` requires
   it for non-fixture lanes. A lane plan whose section lists no test (today: `G0-goldens.md`) is refused; use `--plan`.
8. **Multi-lane plan files**: a paragraph counts as a lane's when it starts `<lane id>:` with an id from the Lanes
   table; when any paragraph does, only the lane's own paragraphs count.

## Gates

- First full suite at `57903d5`: 1 failed (`tests/test_code_shape.py::test_complexity_only_goes_down`: `evaluate`
  was C901 15 > 10 after Tasks 1-3), 4492 passed, 9 skipped. Fixed by splitting `evaluate` (`7e68a1d`); the pinned
  number was not raised. The existing ratchet test was the red; no new test needed.
- At `7e68a1d`: `tests/scripts` + `tests/test_code_shape.py` 197 passed. Final full suite, ruff, format, pyright: in
  the final report (logs under `0.5.0-integration/.superpowers/sdd/0.5.0/logs/F5-gate-*.log`).

## How to resume

Nothing open in code. Next: the coordinator runs the council (Opus + codex + agy Argon) and commits `council.md`
here, a reviewer writes `review.md`, then today's gate as above.
