# Lane F5b: SQLAlchemy gatekeeper package, then the MySQL/SQLite read-only path

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `F5b` (worktree `C:\development\github\sharpit-wt\0.5.0-F5b`, branch `lane/0.5.0-F5b`) |
| **Goal** | `engine/sqla.py` becomes `engine/sqla/` in one move-only commit; then a verified, fail-closed read-only path for SQLite and MySQL/MariaDB. |
| **Spec** | §4.1, §5.0 (O6 = yes, provisional) |
| **Worker** | codex gpt-6-luna, high; reviewer Opus; `ponytail-review` mandatory |
| **Council** | **required** — before Task 1 (rule 4 widens from a file to a package) and on Task 3's design |
| **Depends on** | F5a-harness merged (R0 on `tests/engine/test_import_boundary.py`), P-0.4.1 merged (R0 `engine/sqla` chain: T-unbounded-read → P-0.4.1 → F5b) |
| **Protected files allowed (F5-gate `PROTECTED_ALLOWED`)** | `tests/engine/test_import_boundary.py` |
| **May touch** | `src/sharpit/engine/sqla.py` → `src/sharpit/engine/sqla/{__init__,listeners,readonly,events,orm,inspect}.py`, the seven test files that patch `sqla` names (`tests/engine/test_sqla.py`, `tests/engine/test_sqla_read_only.py`, `tests/engine/test_dispatch.py`, `tests/engine/capture/test_activity.py`, `tests/engine/test_sqlastats.py`, `tests/fastapi/test_sqlite_console.py`, `tests/test_foundation_round2.py`), `tests/engine/test_import_boundary.py` (`GATEKEEPERS` key `sqla/`), `tests/test_patch_targets.py` (new), `tests/engine/test_sqla_read_only_dialects.py` (new), `tests/fastapi/test_mysql_read_only_leased.py` (new), `AGENTS.md` (rule 4, Layout), the lane folder |
| **Must NOT touch** | any collector, route, capture module; `engine/models.py` (stays in the engine: it imports no SQLAlchemy; council r2 M4); budget constants |

After this lane, the lanes working inside `engine/sqla/` at the same time (R-transactions on `events.py`, A-dbadv-1 on
`inspect.py`) add **no public name to `sqla/__init__.py`**; their callers import from the submodule.

## Must-cover

`tests/test_patch_targets.py::test_patch_targets_are_defined_where_called`,
`tests/engine/test_import_boundary.py::test_sqla_package_is_the_only_sqlalchemy_importer`,
`tests/engine/test_import_boundary.py::test_planted_sqlalchemy_import_outside_package_fails`,
`tests/engine/test_sqla_read_only_dialects.py::test_sqlite_read_only_wrapper_rejects_write`,
`tests/engine/test_sqla_read_only_dialects.py::test_sqlite_restore_failure_invalidates`,
`tests/engine/test_sqla_read_only_dialects.py::test_mysql_read_only_statement_order`,
`tests/engine/test_sqla_read_only_dialects.py::test_mysql_verification_failure_refuses`,
`tests/engine/test_sqla_read_only_dialects.py::test_mysql_autocommit_refused`,
`tests/engine/test_sqla_read_only_dialects.py::test_mariadb_old_variable_name`,
`tests/engine/test_sqla_read_only_dialects.py::test_mysql_restore_failure_invalidates`,
`tests/engine/test_sqla_read_only_dialects.py::test_other_dialect_read_only_unavailable`,
`tests/fastapi/test_mysql_read_only_leased.py::test_mysql_read_only_wrapper_rejects_write` (leased),
`tests/fastapi/test_mysql_read_only_leased.py::test_mysql_autocommit_engine_refused` (leased).

## Tasks

### Task 0: council
- [ ] `/sharpit:llm-council --tier high` on spec §4.1 and §5.0 → `council.md` (APPROVE needed before Task 1).

### Task 1: the move (one `refactor:` commit, no logic edit)
- [ ] **Step 1:** Red commit `test: sqlalchemy gatekeeper is the sqla package; patches hit their definitions`:
  - `test_sqla_package_is_the_only_sqlalchemy_importer` — the set of modules importing `sqlalchemy` ⊆
    `engine/sqla/`; expected failure: the assertion lists `engine/sqla.py`.
  - `test_patch_targets_are_defined_where_called` — `ast` scan of `tests/` for `monkeypatch.setattr(<module>, "<name>")`
    on `sharpit.engine.sqla*`; each `<name>` defined in `<module>` itself. A pin today (single module), recorded as
    such; it fails mid-move if a patch is left on `__init__`.
  - `test_planted_sqlalchemy_import_outside_package_fails`.
