# A4: Database advisor incomplete discovery (BootUI 2.4.0 #1600)

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit. Read the named BootUI files at `v2.4.0` in a BootUI clone; never from a summary.

**Goal:** Database advisor discovery is honest about what could not be inspected. Incomplete evidence (missing
driver name, version, or URL; failed ORM model discovery; or dedicated PostgreSQL incomplete relation inventory) never reads
as a clean scan (`SCANNED`), but stays `PARTIAL` with explicit `WARNING` diagnostics and incomplete coverage. Absent
SQLAlchemy models and unconfigured mappers remain a neutral `INFO` skip that does not degrade an otherwise complete scan.

**Architecture:**
- Driver evidence (`engine.dialect.driver`, driver version, `engine.url`): driver version resolves from DBAPI
  `__version__`, `importlib.metadata`, or `sqlite3.sqlite_version`. Missing driver metadata emits adapted warning
  text (`"The database driver..."`, `"The database URL..."`), marking the scan `PARTIAL`.
- Usable flag: matches BootUI `DatabaseAdvisorScanner.doScan`: usable when any rule evaluated (violations or clean PASS),
  not "no findings".
- ORM metadata: absence of models/registries and unconfigured mappers are confirmed absent (`INFO` diagnostic), while
  an exception or invalid `models=` entry emits a `WARNING` diagnostic and marks the scan `PARTIAL`.
- PostgreSQL relation inventory: warned only on dedicated signal (`relation_inventory_complete is False`); generic
  incomplete catalog does not emit false relation inventory warnings.
- Limitations: parity with BootUI (distinct `WARNING`/`ERROR` diagnostics up to 20), without duplicate datasource scope notes.
- Masking: every diagnostic message passes through the masker in the production service scan path.

## Scenarios

| Scenario | Expected Behaviour |
|---|---|
| Fully populated driver (`sqlite://`, `aiosqlite`) | `complete=True`, status `SCANNED`, no driver warnings |
| Absent ORM models (`models=()`) or unconfigured mappers | Neutral `INFO` diagnostic on `SQLAlchemy metadata`; clean scan (`SCANNED`) when physical schema is complete |
| Failed ORM model discovery or invalid `models=` | `WARNING` diagnostic on `SQLAlchemy metadata`; scan status `PARTIAL`; `coverageComplete=False` |
| Missing driver name (`dialect.driver = None` or `""`) | `WARNING` diagnostic `"The database driver name was unavailable; driver settings are not evaluated."`; status `PARTIAL` |
| Missing driver version (no version anywhere) | `WARNING` diagnostic `"The database driver version was unavailable."`; status `PARTIAL` |
| Missing or unreadable URL (`url = None` or read raises) | `WARNING` diagnostic (`"The driver reported no database URL..."` or `"The database URL could not be read..."`); status `PARTIAL` |
| Scan with findings | `evidence.usable=True` (BootUI `doScan` parity) |
| Complete empty relation inventory (0 tables) | Datasource status `AVAILABLE`, `complete=True`; scan status `SCANNED` |
| Dedicated PostgreSQL incomplete inventory | `WARNING` diagnostic `"The PostgreSQL relation inventory is incomplete; some relations may be missing."` only when signaled |
| Limitations parity | Distinct WARNING/ERROR diagnostics only, no duplicate scope notes |
| Secret masking in diagnostics | No cleartext password appears in report JSON or logs |

## Changed Files

- `src/sharpit/engine/sqla/inspect.py`: Driver version lookup cascade (DBAPI `__version__`, `importlib.metadata`, `sqlite3.sqlite_version`), database driver/URL diagnostic wording.
- `src/sharpit/engine/collectors/database_advisor/rules_orm.py`: Unconfigured mappers as neutral INFO skip, invalid `models=` as WARNING with registries explanation.
- `src/sharpit/engine/collectors/database_advisor/report.py`: `usable` evaluation parity, limitations parity with BootUI, dedicated relation inventory check, simplified `complete` check, safe exception formatting.
- `tests/engine/collectors/database_advisor/test_incomplete_discovery.py`: Complete test coverage for incomplete discovery, driver versioning, and BootUI parity.
- `tests/fastapi/test_database_advisor_api.py`: Cleaned global test fixture patch.
- `docs/reference/matrix-updates/a4-db-advisor.tsv`: Parity matrix updates and deviation rows.
- `docs/superpowers/plans/2026-11-18-sharpit-0.7.0/A4-db-advisor.md`: Plan document.
- `CHANGELOG.md`: Changelog entry.

## Tasks

### Task 1: Driver metadata incomplete evidence checks
**Files:** `src/sharpit/engine/sqla/inspect.py`, `tests/engine/collectors/database_advisor/test_incomplete_discovery.py`.
- [x] Implement multi-step driver version resolution (DBAPI `__version__`, `importlib.metadata`, `sqlite3.sqlite_version`).
- [x] Adapt diagnostic wording from JDBC to database driver/URL.
- [x] Verify tests pass.

### Task 2: ORM / SQLAlchemy Model Discovery and Usable Parity
**Files:** `src/sharpit/engine/collectors/database_advisor/rules_orm.py`, `src/sharpit/engine/collectors/database_advisor/report.py`, `tests/engine/collectors/database_advisor/test_incomplete_discovery.py`.
- [x] Neutral INFO skip for unconfigured mappers and absent models; WARNING for invalid `models=`.
- [x] Match BootUI `usable` calculation (any rule evaluated).
- [x] Verify tests pass.

### Task 3: Limitations, PostgreSQL Relation Inventory, and Diagnostics Formatting
**Files:** `src/sharpit/engine/collectors/database_advisor/report.py`, `tests/engine/collectors/database_advisor/test_incomplete_discovery.py`.
- [x] Dedicated relation inventory check on PostgreSQL.
- [x] Limitations parity with BootUI.
- [x] Exception formatting with `type(exc).__name__`.
- [x] Production path masking verification.
- [x] Verify tests pass.
