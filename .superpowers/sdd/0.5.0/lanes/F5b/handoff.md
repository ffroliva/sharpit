# F5b handoff

Implementer: Claude subagent (claude-opus-5-5)

## Status

DONE_WITH_CONCERNS. Code head `f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd` on `lane/0.5.0-F5b` (from `release/0.5.0`
836d3fd); the evidence commit follows it. Never pushed. Concerns: the leased MySQL tests have not run (no server here),
and three overhead budgets fail on this busy machine at base and head alike (below). Task 0 (council) skipped per the
brief: the coordinator runs it on this diff; the Task 3 design decisions are below for it.

## Tasks

| Task | Commit | What it proved |
|---|---|---|
| 1 red | `cc008ea4c4b847e92f712a81a14c39829e712203` (`test:`) | 2 reds (import boundary) + `test_patch_targets_are_defined_where_called` as a mutation-proven pin |
| 1 move | `8f80ad4bcc7bdb5837addaeb35f5d6fe7b3465d8` (`refactor:`) | `engine/sqla.py` → `engine/sqla/`; gatekeeper key `sharpit/engine/sqla`; AGENTS.md rule 4 + Layout; 7 retargeted patches mutation-proven |
| 2 red | `d81eab2c79024bc57f3d285ff06f1d6690d35d0a` (superseded), `9f7996026a5c1e4b96bbd2570b3cdd0ddc6eae36` (re-red) | 4 sqlite reds |
| 2 fix | `bf5370a67b3c14b4fc4e67a102337a6bfcd9e394` (`feat:`) | `PRAGMA query_only` saved, set ON, read back, restored; invalidate on a failed restore |
| 3 red | `9e1285527ad09cf37e457019d68655b37f3fe29e` (`test:`) | 7 MySQL/MariaDB reds + 2 pins + leased file (skips without `SHARPIT_TEST_MYSQL_URL`) |
| 3 fix | `f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd` (`feat:`) | MySQL/MariaDB session read-only path in `sqla/readonly.py` |

Reds, pins and mutations: `findings.md`, `mutations-task1.log`, `mutations-task3.log`, `budgets-paired.log`.

## Module map (old `engine/sqla.py` → `engine/sqla/`)

| Submodule | Names |
|---|---|
| `__init__` | `logger`, `UNAVAILABLE`, `TRACING_DISABLED`, `_lock` (one lock for the package), `sqlalchemy_module`, `unavailable_reason`, `sqlite3_traced`, `sql_trace_unavailable_reason`; re-exports every public name below in `__all__`, plus `TEST` (`tests/engine/test_n_plus_one_overhead.py` reads `sqla.TEST`) |
| `orm` | `RELATIONSHIP_KEY`, `_EAGER_RELATIONSHIP_KEY`, relationship / statement-site / eager / lazy / unbounded-read state, `MAX_STATEMENT_SITES`, `GENERIC_BATCH`, `_is_application_code` through `_mapper_load`, `apply_relationship_facts`, `apply_unbounded_read_facts`, `unbounded_read_capture_limitation_needed`, `set_unbounded_read_factor` |
| `inspect` | `_engine_class`, `live_engine_drivers`, `EngineRegistry` |
| `events` | `ConnectionEvent`, `CONNECTION_EVENTS`, `add_connection_listener` |
| `listeners` | `STATEMENT_EVENTS`, `DISCOVERY_EVENT`, `DISCOVERY_PANELS`, `START_KEY`, routing state, `engine_connect`, `before_cursor_execute`, `_pop_start`, `_named`, `_emit`, `after_cursor_execute`, `handle_error`, `_LISTENERS`, `_sync_listeners`, `add`, `remove`, `detach_all`, `attach_session`, `detach_session`, `routed`, `note_request_captured`, `attached` |
| `readonly` | `READ_ONLY_REFUSED`, `ReadOnlyUnavailable`, `is_internal`, `bounded_read_only`, `bounded`, `run_db_read` (+ new `_restore`, `_sqlite_read_only`, `_mysql_read_only`, `_version`, `_number`) |

Lookups changed in the move (no logic change): submodules call `_sqla.sqlalchemy_module()` through the package (tests
patch it there, some in files outside May-touch: `tests/fastapi/test_sqla_absent.py`,
`tests/engine/postgresql/test_service.py`); `detach_session` and `note_request_captured` write the three
unbounded-read flags as `_orm.<flag>`, and `note_request_captured` moved to `listeners` (it reads `_session`) so `orm`
never imports `listeners`. `orm` and `listeners` carry a file-level `# pyright: reportPrivateUsage=false` (the package
was one module; they share private state; `orm` also `reportUnusedFunction=false` for helpers only `listeners` calls).
All imports are absolute, so `orm`'s `import inspect` is the stdlib.

Other edits: `tests/engine/test_import_boundary.py::test_the_rules_catch_a_violation` (pre-existing) plants its allowed
SQLAlchemy import in `sqla/listeners.py` instead of `sqla.py`, as the rule changed. `tests/test_patch_targets.py` was
started by a previous worker: reviewed and kept (it checks every caller, stricter than "defined where patched"), with
two line-length fixes and a `SyntaxWarning` filter when parsing test files.

## Task 3 design decisions (for the council)

1. Variable from `SELECT @@version`: MariaDB when the version (or the dialect name) says so; `transaction_read_only` on
   MySQL >= 5.7.20 and MariaDB >= 11.1, else `tx_read_only`. `@@version_comment` is not read: MariaDB's `@@version`
   carries `-MariaDB` itself. Timeout: `max_execution_time` in ms (MySQL), `max_statement_time` in s (MariaDB), as
   `bounded()` does.
