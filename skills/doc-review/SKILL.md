---
name: doc-review
version: "1.0"
description: >
  Use before merging any sharpit change that touches user-visible behaviour, settings, the API or the agent workflow:
  checks that README, skills/sharpit/SKILL.md, the spec, AGENTS.md and docs/ still tell the truth.
---

# `doc-review`: documentation gate

Docs lie quietly. This gate compares what the docs claim against what the branch does.

## 1. Scope the diff

```bash
git diff --name-only master...HEAD
```

Map changed code to the docs that describe it:

| Code changed | Docs to check |
|---|---|
| `src/sharpit/settings.py`, `panels.py` | README settings table, `skills/sharpit/SKILL.md` settings table, spec §7 |
| `src/sharpit/engine/activation.py`, `guard.py` | README safety section, `skills/sharpit/SKILL.md` safety model, AGENTS.md safety summary |
| `src/sharpit/engine/masking.py` | Same as above, plus the contract's masking § |
| `src/sharpit/fastapi/adapter.py` (routes) | `skills/sharpit/SKILL.md` panels/API list; `docs/reference/BOOTUI-CONTRACT-MVP.md` if a shape moved |
| MCP / CLI tools | `skills/sharpit/SKILL.md` MCP section |
| `pyproject.toml` (deps, version, Python floor) | README install and requirements |
| `skills/`, `.claude/commands/`, `scripts/dev/` | `skills/README.md`, `.claude/README.md`, AGENTS.md skills index, `docs/development/workflow.md` |
| Any deliberate BootUI difference | Spec §14 deviation log |

## 2. Check each claim

For every doc in scope: every env var named exists in `settings.py`; every route named is mounted; every default stated
matches the code; every command shown runs. Run the commands you can (`uv run python -c "import sharpit; ..."`).
Flag invented APIs: sharpit is a pre-release MVP and docs must not describe panels that are not built yet as working.

## 3. Check links

Relative links in changed Markdown files resolve to files that exist. No slash command outside the `/sharpit:` namespace, no base branch other than
`master` (sharpit's default branch).

## Output

A table `doc | claim | status (ok / stale / wrong / missing) | fix`. Fix stale docs on the same branch. A missing doc
for a user-visible change is a blocker for `/sharpit:pr-council-review`.

Ported from gflow-cli's doc-review gate, rewritten around sharpit's settings, routes and safety docs.
