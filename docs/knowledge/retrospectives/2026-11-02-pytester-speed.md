---
type: retrospective
date: 2026-11-02
tags: [sharpit, pytest, speed, isolation]
---

# Pytester subprocess cost and isolation

## Outcome

The `fix/0.4.0-speed-pytester-inprocess` worktree classified 73 existing subprocess call sites. It moved 24 to in-process execution and retained 49 for process-bound assertions. The final full suite passed: 4,381 passed, 9 skipped. Nothing was pushed.

## Worked

- A per-file call-site ceiling catches future subprocess growth without timing thresholds.
- Four-round interleaved A/B on Windows showed gains above noise in every changed behavior file. `pytest-speed check` flagged no files.
- Fixture profiling found `pytester` setup below 9ms; one session setup per worker. The repeated child pytest launches were the recurring cost.

## Didn't work, root cause, and mechanism

- Converting every call made the isolated plugin suite pass but caused 12 full-suite failures. Other outer test modules were already in `sys.modules`, including sqlite connection aliases and async drivers; nested in-process sessions treated them as application state and became `unknown`. All 12 nodes passed on the untouched base. The calls asserting a clean environment now stay subprocess-based, and the full suite runs before completion.
- SQLAlchemy nested runs can unload/reload Cython-backed modules through `Pytester.inline_run`, producing `InternalTraversal` errors. The five SQLAlchemy behavior cases and the live-engine driver case stay subprocess-based.
- The first A/B trial overlapped diagnosis and edits, so its measurements were discarded. The final measurements used four interleaved rounds after the code was stable.

## Rulings

- Process-bound cases include xdist topology/crashes, entry-point import behavior, `sys.monitoring` IDs, `sitecustomize`, clean module/environment state, and SQLAlchemy Cython state.
- `Pytester.inline_run` restores modules added during the run, not unrelated modules loaded before it starts.

## Open

- Lowest-direct and no-SQLAlchemy special jobs were not run; no PR is being opened and no dependency or plugin was added.
- The branch remains local and unmerged per the no-push instruction.
