---
type: retrospective
date: 2026-11-07
tags: [sharpit, skills, workflow, docs-drift]
---

# Source over docs: three skill rules from two articles

## Outcome

PR #73 merged as `f7c72582`. It adds one rule to each of three workflow skills, taken from Thor Henning Hetland's
"Open Source Superpowers in the Agentic Era" (2026-10-21):

- `skills/predict/SKILL.md`: a persona's claim about BootUI, FastAPI or Starlette cites the line it read. BootUI is
  read from the reference checkout, after confirming it sits at the commit the latest
  `docs/reference/BOOTUI-CONTRACT-*-DRIFT.md` names. FastAPI and Starlette are read from `.venv`.
- `skills/scenario/SKILL.md`: a worst-case trace by hand through the current code before any code is written, as a
  section of the scenario artifact.
- `skills/doc-review/SKILL.md`: every behaviour claim names the test that pins it, or it is `untested`.

Before the change, `doc-review` checked claims against code but never against tests.

## Worked

- Baselining every failure on untouched `origin/main` before acting. The full suite had 7 failures on a docs-only
  branch. Six passed on `--lf`. `test_request_overhead_budget` passed alone on both branch and base. `test_red_check.py`
  failed on the base too, on a different case. All seven were load, not the change.
- Running the council inline for a 20-line docs diff instead of spawning reviewers: one real Low finding (confirm the
  checkout commit), fixed before merge.

## Didn't work

| What | Root cause | Mechanism now in place |
|---|---|---|
| The full suite ran while a base-worktree suite ran in parallel, and the overhead budget failed | Two suites competed for the cores | AGENTS.md "Tests run in parallel": check the load first; overhead budgets run alone with `-n 0` and the reason reported |
| Single-file pytest runs without `-n` | Habit | The same AGENTS.md rule: every run passes `-n` |
| The summary called the repo's rules "CLAUDE.md" (the article's wording) | The article's wording was copied | `CLAUDE.md` already points to `AGENTS.md`. An auto-memory note records the correction |
| `gh pr merge --match-head-commit` with a short SHA failed | GitHub requires the full object id | None needed. Pass `$(git rev-parse HEAD)` |

## Rulings

- Owner: merge PR #73 after the one-clause fix (2026-11-07). The merge was authorised for this PR only.

## Open

- The three new rules are prose. The second article, "Production Scars Are Architecture" (2026-06-23), argues that prose
  fails under task pressure. A mechanical check is the follow-up: for example, `/sharpit:check` fails when a scenario
  file lacks `## Worst-case trace`.
- A per-task retry limit that stops for the owner after N failed rounds (masking took six).
- The real-use test: run the edited `scenario` on the next masking or guard task.
- A Dependabot alert is open on the repo (`security/dependabot/1`). Not looked at.
