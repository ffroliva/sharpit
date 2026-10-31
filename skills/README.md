# sharpit skills

Each `skills/<name>/SKILL.md` is a plain-Markdown workflow any agent can read (Claude Code, Codex, Gemini,
Antigravity, Cursor). Claude Code reaches them through the thin wrappers in `.claude/commands/sharpit/`, so
`/sharpit:<name>` reads `skills/<name>/SKILL.md`. The skills are **not** registered with the `Skill` tool.

`tests/test_agent_workflow.py` checks that every command points at an existing skill, that each skill's frontmatter
`name` matches its directory, and that no command of the project this workflow was ported from survives.

## The chain

```
predict → scenario → plan → (subagent-driven execution, one task at a time) → check → branch-review / pr-council-review → release
```

The full guide, with when to use each step, is [docs/development/workflow.md](../docs/development/workflow.md).

## Index

| Skill | Command | What it does |
|---|---|---|
| `sharpit` | (none: user-facing) | How to install, configure and use sharpit. Labelled pre-release. |
| `predict` | `/sharpit:predict` | Five-persona go/no-go on a proposed change |
| `scenario` | `/sharpit:scenario` | Edge cases across sharpit's ten risk dimensions, before planning |
| `plan` | `/sharpit:plan` | Task-by-task TDD plan in `docs/superpowers/plans/` |
| `status` | `/sharpit:status`, `/sharpit:next`, `/sharpit:active` | Active plan state, via `scripts/dev/active_plan.py` |
| `check` | `/sharpit:check` | Auto-fix, then the CI gate and the contract/safety checklist |
| `changelog` | `/sharpit:changelog` | What is queued since the last release (git fallback) |
| `known-issues` | `/sharpit:known-issues` | Open issues and the spec's deviation log |
| `doc-review` | `/sharpit:doc-review` | Docs still tell the truth about the branch |
| `issue-assessment` | `/sharpit:issue-assessment` | Read-only triage of a GitHub issue |
| `issue-resolve` | `/sharpit:issue-resolve` | Worktree, red test, fix, gates, draft PR |
| `pr-council-review` | `/sharpit:pr-council-review`, `/sharpit:branch-review` | Specialist council review (PR or local branch mode) |
| `llm-council` | `/sharpit:llm-council` | The council plus Codex / Antigravity reviewers |
| `spike` | `/sharpit:spike` | Time-boxed experiment with a written verdict |
| `live-verify` | `/sharpit:live-verify` | Run a sample FastAPI app with sharpit and hit `/sharpit/api` |
| `optimize` | `/sharpit:optimize` | Test-suite speed: a pointer to the pytest-speed skill and `pytest-speed.toml` |
| `release` | `/sharpit:release` | Gated release prep; never publishes to PyPI without the owner |

## Provenance: ported, adapted, dropped

The workflow was ported from gflow-cli and rewritten for sharpit's failure surfaces: safe mode failing closed, the
activation and access guard, secret masking, BootUI contract parity, FastAPI/Starlette introspection drift, no side
effects on GET or MCP, and OSV network failures.

| Source skill | Here | Why |
|---|---|---|
| predict, scenario, plan, status, check, changelog, known-issues, doc-review, issue-assessment, issue-resolve, pr-council-review, llm-council, spike, release | Ported and rewritten | Same role; sharpit's personas, risk dimensions, gates and branch (`main`) |
| live-verify | Adapted | The original drove a browser against a remote service; here it installs sharpit in a sample FastAPI app and hits `/sharpit/api` |
| optimize | New pointer | Means test-suite speed: points at the standalone pytest-speed skill, vendored in `scripts/pytest_speed/` |
| gflow-cli (user-facing skill) | Dropped, replaced by `sharpit` | Described the other project's CLI |
| video-production | Dropped | Video generation workflow; nothing to do with a dev console |
| sonar | Dropped | sharpit has no SonarQube project; ruff, pyright strict and the council cover it |
| skillopt (skill-optimisation loop) | Not ported | `/sharpit:optimize` was redefined as pytest-speed; no skill-tuning harness is needed yet |

Files the source skills read that sharpit does not have yet (`CHANGELOG.md`, `KNOWN_ISSUES.md`): the skills fall back to
git history and the design spec §14/§15 and offer to bootstrap the file, instead of creating it unasked.
