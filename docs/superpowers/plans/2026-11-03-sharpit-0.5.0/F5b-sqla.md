# Lane F5b: SQLAlchemy gatekeeper package, then the MySQL/SQLite read-only path

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `F5b` (worktree `C:\development\github\sharpit-wt\0.5.0-F5b`, branch `lane/0.5.0-F5b`) |
| **Goal** | `engine/sqla.py` becomes `engine/sqla/` in one move-only commit; then a verified read-only path for MySQL/MariaDB and SQLite; then the mapper walk joins the package. |
| **Spec** | §4.1, §5.0 (O6 = yes, provisional) |
| **Worker** | codex gpt-6-luna, high; reviewer Opus; `ponytail-review` mandatory |
| **Council** | **required** — before Task 1 (rule 4 widens from a file to a package) and on Task 3's design |
| **Depends on** | F5a merged (R0 on `tests/engine/test_import_boundary.py`; Task 4 folds `engine/models.py`), P-0.4.1 merged (R0 `engine/sqla` chain: T-unbounded-read → P-0.4.1 → F5b) |
| **May touch** | `src/sharpit/engine/sqla.py` → `src/sharpit/engine/sqla/{__init__,listeners,readonly,events,orm,inspect}.py`, `src/sharpit/engine/models.py` → folded into `sqla/orm.py` (Task 4), the seven test files that patch `sqla` names (`tests/engine/test_sqla.py`, `tests/engine/test_sqla_read_only.py`, `tests/engine/test_dispatch.py`, `tests/engine/capture/test_activity.py`, `tests/engine/test_sqlastats.py`, `tests/fastapi/test_sqlite_console.py`, `tests/test_foundation_round2.py`), `tests/engine/test_import_boundary.py` (`GATEKEEPERS` key `sqla/`), `tests/test_patch_targets.py` (new), `tests/engine/test_sqla_read_only_dialects.py` (new), `tests/fastapi/test_mysql_read_only_leased.py` (new), `AGENTS.md` (rule 4, Layout), the lane folder |
| **Must NOT touch** | any collector, route, capture module; budget constants |

## Must-cover

`test_patch_targets_are_defined_where_called`, `test_sqla_package_is_the_only_sqlalchemy_importer`,
`test_planted_sqlalchemy_import_outside_package_fails`, `test_sqlite_read_only_wrapper_rejects_write`,
`test_mysql_read_only_wrapper_rejects_write`, `test_mysql_autocommit_refused`, `test_other_dialect_read_only_unavailable`,
`test_read_only_restores_session_state`.

## Tasks

### Task 0: council
- [ ] `/sharpit:llm-council --tier high` on spec §4.1 and §5.0 → `council.md` (APPROVE needed before Task 1).

### Task 1: the move (one `refactor:` commit, no logic edit)
- [ ] **Step 1:** Red commit `test: sqlalchemy gatekeeper is the sqla package; patches hit their definitions`:
  - `test_sqla_package_is_the_only_sqlalchemy_importer` — asserts the set of modules importing `sqlalchemy` ⊆
    `engine/sqla/`; expected failure: the assertion lists `engine/sqla.py` (a file, not under the package).
  - `test_patch_targets_are_defined_where_called` — `ast` scan of `tests/` for `monkeypatch.setattr(<module>, "<name>")`
    on `sharpit.engine.sqla*`; each `<name>` must be defined in `<module>` itself, not re-exported. A pin today
    (single module); it turns red mid-move if a patch is left on `__init__`, which is the point.
  - `test_planted_sqlalchemy_import_outside_package_fails`.
- [ ] **Step 2:** Move by concern; `__init__.py` re-exports `__all__`; retarget every patch to the defining submodule;
  mutation-prove each retargeted patch (break the patched function in a scratch tree, the test must fail; record in
  `findings.md`). Gatekeeper key → prefix `sqla/`; AGENTS.md rule 4 + Layout.
- [ ] **Step 3:** Full suite + overhead budgets (background), constants unchanged. Commit
  `refactor: sqlalchemy gatekeeper becomes the engine/sqla package` (body: the rule change and why). A veto is one revert.

### Task 2: SQLite read-only
- [ ] **Step 1:** Red commit (skeleton: the SQLite branch raises `ReadOnlyUnavailable` as today):
  `test_sqlite_read_only_wrapper_rejects_write` (in-memory sqlite, `INSERT` inside `run_db_read(read_only=True)` →
  `sqlite3.OperationalError` "attempt to write a readonly database"; expected failure: `ReadOnlyUnavailable` raised
  before the write), `test_read_only_restores_session_state` (`PRAGMA query_only` back to 0 after success and after an
  exception).
- [ ] **Step 2:** `PRAGMA query_only = ON`, verified by reading it back, restored in `finally`. Commit
  `feat: verified read-only reads on sqlite`.

### Task 3: MySQL/MariaDB read-only
- [ ] **Step 1:** Red commit (unit with a recording fake connection for MySQL and MariaDB dialect names, plus the
  leased file): `test_mysql_read_only_statement_order` (`SET SESSION max_execution_time` / MariaDB
  `max_statement_time`, `innodb_lock_wait_timeout`, `START TRANSACTION READ ONLY`, verify `@@transaction_read_only`
  or the in-transaction check, then `fn`, then `ROLLBACK`, then restores), `test_mysql_autocommit_refused`,
  `test_other_dialect_read_only_unavailable` (`oracle` → `ReadOnlyUnavailable`), and leased
  `test_mysql_read_only_wrapper_rejects_write` (`ER_CANT_EXECUTE_IN_READ_ONLY_TRANSACTION`; skips without
  `SHARPIT_TEST_MYSQL_URL`; coordinator runs it, `gate/leased-mysql.log`).
- [ ] **Step 2:** Implement in `sqla/readonly.py`; restore failure invalidates the connection (the `bounded()` pattern).
  Commit `feat: verified read-only reads on MySQL and MariaDB`.

### Task 4: mapper walk into the package
- [ ] Move `engine/models.py` (F5a) into `sqla/orm.py`; F5a's tests green unchanged. Commit
  `refactor: mapper walk lives in the sqla package`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/F5b/`: `council.md`, `handoff.md` (the module map old name → submodule), `findings.md`
(the patch mutations), `field-map.md` (`N/A`), `checklist.md`.
