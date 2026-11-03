# Handoff: lane A-dbadv-2 (0.5.0)

Implementer: Claude Code (claude-opus-5-5)
Branch `lane/0.5.0-A-dbadv-2` from `f39fee2` (release/0.5.0 after A-dbadv-1). Status: DONE_WITH_CONCERNS: the rules
are complete and tested, but a live scan cannot feed them until the coordinator applies `wiring.patch` (question 1);
leased PG/MySQL tests are unverified here.

## Done

| Task | Red SHA | Fix SHA | What |
|---|---|---|---|
| 1 ORM rules | `5033069` | `c4fb15b` | `rules_orm.py`: DB-HIB-002..007, 009, 010; `facts(models)` through `engine/models.py`'s configured-gate |
| 2 runtime + vendor | `2c8333e` | `d7a05f4` | `rules_runtime.py` DB-RUNTIME-001; `rules_vendor.py` DB-PG-001..005, DB-MYSQL-001..003, DB-SCHEMA-010, DB-SERVER-001/002, `read_vendor(conn, bounds)` |
| pin + test hardening | — | `a0c88d0` | `test_scan_leaves_a_configurable_registry_unconfigured` (mutation-proven); autouse GC pause in the ORM tests |

All 33 ported checks are now registered (`database_advisor/__init__.py::RULES`) and `implemented` in
`docs/database-advisor-checks.md`. Reds, pins and dispositions: `findings.md`.

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

## Decisions

1. **Facts seam.** Rules keep A-dbadv-1's `Rule(definition, check(Source))` shape and read optional plain-dict facts
   from `source.catalog`: `"orm"` (`rules_orm.facts(models)`), `"runtime"` (`rules_runtime.facts(trace.rows())`),
   `"vendor"` (`rules_vendor.read_vendor(conn, bounds)`). An absent fact is a skip reason ("not read"), never a pass.
2. **ORM without configuring.** Only `mapper.local_table` (a `Table`) is read, after `mappers_configured`; a declared
   foreign key is the `ForeignKey` target string, never `mapper.relationships`. Tables declared in a non-default
   schema are not compared. HIB-005 skips on SQLite (the inspector hides UNIQUE-constraint indexes); HIB-009 runs on
   PostgreSQL/MySQL/MariaDB only. IDENTITY analogue = `Identity()` or `autoincrement=True` (not `"auto"`).
   Known limit: the catalog lists no views, so a model mapped to a view is reported by HIB-002.
3. **DB-RUNTIME-001** keeps only counts and SHA-256 digests per shape; the raw text exists in the ring only with
   parameter capture on, otherwise the rule skips ("parameter capture is off"). Placeholder lists are folded.
4. **Vendor reads**: fixed statements, no parameters and no `%` (pymysql would format it); PostgreSQL statements in a
   savepoint; rows bounded by `vendor_rows`. DB-SERVER-001/002 read `pg_settings.reset_val`, because the advisor's own
   read sets a statement timeout. DB-PG-002 compares the sequence's own bounds (not the owning column's type); a null
   `last_value` is not assessed. DB-SCHEMA-010 and DB-SERVER-001/002 live in `rules_vendor.py` (vendor catalog reads).
5. **Size**: the three rule modules are 737 lines, over PLAN's ~600 split guide; about half is rule prose
   (`RuleDefinition` texts) and the logic is small, so nothing was parked as a `-3` lane. Coordinator may disagree.

## Wiring (open question 1)

`wiring.patch` (this folder) changes `catalog.py` (`_read` returns `{**catalog(...), "vendor": read_vendor(...)}`,
lazy import because `rules_vendor` imports `catalog`) and `report.py` (`run_scan` adds `"orm"` to every source and
`"runtime"` to the first, so runtime findings are not duplicated), plus `tests/engine/collectors/database_advisor/
test_wiring_e2e.py` (in-process `POST /scan` with `install(models=...)`: DB-HIB-006 fires). Validated applied on this
head: e2e passes; with it, `test_database_advisor_api.py`, the advisor tests, safety, masking, import boundary: 154
passed, 3 skipped; pyright 0. Both files are outside A-dbadv-2's May-touch, so it is not committed.

## Gates (at head `a0c88d0` + evidence)

`ruff check` clean, `ruff format --check` clean, `pyright` 0 errors. Full suite `pytest -q -n 4`: 5161 passed,
23 skipped, 5 failed, all in `tests/fastapi/test_transactions_api.py` (capture-context assertions). They pass alone
(14 passed) and the same tests failed in lane B-security-logs' full suite (`logs/B-security-logs-pytest.log`), which
touches none of these files: an order-dependent failure outside this lane.

## Open questions for the coordinator

1. Apply `wiring.patch` (or allow `catalog.py`/`report.py`), otherwise the new rules are `SKIPPED` in every live scan.
2. Run the leased tests in `test_rules_vendor.py` on PostgreSQL and MySQL. PG-004 (publications) has no leased test.
3. The `test_transactions_api.py` order-dependent failures (above).

## How to resume

All work is committed. Next: coordinator review, wiring decision, leased runs.
