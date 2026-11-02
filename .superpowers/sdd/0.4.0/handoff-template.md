# Lane <lane-id> handoff

Copy to `.superpowers/sdd/0.4.0/lanes/<lane-id>/handoff.md` in the lane worktree, keep it current after every task,
and commit it with `git add -f` (`.superpowers/` is gitignored). `scripts/dev/lane_gate.py` reads it at the lane head.

Implementer: <agentctl id, e.g. codex-sharpit-A-data>
Lane plan: `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/<lane plan>.md`
Branch / worktree: `lane/0.4.0-<lane-id>` in `C:\development\github\sharpit-wt\0.4.0-<lane-id>`

## Status

- Done: <tasks finished, with their fix commit SHAs>
- Next step: <the exact next action>
- Last green command: <command and its summary line>
- Open findings: <none | see findings.md rows not yet fixed or parked>

## How to resume

<what another worker needs to continue from here: branch state, WIP commits, background jobs to re-run>

## Decisions

<each decision taken without the owner, with the spec/plan section it relies on>

## Red tests

One row per red test. `Red SHA` is the `test:` commit where the test fails with an `AssertionError` against a
wrong-value stub. The gate replays each row at that SHA and at the head, and refuses if the red SHA is not a lane commit
that is an ancestor of the head, or if the test's function body changed after the red commit. Non-pytest rows (for
example Vitest) are reported `unverified` and need `--accept-unverified`.

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/path/test_x.py::test_name` | `<full sha>` | `assert <the assertion that names the defect>` |

## Evidence (C2)

- `findings.md`: table with `Finding | Test | Red SHA | Assertion message | Disposition`; every `Disposition` starts
  with `Fixed` (and the row names its test) or `Parked: <reason>`.
- `field-map.md`: the panel field map, or `N/A — not a panel lane`.
- `checklist.md`: spec §6.1 items 1–10 in order, one table row each (`| 1 | ... | <evidence> |`), each with a
  backticked evidence path that exists, or `N/A — <reason>`.
- Never in the lane diff: `review.md`, `gate/`, `live-verify.md` (the coordinator writes them in the integration
  worktree).
