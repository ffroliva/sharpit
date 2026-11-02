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

One row per red test, with the full pytest node id (`tests/...py::name`, or `::Class::name`). `Red SHA` is the `test:`
commit where the test fails against a wrong-value stub. What `scripts/dev/lane_gate.py` checks for each row:

- The red SHA is a lane commit (not on the integration branch) and an ancestor of the head. The test is added or
  changed by the lane: a test that already exists on the integration branch is not a red. List it under "Not a red".
- At the red SHA the test fails with an `AssertionError` (or pytest's `Failed: DID NOT RAISE` from the test file).
  The failing frame may be the test or a shared test helper, never `src/` or an installed package. It must pass at
  the head. An `<error>`, a skip, another exception or a pass refuses.
- After the red commit, the test function itself (body, signature, decorators and marks) must not change. Neither may
  any top-level name it uses in its file (constants, helpers, fixtures, imports, and class attributes for a method).
  A new definition that shadows one of them counts as a change. A fixture it requests in a `conftest.py` on its path
  must not change either. Added imports, new functions, classes, constants and new test methods are fine, and so are
  edits to code the test does not use.
- Every row that names a test needs a Red SHA, unless its Disposition is `Parked: <reason>`. Tables that are not red
  tables (history, superseded, not-a-red) must not have a column header containing `Red SHA`.
- Non-pytest reds (Vitest) go in a separate table under a heading containing `UI` or `manual`. They are reported
  `unverified` and need `--accept-unverified`. A non-pytest id anywhere else refuses.
- The reviewer, not the gate, checks that the red commit subject starts with `test:`, and that a review-finding red
  records the parent of its fix commit.

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/path/test_x.py::test_name` | `<full sha>` | `assert <the assertion that names the defect>` |

## Evidence (C2)

- `findings.md`: table with `Finding | Test | Red SHA | Assertion message | Disposition`; every `Disposition` starts
  with `Fixed` (and the row names its test) or `Parked: <reason>`. A findings file with rows but no table with a
  `Disposition` column refuses.
- `field-map.md`: the panel field map, or `N/A — not a panel lane`.
- `checklist.md`: spec §6.1 items 1–10 in order, one table row each (`| 1 | ... | <evidence> |`), each with a
  backticked evidence path that exists, or `N/A — <reason>`.
- Never in the lane diff: `review.md`, `gate/`, `live-verify.md` (the coordinator writes them in the integration
  worktree). Also refused unless the coordinator passes `--allow-path <path>`: `scripts/dev/lane_gate.py`,
  `sonar-baseline.txt`, `tests/engine/test_import_boundary.py`, `uv.lock`, `tests/overhead.py`,
  `tests/test_code_shape.py`, `tests/conftest.py`, `conftest.py`, dependency lists and the `[tool.ruff]`,
  `[tool.pyright]`, `[tool.pytest]`, `[tool.uv]` sections of `pyproject.toml`, a raised or added complexity-baseline
  entry, and any edit to an overhead test module other than added test functions.