2. Refused before any statement when the connection's execution options say `isolation_level=AUTOCOMMIT`; refused
   after `SELECT @@SESSION.autocommit` answers non-zero (an engine-level `isolation_level="AUTOCOMMIT"` shows up here).
3. Order: `SELECT @@version`, `SELECT @@SESSION.autocommit`, save `<ro>`, the timeout, `innodb_lock_wait_timeout`;
   `conn.rollback()`; `SET SESSION <ro> = 1`, the timeout, `innodb_lock_wait_timeout = ceil(lock_timeout)` (min 1 s);
   verify `SELECT @@SESSION.<ro>` = 1, else `ReadOnlyUnavailable`; `fn`; `finally` `conn.rollback()` and
   `SET SESSION` of each saved value; a failing restore → `conn.invalidate()` and re-raise (shared `_restore`, also
   used by SQLite).
4. Saved values pass through `_number` (`float()`), so only a number is ever written back into SQL.
5. Errors before the SETs (a missing variable on an old server, a dropped connection) propagate as themselves, as in
   the PostgreSQL branch; `fn` never runs, so the read still fails closed.
6. SQLite: `PRAGMA query_only` saved, `= ON`, read back (not 1 → refused), restored after `conn.rollback()`; no
   timeouts (sqlite has none server-side).

Open question for the coordinator: the leased run is the acceptance test (`SHARPIT_TEST_MYSQL_URL`, pymysql; error
1792 expected; after the read the pooled connection must report `transaction_read_only = 0`). Not run here; record
the server version and variable values from it.

## Gates (at f079a6f)

- `ruff check`: clean; `ruff format --check`: clean; `pyright src/sharpit`: 0 errors.
- Full suite `-n 4` (`0.5.0-integration/.superpowers/sdd/0.5.0/logs/F5b-suite-final.log`): 4666 passed, 11 skipped,
  4 failed:
  - `tests/test_overhead_harness.py::test_every_budget_module_runs_last`: `ImportError: cannot import name
    'TIMING_MODULES' from 'conftest' (tests/fixtures/apps/unbounded_read/conftest.py)`. A conftest module-name
    collision already on the base (that fixture conftest came in 4681c8b); lane A-sqltrace-insights hits the same
    (`logs/A-sqltrace-insights-pytest.log`). Passes when run alone.
  - Three budgets (`test_request_overhead_budget`, `test_statement_overhead_budget`,
    `test_sqlalchemy_lazy_relationship_hook_overhead_budget`) on a loaded machine. Paired serial runs, base 836d3fd vs
    head 8f80ad4 (`budgets-paired.log`): base run 1 failed all three, head run 1 only the lazy one; base run 2 failed
    capture + lazy, head run 2 only lazy (42.5 µs, noise 25.8). Head is not slower than base. No budget constant
    changed.

## Fix round 1 (council: Gemini APPROVE x2, Claude APPROVE WITH CHANGES)

Base: coordinator merge `2281ad2`. The leased MySQL tests passed there (coordinator, MySQL 8.4).

| Finding (`council-claude.md`) | Disposition |
|---|---|
| 1 medium: SQLite read-back check untested | `6a2d8cf` (`test:`): `test_sqlite_read_back_not_on_refuses` (read-back answers 0 → refused, `fn` not run, `query_only` still restored) and `test_sqlite_read_back_failure_refuses` (read-back raises → the error, `fn` not run, restored). Both pass at head, so they are pins: M8 deleted the check and both failed (`mutations-fix1.log`, `findings.md`) |
| 2 low: two MariaDB rules | `47ed801` (`refactor:`): `_is_mariadb(conn, version="")` (dialect name, `dialect.is_mariadb`, or `-MariaDB` in `@@version` when read), used by `bounded()` and `_mysql_read_only`. `bounded()` behaviour unchanged; the read-only path now also honours `is_mariadb` |
| 3 low: leased test hard-codes `transaction_read_only` | Not changed: the leased file is red-committed (`9e12855`) and must not be edited. MariaDB (`tx_read_only`, `max_statement_time` in seconds) is verified by fakes only, not live; only MySQL 8.4 ran live. A MariaDB < 11.1 leased run needs a new test that reads the variable the code chose |
| 4 low: MySQL < 5.7.8 refuses with the driver error | Kept as design note 5 (fail-closed, as the PostgreSQL branch). A-mysql and A-dbadv-1 callers must catch driver errors as well as `ReadOnlyUnavailable`. The `tx_read_only` MySQL branch is reachable on 5.7.8 to 5.7.19 only |
| 5 low: pyright suppressions | `47ed801`: `orm.py` loses the file-level `reportUnusedFunction=false`; the two helpers only `listeners` calls (`_record_relationship`, `_mapper_load`) carry a line-level ignore, so dead-code detection is back on for the rest of `orm`. The file-level `reportPrivateUsage=false` in `orm`/`listeners` and the one line ignore in `events` stay: making the shared state public would rename names that tests and the move-only commit rely on, for no behaviour gain |
| 6 nit: duplicate importer test | Kept: it is a plan must-cover test and states the rule in its own name |

Gates at `47ed801`: ruff check and format clean, pyright 0 errors; sqla test files 100 passed, 5 skipped; full suite
`-n 4` (`logs/F5b-suite-fix1.log`): 4673 passed, 11 skipped, 1 failed, `test_request_overhead_budget` (capture per
request 0.212 ms vs 0.200 ms on a loaded machine; the fix touched only `readonly.py` and `orm.py` comments, not the
capture path; the base failed the same budget in the paired runs above).

## How to resume

Nothing left in the lane except the leased MySQL run and the coordinator's council and review. The scratch worktree
used for the paired budget runs (`sharpit-wt/F5b-base`) was removed.
