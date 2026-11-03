# Lane G0: post-scan golden recapture (tiny-ledger-bootui, BootUI 2.2.0)

> **For agentic workers:** steps use `- [ ]` checkboxes. This lane runs in the reference repo; only fixture files land
> in sharpit, through one commit on `lane/0.5.0-G0`.

| | |
|---|---|
| **Lane id** | `G0` (reference: `C:\development\github\tiny-ledger-bootui-ref`, branch `chore/bootui-2.2.0-goldens-05`; sharpit worktree `C:\development\github\sharpit-wt\0.5.0-G0` for the fixture commit) |
| **Goal** | Post-scan goldens so the advisor and database panels can be checked item by item, not only on the empty pre-scan shape. |
| **Spec** | §6; owner call §13 O1 decides which of Tasks 2–4 run |
| **Worker** | agy-sergio, Gemini 3.8 slot (Argon stays on C-architecture) |
| **Council** | not required |
| **Depends on** | owner's O1 answer; reference stack leases (coordinator) |
| **May touch (sharpit)** | `tests/fixtures/bootui/2.2.0/{security,architecture,fastapi,database-advisor,mysql,sqlalchemy-statistics,data}/scanned.captured.json`, `.../violations.captured.json`, `tests/fixtures/bootui/2.2.0/meta.json`, the lane folder |
| **Must NOT touch** | any `src/` file, any test, existing `captured.json` files |

## Tasks

### Task 1: post-scan captures (no reference-app change)
- [ ] On the running reference stack: for `security`, `architecture`, `spring`, `database-advisor`: `POST .../scan`,
  then `GET` → `scanned.captured.json`; first rule with violations → `GET rules/{id}/violations?limit=5` →
  `violations.captured.json`. Through `scripts/sanitize_golden.py` (ids → sharpit ids via `ids.json`).
- [ ] `meta.json`: capture time, BootUI commit, which files are post-scan.

### Task 2 (O1): Hibernate statistics
- [ ] `spring.jpa.properties.hibernate.generate_statistics=true` in the reference app profile; restart; exercise the
  ledger flows; `GET /bootui/api/hibernate-statistics` → `sqlalchemy-statistics/captured.json`; drop its `uncaptured`
  entry from `meta.json`.

### Task 3 (O1): Spring Data repository
- [ ] One `JpaRepository` in the reference app; `GET /bootui/api/data/repositories` →
  `data/repositories.scanned.captured.json` with `total >= 1`.

### Task 4 (O1): MySQL
- [ ] A capture app (or profile) with a MySQL 8.4 datasource; `POST /bootui/api/mysql/read`, `GET` →
  `mysql/scanned.captured.json`.

### Task 5: hand-off
- [ ] One sharpit commit `test: BootUI 2.2.0 post-scan goldens` with only the fixture files; the coordinator
  cherry-picks it onto `release/0.5.0` and tells the lanes in flight (their parity tests pick the file up
  automatically).

## Evidence

`.superpowers/sdd/0.5.0/lanes/G0/handoff.md`: commands, reference commit, which tasks ran and which the owner declined.