- [ ] **Step 2:** Move by concern; `__init__.py` re-exports `__all__`; retarget every patch to the defining submodule;
  mutation-prove each retargeted patch (`findings.md`, `pin:` rows). Gatekeeper key → prefix `sqla/`; AGENTS.md.
- [ ] **Step 3:** Full suite + overhead budgets (background), constants unchanged. Commit
  `refactor: sqlalchemy gatekeeper becomes the engine/sqla package` (body: the rule change and why).

### Task 2: SQLite read-only
- [ ] **Step 1:** Red commit (skeleton: the SQLite branch raises `ReadOnlyUnavailable` as today):
  `test_sqlite_read_only_wrapper_rejects_write` (in-memory sqlite, `INSERT` inside `run_db_read(read_only=True)` →
  `sqlite3.OperationalError` "attempt to write a readonly database"; expected failure: `ReadOnlyUnavailable` before
  the write), `test_read_only_restores_session_state` (`PRAGMA query_only` back to its saved value after success and
  after an exception), `test_sqlite_restore_failure_invalidates` (a restore that raises → `conn.invalidate()` called;
  the connection never returns to the pool read-only).
- [ ] **Step 2:** Save `PRAGMA query_only`, set `ON`, read back (≠ 1 → `ReadOnlyUnavailable`), run, restore in
  `finally`, invalidate on restore failure. Commit `feat: verified read-only reads on sqlite`.

### Task 3: MySQL/MariaDB read-only (council r2 H1, H2)

Design. `START TRANSACTION READ ONLY` affects only the current transaction and does **not** change
`@@transaction_read_only` (that variable reports the session value), and SQLAlchemy's autobegin makes
`conn.in_transaction()` true anyway, so neither proves anything. sharpit sets the **session** characteristic instead,
and the leased write-rejection test is the acceptance test:

1. Variable name: `transaction_read_only` (MySQL ≥ 5.7.20, MariaDB ≥ 11.1), else `tx_read_only` (older MariaDB),
   chosen from `@@version` / `@@version_comment`.
2. Save `@@SESSION.autocommit`, `@@SESSION.<ro var>`, `@@SESSION.max_execution_time` (MariaDB
   `max_statement_time`) and `@@SESSION.innodb_lock_wait_timeout`. `@@SESSION.autocommit = 1` →
   `ReadOnlyUnavailable`: a server-side answer, independent of the driver (pymysql's `autocommit` is a method, so the
   PostgreSQL branch's `getattr(dbapi, "autocommit") is True` idiom, `sqla.py:625`, cannot see it). An engine whose
   execution options say `isolation_level="AUTOCOMMIT"` is refused before any statement.
3. `ROLLBACK` (ends any implicit transaction autobegin opened, so the next transaction takes the session value), then
   `SET SESSION <ro var> = 1` and the timeout variables.
4. Verify `SELECT @@SESSION.<ro var>` is `1`, else `ReadOnlyUnavailable`. Then `fn(conn)`.
5. `finally`: `ROLLBACK`, restore every saved session value; a restore failure → `conn.invalidate()` (the `bounded()`
   pattern), so a read-only session never returns to the app's pool.

- [ ] **Step 1:** Red commit (a recording fake connection whose `SELECT` answers are scripted, plus the leased file):
  `test_mysql_read_only_statement_order` (the five steps in order), `test_mysql_verification_failure_refuses` (the
  read-back answers 0 → `ReadOnlyUnavailable`, `fn` never called), `test_mysql_autocommit_refused` (`@@autocommit`
  answers 1), `test_mariadb_old_variable_name` (`10.6.x-MariaDB` → `tx_read_only`),
  `test_mysql_restore_failure_invalidates`, `test_other_dialect_read_only_unavailable` (`oracle`). Expected failure:
  today's branch raises `ReadOnlyUnavailable` before any statement (`sqla.py:612-613`), so the recorded statement list
  is empty. Leased (`SHARPIT_TEST_MYSQL_URL`, `pymysql`): `test_mysql_read_only_wrapper_rejects_write` (`INSERT`
  inside → error 1792 `ER_CANT_EXECUTE_IN_READ_ONLY_TRANSACTION`), `test_mysql_autocommit_engine_refused`.
- [ ] **Step 2:** Implement in `sqla/readonly.py`. If the leased run shows the server behaving otherwise, the lane stops
  and reports to the coordinator; fail-closed stays (any doubt → `ReadOnlyUnavailable`). Commit
  `feat: verified read-only reads on MySQL and MariaDB`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/F5b/`: `council.md`, `handoff.md` (module map old name → submodule; the leased run's
server version and variable values), `findings.md` (patch mutations as `pin:` rows), `field-map.md` (`N/A`),
`checklist.md`.
