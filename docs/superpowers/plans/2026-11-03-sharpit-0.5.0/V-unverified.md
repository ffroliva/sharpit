# Lane V-unverified: settle `data` and `sqlalchemy-statistics`

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `V-unverified` (worktree `C:\development\github\sharpit-wt\0.5.0-V-unverified`, branch `lane/0.5.0-V-unverified`) |
| **Goal** | Each of the two panels ends either at parity (item-checked against a real golden) or `unverified` with the exact reason no golden can exist. No blind code change. |
| **Spec** | §5.9 |
| **Worker** | Claude subagent; reviewer codex |
| **Council** | not required |
| **Depends on** | G0 Tasks 2–3 (if the owner approved them; otherwise only Task 3 here runs) |
| **May touch** | `tests/fastapi/test_data_api.py`, `tests/fastapi/test_sqlalchemy_statistics_api.py` (parity tests only), `src/sharpit/engine/collectors/data.py`, `src/sharpit/engine/collectors/sqlastats.py` (only to fix a mismatch a new golden shows), `tests/fixtures/bootui/2.2.0/{data,sqlalchemy-statistics}/nullable.json`, `docs/reference/PARITY.md` (these two rows), the lane folder |
| **Must NOT touch** | `engine/capture/sqltrace.py`, `engine/sqla/`, other panels |

## Tasks

### Task 1: `data` (only if G0 delivered `data/repositories.scanned.captured.json`)
- [ ] **Step 1:** `test_repositories_golden_parity_items` against the new golden with a fixture app whose models
  mirror the reference repository's entity. Red if any key or item type differs (expected: unknown until run; a pass
  on first run is recorded as "parity confirmed, no change", mutation-proven by dropping one key in a scratch tree).
- [ ] **Step 2:** Fix only what the red shows. Commit `test: data repositories item-level parity` (+ `fix:` if any).

### Task 2: `sqlalchemy-statistics` (only if G0 delivered its golden)
- [ ] Same pattern: `test_statistics_golden_parity`; every Hibernate counter SQLAlchemy cannot measure stays `null`
  and is listed in `nullable.json` with its reason (0.4.0 spec §4: no fabricated data).

### Task 3: PARITY rows
- [ ] `PARITY.md` rows for both: `parity` with the evidence test, or `unverified` with the reason (`total: 0` golden;
  no Hibernate statistics bean on the reference app; owner declined O1). Commit `docs: settle data and
  sqlalchemy-statistics parity status`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/V-unverified/`: `handoff.md`, `findings.md`, `checklist.md`.
