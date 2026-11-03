# Lane V-unverified: settle `data` and `sqlalchemy-statistics`

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development, one task at a time,
> `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `V-unverified` (worktree `C:\development\github\sharpit-wt\0.5.0-V-unverified`, branch `lane/0.5.0-V-unverified`) |
| **Goal** | The two built panels end at parity (item-checked against a real golden) or `unverified` with the exact reason. No blind code change. |
| **Spec** | §5.9 |
| **Worker** | Claude subagent; reviewer codex |
| **Council** | not required |
| **Depends on** | G0 Tasks 4–5 (owner-only, O1). Without them the lane is Task 3 only |
| **May touch** | `tests/fastapi/test_data_api.py`, `tests/fastapi/test_sqlalchemy_statistics_api.py` (parity tests only), `src/sharpit/engine/collectors/data.py`, `src/sharpit/engine/collectors/sqlastats.py` (only to fix a mismatch a new golden shows), `tests/fixtures/bootui/2.2.0/{data,sqlalchemy-statistics}/nullable.json`, the lane folder |
| **Must NOT touch** | `docs/reference/PARITY.md` (coordinator-owned), `engine/capture/sqltrace.py`, `engine/sqla/`, other panels |

## Must-cover

`test_repositories_golden_parity_items` (only if G0 Task 5 ran), `test_statistics_golden_parity` (only if G0 Task 4
ran). Neither ran → the lane has no must-cover tests and Task 3 records why.

## Tasks

### Task 1: `data` (only with `data/repositories.scanned.captured.json`)
- [ ] `test_repositories_golden_parity_items` with a fixture app mirroring the reference repository's entity. A
  first-run pass is a pin (mutation: drop one key from the collector in a scratch tree), never claimed as a red. Fix
  only what a red shows.

### Task 2: `sqlalchemy-statistics` (only with its golden)
- [ ] `test_statistics_golden_parity`; every Hibernate counter SQLAlchemy cannot measure stays `null` in
  `nullable.json` with its reason (no fabricated data).

### Task 3: status hand-off
- [ ] `handoff.md` gives the coordinator each row's status and evidence: `parity` + test, or `unverified` + reason
  (`total: 0` golden; no Hibernate statistics bean on the reference app; owner declined O1).

## Evidence

`.superpowers/sdd/0.5.0/lanes/V-unverified/`: `handoff.md`, `findings.md`, `checklist.md`.
