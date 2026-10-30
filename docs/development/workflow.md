# Development workflow

How a change to sharpit goes from idea to release. Rules (worktrees, TDD, commits, no AI attribution, never push
`master` or publish) are in [AGENTS.md](../../AGENTS.md); this page is the order of the steps and when to use each.
Every `/sharpit:<name>` step is `skills/<name>/SKILL.md`, readable by any agent.

```
predict → scenario → plan → subagent-driven execution → check → review → release
                                    ↑ spike, optimize, live-verify, known-issues as needed
```

## 1. Decide: `/sharpit:predict`

Five personas (architect, security, contract parity, host-app compatibility, devil's advocate) give GO, CAUTION or
NO-GO with a confidence and the mitigations. Use it for any feature, any change to activation, the guard, masking or
settings, and any new dependency. Skip it for a bug fix under ~10 lines with a proven cause.

If a persona's answer depends on a fact nobody knows ("does Starlette 0.40 expose X?"), run **`/sharpit:spike`** first:
a time-boxed experiment that writes a verdict to `docs/superpowers/spikes/` and throws the code away.

## 2. Explore: `/sharpit:scenario`

Edge cases across sharpit's risk dimensions (safe mode, guard, masking, contract, introspection drift, side effects,
OSV, host integration, scale, MCP/CLI parity), ranked by severity. Critical and High rows become named tests in the
plan. Output: `docs/superpowers/plans/<date>-<slug>-scenario.md`.

## 3. Plan: `/sharpit:plan`

A task-by-task TDD plan at `docs/superpowers/plans/<date>-<slug>.md`, contract first, with `- [ ] **Step N:**` lines.
`/sharpit:status`, `/sharpit:next` and `/sharpit:active` read it through `scripts/dev/active_plan.py`.

## 4. Execute: subagent-driven

In a worktree from `origin/master`, one task at a time with `superpowers:subagent-driven-development`: a fresh subagent
per task, red test first, review between tasks. Before touching activation, the guard, masking, introspection or
OSV, read **`/sharpit:known-issues`**. Delegated agents get the background-command rule in their brief.

## 5. Gate: `/sharpit:check`

Before every commit: ruff fix and format, then the CI gate (ruff check, ruff format --check, pyright strict, pytest)
and the contract/safety checklist. If an endpoint, the guard, activation or the UI changed, also
**`/sharpit:live-verify`**: a sample FastAPI app with sharpit installed, hit for real, fail-closed rows included.

If the suite is slow or the pytest-speed check flags a file, **`/sharpit:optimize`** follows the pytest-speed protocol
(`pytest-speed.toml`): find the cost, pin it with a red test, fix it, prove it with a paired A/B. It never skips,
marks slow or weakens a test.

## 6. Review

| Step | When |
|---|---|
| `/sharpit:doc-review` | The branch changes anything a doc describes |
| `/sharpit:branch-review` | Before opening the PR: the council on the local branch (base `origin/master`) |
| `/sharpit:pr-council-review <N>` | On the open PR; posts only when asked |
| `/sharpit:llm-council` | Activation, guard, masking, settings parsing or a release: adds Codex and Antigravity |

The owner merges. Agents never merge.

## 7. Release: `/sharpit:release`

Only when the owner asks. `/sharpit:changelog` first, then a version bump in `src/sharpit/__init__.py`, the changelog,
a local `uv build` sanity check, and a high-tier council on a `chore/release-<version>` branch. It stops and prints the
push, tag and `uv publish` commands for the owner; it never runs them.

## Issues

`/sharpit:issue-assessment <N>` triages read-only (class, severity, reproduction, cause, size).
`/sharpit:issue-resolve <N>` fixes small ones end to end: worktree, red test, fix, gates, draft PR. Larger ones go
back to step 1.
