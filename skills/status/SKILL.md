---
name: status
version: "1.0"
description: >
  Use to answer "where are we?" in sharpit: shows the active implementation plan at three levels of detail. status =
  full state, next = next unchecked task only, active = plan identity only. All run scripts/dev/active_plan.py.
---

# `status`: plan state reader

All three variants run the same script and filter its output:

```bash
uv run python scripts/dev/active_plan.py                 # newest dated plan that still has open steps
uv run python scripts/dev/active_plan.py --feature <slug> # a specific plan
```

Plans are `docs/superpowers/plans/YYYY-MM-DD-<slug>.md` (a `<date>-<slug>/PLAN.md` directory also works). The newest is
chosen by the date in the file name, never by mtime (a checkout resets every mtime). `*-scenario.md` notes are skipped.
Exit code 1 with a message means no plan matched.

## Variants

**`status [feature]`**: return the script output verbatim: plan path, title, goal, progress, and the
`--- Next task ---` block. Use at session start, after finishing a task, and before adding scope.

**`next [feature]`**: return only what follows `--- Next task ---`. If the output says "All steps complete", say so and
suggest `/sharpit:changelog` and, when the owner wants one, `/sharpit:release`.

**`active [feature]`**: return only the header lines (stop before `--- Next task ---`). Use before `/sharpit:predict` or
`/sharpit:scenario` to check the proposal fits the current scope.

## Feature slug

Use the slug passed in, else one named earlier in the conversation, else run without `--feature`.

Ported from gflow-cli's `status` skill (sharpit has no root `PLAN.md`; the newest dated plan is the default).
