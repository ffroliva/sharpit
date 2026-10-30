---
description: Make sharpit's test suite faster with the pytest-speed protocol (measure, find the cause, red test, fix, paired A/B), never by skipping or weakening a test.
---

# `/sharpit:optimize [test file or flagged report]`

**Read `skills/optimize/SKILL.md` and follow it now**, passing `$ARGUMENTS` as given. It points at the standalone
pytest-speed skill (`~/.agents/skills/pytest-speed/SKILL.md`) and gives sharpit's config: `pytest-speed.toml`,
module `scripts.pytest_speed`.

> Do **not** call `Skill(skill="optimize")`: the repo's `skills/*/SKILL.md` files are plain Markdown, not Skill-tool-invocable
> (only `.claude/commands/sharpit/*` are). Read the file directly.
