---
name: llm-council
version: "1.0"
description: >
  Use for high-stakes sharpit changes (activation, guard, masking, OSV handling, a release) where one model family's
  blind spots matter: runs pr-council-review, then gets independent reviews from other model families and reconciles.
---

# `llm-council`: cross-model review

## 1. Tier

| Tier | When | Reviewers |
|---|---|---|
| small | Docs, tests only | Claude council only (this is just `pr-council-review`) |
| medium (default) | Product code outside the safety core | Claude council + Codex |
| high | `engine/activation.py`, `engine/guard.py`, `engine/masking.py`, settings parsing, a release | Claude council + Codex + Antigravity |

## 2. Claude council

Run `skills/pr-council-review/SKILL.md` (PR or branch mode). Keep its findings table.

## 3. External reviewers

Model configuration and the exact headless commands live in the `harness-delegation` skill
(`~/.agents/skills/harness-delegation/SKILL.md`): Codex uses `gpt-6-luna`; Antigravity uses `gemini-3.8-flash-*` only.
Launch each one in the background with a timeout and a log file.

Give each the same brief, and **not** the Claude findings (an anchored reviewer confirms instead of finding):

```
Review this diff of sharpit, a Python port of BootUI (a dev console for FastAPI apps).
Safety model: disabled unless explicitly or dev-server enabled; fails closed (404) when inactive; a guard chain
(headers, trusted source, Host allow-list, cross-site, token, panel access) protects every route; secrets are masked
before any output; GET routes and MCP tools must have no side effects.
Find bugs, fail-open paths, secret leaks, side effects and contract breaks. For each: severity, file:line, evidence.
Diff: <path to the saved diff>
```

## 4. Reconcile

Merge all findings into one table with a `found by` column. For every finding raised by one family only, verify it
yourself (§4 of pr-council-review) before keeping it. Disagreements on severity: take the higher, unless disproved.

## 5. Verdict

The pr-council-review verdict format, plus `Reviewers: claude, codex(<model>), agy(<model>)` and which external runs
failed or timed out ("not run", never silently dropped). Posting rules are pr-council-review's §6.

Ported from gflow-cli's `llm-council`; reviewer models follow the global harness-delegation configuration.
