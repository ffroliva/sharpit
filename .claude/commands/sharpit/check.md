---
description: Run the exact CI gate (ruff check, ruff format --check, pyright, pytest) plus sharpit's contract checklist. Run before every commit.
---

# `/sharpit:check`

**Read `skills/check/SKILL.md` and follow its protocol now**, passing `$ARGUMENTS` as given.

> Do **not** call `Skill(skill="check")`: the repo's `skills/*/SKILL.md` files are plain Markdown, not Skill-tool-invocable
> (only `.claude/commands/sharpit/*` are). Read the file directly.
