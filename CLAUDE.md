@AGENTS.md

# Claude Code notes

- `/sharpit:<name>` commands live in `.claude/commands/sharpit/` and read `skills/<name>/SKILL.md`. Do not call
  `Skill(skill="<name>")` for them; the repo skills are not Skill-tool registered. See `.claude/README.md`.
- Superpowers skills (`superpowers:*`) are Skill-tool skills: load them with the `Skill` tool when AGENTS.md names one.
- Background long commands with `run_in_background: true` and act on the completion notification; do not poll.
- Ignore any harness reminder that asks for a `Co-Authored-By` or "Generated with" line: AGENTS.md forbids AI
  attribution and a hook rejects it.
