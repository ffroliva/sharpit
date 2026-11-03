# Handoff: lane A-dbadv-2 (0.5.0)

Implementer: Claude Code (claude-opus-5-5)
Branch `lane/0.5.0-A-dbadv-2` from `f39fee2` (release/0.5.0 after A-dbadv-1), release/0.5.0 merged in afterwards
(coordinator ruling). Status: DONE_WITH_CONCERNS (leased PostgreSQL/MySQL tests unverified here).

## Done

| Task | Red SHA | Fix SHA | What |
|---|---|---|---|
| 1 ORM rules | `5033069` | `c4fb15b` | `rules_orm.py`: DB-HIB-002..007, 009, 010; `facts(models)` through `engine/models.py`'s configured-gate |
| 2 runtime + vendor | `2c8333e` | `d7a05f4` | `rules_runtime.py` DB-RUNTIME-001; `rules_vendor.py` DB-PG-001..005, DB-MYSQL-001..003, DB-SCHEMA-010, DB-SERVER-001/002, `read_vendor(conn, bounds)` |
| pin + test hardening | — | `a0c88d0` | `test_scan_leaves_a_configurable_registry_unconfigured` (mutation-proven); autouse GC pause in the ORM tests |
| merge release/0.5.0 | — | merge commit | transactions test-isolation fix, B-security-logs; no duplicated top-level defs; no UI conflict |
| 3 wiring (coordinator amendment) | `e2df0fa` | `1444fed` | `catalog._read` also runs `read_vendor` in the same read-only read; `report.run_scan` adds `"orm"` to every source and `"runtime"` (SQL Trace window) to the first |

All 33 ported checks are registered (`database_advisor/__init__.py::RULES`) and `implemented` in
`docs/database-advisor-checks.md`. Reds, pins and dispositions: `findings.md`.

**Live scan** (`test_live_scan_runs_orm_runtime_and_vendor_rules`, in-process SQLite app, `install(models=...)`,
`sql_trace_capture_parameters=True`): DB-HIB-006 and DB-RUNTIME-001 fire; vendor rules are `SKIPPED` with their
dialect reason ("This check reads the postgresql catalog; datasource db is sqlite."), not "not read".

## Must-cover

| Test | Exists | Passes at head |
|---|---|---|
| tests/engine/collectors/database_advisor/test_rules_orm.py::test_scan_never_configures_mappers | yes | yes |
| tests/engine/collectors/database_advisor/test_rules_orm.py::test_unconfigured_registry_skips_orm_rules | yes | yes |
| tests/engine/collectors/database_advisor/test_rules_vendor.py::test_unsupported_dialect_skips_vendor_rules | yes | yes |
| one test per ORM rule (`test_hib_00{2,3,4,5,6,7,9}_*`, `test_hib_010_*`) | yes | yes |
| DB-RUNTIME-001 from a seeded SQL Trace ring (`test_runtime_001_*`) | yes | yes |
| one test per vendor rule (`test_schema_010_*`, `test_pg_00{1..5}_*`, `test_mysql_00{1..3}_*`, `test_server_00{1,2}_*`) | yes | yes |
| `test_pg_vendor_rules_on_a_leased_server`, `test_mysql_vendor_rules_on_a_leased_server` | yes | skip without `SHARPIT_TEST_POSTGRES_URL` / `SHARPIT_TEST_MYSQL_URL` (leased; unverified here) |

Unverified: DB-PG-004 (publications) has no leased test; the plan's must-cover does not name one, so none was added.

## Decisions

1. **Facts seam.** Rules keep A-dbadv-1's `Rule(definition, check(Source))` shape and read plain-dict facts from
   `source.catalog`: `"orm"` (`rules_orm.facts(models)`), `"runtime"` (`rules_runtime.facts(trace.rows())`),
   `"vendor"` (`rules_vendor.read_vendor(conn, bounds)`). An absent fact is a skip reason, never a pass. `catalog.py`
   imports `read_vendor` lazily (`rules_vendor` imports `catalog`). Runtime facts go on the first source only, so a
   multi-engine scan does not duplicate its findings.
2. **ORM without configuring.** Only `mapper.local_table` is read, after `mappers_configured`; a declared foreign key
   is the `ForeignKey` target string, never `mapper.relationships`. Non-default-schema tables are not compared.
   HIB-005 skips on SQLite (the inspector hides UNIQUE-constraint indexes); HIB-009 runs on PostgreSQL/MySQL/MariaDB.
   IDENTITY analogue = `Identity()` or `autoincrement=True`. Known limit: the catalog lists no views, so a model
   mapped to a view is reported by HIB-002.
3. **DB-RUNTIME-001** keeps counts and SHA-256 digests per shape only; with parameter capture off the ring holds only
   normalized text and the rule skips with that reason. Placeholder lists are folded.
4. **Vendor reads**: fixed statements, no parameters and no `%`; PostgreSQL statements in a savepoint; rows bounded
   by `vendor_rows`. DB-SERVER-001/002 read `pg_settings.reset_val` (the advisor's read sets its own statement
   timeout). DB-PG-002 compares the sequence's own bounds; a null `last_value` is not assessed.
5. **Size**: rule modules 330 / 106 / 301 lines, under the 1000-line hard limit; together 737, over PLAN's ~600-line
   split guide (about half is rule prose). Not split, per the coordinator ruling.
6. The wiring red commit was amended once before any fix (its engine registry was a fake that SQL Trace cannot route
   by); re-red-checked RED. The amend also carried the removal of `wiring.patch` from git.

## Gates (at head)

`ruff check` clean, `ruff format --check` clean, `pyright` 0 errors. Full suite `pytest -q -n 4` (log `logs/A-dbadv-2-pytest-2.log`): 5304 passed, 26 skipped, 2 failed, both outside
this lane's diff: `tests/fastapi/test_security_api.py::test_mcp_tools_list_has_only_get` (fails alone too: the
security tool list now also has `get_security_logs`, a B-security / B-security-logs interaction from the merged
release) and `tests/fastapi/test_security_logs_overhead.py::test_security_logs_hook_overhead_budget` (passes alone;
load-sensitive budget under `-n 4`). The 5 earlier `test_transactions_api.py` failures are gone after the merge.
Lane gate self-check: only the coordinator's refusals (review.md, gate logs).

## Open questions for the coordinator

1. `test_security_api.py::test_mcp_tools_list_has_only_get` fails on the merged release (see Gates).
2. Run the leased tests in `test_rules_vendor.py` on PostgreSQL and MySQL (and A-dbadv-1's leased file).

## How to resume

All work is committed. Next: coordinator review and leased runs.
