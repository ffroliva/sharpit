# Lane G0: post-scan golden recapture (tiny-ledger-bootui, BootUI 2.2.0) — OWNER-ONLY

> **For agentic workers:** steps use `- [ ]` checkboxes. **Tasks 2–6 run only with the owner's go on spec §13 O1.**
> Task 1 is groundwork and needs nothing. Only fixture files land in sharpit, through one commit on `lane/0.5.0-G0`.

| | |
|---|---|
| **Lane id** | `G0` (reference: `C:\development\github\tiny-ledger-bootui-ref`, branch `chore/bootui-2.2.0-goldens-05`; sharpit worktree `C:\development\github\sharpit-wt\0.5.0-G0` for the fixture commit) |
| **Goal** | Post-scan and post-read goldens so advisor, database and vulnerability panels are checked item by item (spec §5 post-scan parity definition). |
| **Spec** | §5, §6; O1 (owner-only), O2 (provisional no) |
| **Worker** | agy-sergio, Gemini 3.8 slot (Argon stays on the C lanes) |
| **Council** | not required |
| **Depends on** | Task 1: nothing. Tasks 2–6: the owner's O1 answer, reference-stack leases (coordinator) |
| **May touch (sharpit)** | `tests/fixtures/bootui/2.2.0/{security,architecture,fastapi,database-advisor,vulnerabilities}/{scanned,violations}.captured.json`, `tests/fixtures/bootui/2.2.0/sqlalchemy-statistics/captured.json`, `tests/fixtures/bootui/2.2.0/data/repositories.scanned.captured.json`, `tests/fixtures/bootui/2.2.0/mysql/scanned.captured.json`, `tests/fixtures/bootui/2.2.0/meta.json`, the lane folder `.superpowers/sdd/0.5.0/lanes/G0/` |
| **Must NOT touch** | any `src/` file, any test, existing `captured.json` files |

## Tasks

### Task 1: groundwork (no owner call needed)
- [ ] `capture-runbook.md` in the lane folder: per panel the exact requests (BootUI paths, method, body), the order
  (GET pre-scan, POST scan/read, GET post-scan, first violations page `?limit=5`), the `scripts/sanitize_golden.py`
  invocation and the target file name above.
- [ ] Dry-run `scripts/sanitize_golden.py` on the existing `captured.json` files into a scratch dir; the output equals
  the committed files (proves the sanitiser is stable before new captures).

### Task 2 (O1): post-scan captures, no reference-app change
- [ ] `security`, `architecture`, `spring` (→ `fastapi`), `database-advisor`: `scanned.captured.json` +
  `violations.captured.json`.

### Task 3 (O1): vulnerabilities recapture
- [ ] The current golden records `scan.status: "ERROR"` (PKIX). Configure a working truststore for the reference JVM;
  `POST /bootui/api/vulnerabilities/scan`, `GET` → `vulnerabilities/scanned.captured.json` with real findings.

### Task 4 (O1): Hibernate statistics
- [ ] `spring.jpa.properties.hibernate.generate_statistics=true`; exercise the ledger flows;
  `GET /bootui/api/hibernate-statistics` → `sqlalchemy-statistics/captured.json`; drop its `uncaptured` entry.

### Task 5 (O1): Spring Data repository
- [ ] One `JpaRepository`; `GET /bootui/api/data/repositories` → `data/repositories.scanned.captured.json`
  (`total >= 1`).

### Task 6 (O1, advisor recommends no): MySQL
- [ ] Only if the owner adds a MySQL datasource: `POST /bootui/api/mysql/read`, `GET` → `mysql/scanned.captured.json`.

### Task 7: hand-off
- [ ] One sharpit commit `test: BootUI 2.2.0 post-scan goldens` with only fixture files; the coordinator cherry-picks
  it onto `release/0.5.0` and re-runs every parity test (PLAN.md Step 4).

## Evidence

`.superpowers/sdd/0.5.0/lanes/G0/`: `capture-runbook.md`, `handoff.md` (commands, reference commit, which tasks ran
and which the owner declined).
