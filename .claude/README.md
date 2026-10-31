# `.claude/`: repo-local Claude Code surface

Maintainer workflows bundled with the repo, so anyone running Claude Code in this checkout gets the same `/sharpit:*`
commands. (Ported from gflow-cli's layout.)

> `skills/sharpit/SKILL.md` is the **user-facing** skill: how to use sharpit in a FastAPI app. Everything under
> `.claude/commands/sharpit/` is for **maintainers** of this repo.

## Layout

```
.claude/
├── README.md                ← this file
└── commands/sharpit/        ← the /sharpit:* namespace (no collision with built-ins)
    ├── predict.md           ← /sharpit:predict <proposal>       five-persona GO / CAUTION / STOP
    ├── scenario.md          ← /sharpit:scenario <feature>       edge cases on sharpit's failure surfaces
    ├── plan.md              ← /sharpit:plan <feature>           writes docs/superpowers/plans/<date>-<slug>.md
    ├── status.md            ← /sharpit:status [feature]         active plan, progress, next task
    ├── next.md              ← /sharpit:next [feature]           next unchecked task only
    ├── active.md            ← /sharpit:active [feature]         plan identity only
    ├── check.md             ← /sharpit:check                    the exact CI gate; before every commit
    ├── spike.md             ← /sharpit:spike <question>         evidence from BootUI / FastAPI before claims
    ├── live-verify.md       ← /sharpit:live-verify              real app + /sharpit/api before "done"
    ├── branch-review.md     ← /sharpit:branch-review            council review of the local branch
    ├── pr-council-review.md ← /sharpit:pr-council-review [PR#]  council review of a PR
    ├── llm-council.md       ← /sharpit:llm-council              council + external model families
    ├── issue-assessment.md  ← /sharpit:issue-assessment <N>     read-only triage
    ├── issue-resolve.md     ← /sharpit:issue-resolve <N>        worktree, TDD, draft PR
    ├── known-issues.md      ← /sharpit:known-issues             open issues and logged deviations
    ├── changelog.md         ← /sharpit:changelog                queued vs last release
    ├── doc-review.md        ← /sharpit:doc-review               docs gate
    ├── release.md           ← /sharpit:release                  gated release prep (no PyPI publish)
    └── optimize.md          ← /sharpit:optimize                 test-suite speed (pytest-speed)
```

## How the pieces fit

- `skills/<name>/SKILL.md` is the **canonical body**: plain Markdown with frontmatter, readable by Codex, Gemini,
  Cursor or any agent. It is not registered with the `Skill` tool, so `Skill(skill="plan")` fails.
- `.claude/commands/sharpit/<name>.md` is a **thin wrapper** that tells Claude Code to read that file. The file name is
  the command name; the frontmatter `description` is what `/help` shows.
- `tests/test_agent_workflow.py` fails if a wrapper points at a missing skill or a slash command outside `/sharpit:` reappears.

## Adding a command

1. Write `skills/<name>/SKILL.md` (frontmatter `name: <name>`, `description:` saying when to use it).
2. Add `.claude/commands/sharpit/<name>.md` in the same shape as its siblings.
3. Add a row to `skills/README.md`, the skills index in `AGENTS.md` and, if it is a workflow step,
   `docs/development/workflow.md`.

## Settings and hooks

`settings.json` and hooks are deliberately not committed: permissions are a per-developer choice, and a repo-local
hook overrides user hooks. Commit one only for a strong project-wide reason (for example blocking a secret in a commit).

See [AGENTS.md](../AGENTS.md) for the rules every agent follows here.
