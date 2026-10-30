---
name: plan
version: "1.0"
description: >
  Use after /sharpit:predict returns GO or CAUTION (and /sharpit:scenario has run) to turn a sharpit feature into a
  task-by-task TDD implementation plan at docs/superpowers/plans/<YYYY-MM-DD>-<slug>.md.
---

# `plan`: feature plan creator

Writes a plan in the same shape as `docs/superpowers/plans/2026-10-30-sharpit-mvp.md`, so `/sharpit:status` can read
it and a subagent can execute one task at a time (`superpowers:subagent-driven-development`). For a plan of any size,
also load `superpowers:writing-plans`; this skill adds sharpit's conventions on top of it.

```
/sharpit:predict  →  /sharpit:scenario  →  /sharpit:plan  ← here  →  execution  →  /sharpit:check  →  review
```

## When not to invoke

A bug fix under ~10 lines with a proven cause (go to `issue-resolve`), docs-only work, or a task the active plan already
specifies (use `/sharpit:status`).

## Protocol

### 1. Gather inputs (do not ask for what the conversation already holds)

- Predict verdict, confidence, mitigations; scenario must-cover tests.
- The feature in one sentence and a slug (lowercase, hyphenated, no date).
- `uv run python scripts/dev/active_plan.py` to see what is in flight, and the design spec §2/§3 (goals and
  non-goals) to confirm the feature is in scope. If the spec's §15 coordinator's calls or §14 deviation log bear on it,
  cite them.

### 2. Clarify (at most three questions, only if the answer changes the breakdown)

Scope boundary, which module owns it (`engine/` vs `fastapi/` vs `ui/`), and what "done" looks like (an endpoint's JSON,
a UI state, an MCP tool result).

### 3. Decompose

- Each task is one atomic commit with a conventional message (`feat:`, `fix:`, `test:`, `chore:`, `docs:`).
- Failing tests come before the code that turns them green, in the same task.
- Critical and High scenarios become explicit test names in the task that owns them.
- Every task lists files, interfaces it produces or consumes, and `- [ ] **Step N:**` checkboxes.

Typical order for a sharpit feature:

| # | Task | Notes |
|---|---|---|
| 1 | Contract first | Which contract § and golden fixture; add/extend the fixture via `scripts/sanitize_golden.py` if BootUI has the shape |
| 2 | Engine | Pure logic in `engine/` with ported BootUI tests (`# ported: Class.case`) |
| 3 | Adapter | FastAPI wiring in `fastapi/`; guard and panel gate applied |
| 4 | Safety | `no_side_effects` test for every new GET/MCP path; masking corpus extended for every new output |
| 5 | MCP / CLI mirror | Only if the data is exposed to agents: `engine/tools.py`, same caps and masking |
| 6 | UI | Only if user-visible; built into `src/sharpit/ui/static/` and committed |
| 7 | Docs | README, `skills/sharpit/SKILL.md` for user-facing changes, spec §14 for any deviation |

### 4. Draft and show

```markdown
# <Feature> Implementation Plan

> For agentic workers: run `/sharpit:status --feature <slug>` for the next unchecked step. One task at a time;
> `/sharpit:check` before every commit.

**Goal:** <one sentence, user-visible outcome>

**Architecture:** <2-3 sentences: modules, key decisions, what stays the same>

**Predict verdict:** <GO / CAUTION n/10, or "pending">

## Global Constraints
<the ones from AGENTS.md that this feature can break, verbatim>

## Risk register
| Severity | Risk | Mitigation |

### Task 1: <name>
**Files:** ...
**Interfaces:** Produces / Consumes ...
- [ ] **Step 1:** Write the failing test `test_...` (expected failure: ...)
- [ ] **Step 2:** ...

## Definition of done
- [ ] All steps checked
- [ ] `/sharpit:check` green (ruff check, ruff format --check, pyright strict, pytest)
- [ ] Every Critical/High scenario has a named test
- [ ] Deviations from BootUI logged in the spec §14
- [ ] `/sharpit:live-verify` evidence if an endpoint or the UI changed
```

Show the draft. Write it once approved, or straight away when running autonomously, and say so.

### 5. Write

`docs/superpowers/plans/<YYYY-MM-DD>-<slug>.md`, committed on the feature branch with the scenario note. Then: "Plan
written. Next: `/sharpit:status --feature <slug>`, then execute task by task with
`superpowers:subagent-driven-development`."

Ported from gflow-cli's `plan` skill; adapted to sharpit's flat plan files and contract-first task order.
