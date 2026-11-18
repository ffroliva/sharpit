# A4: Database advisor incomplete discovery (BootUI 2.4.0 #1600)

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit. Read the named BootUI files at `v2.4.0` in a BootUI clone; never from a summary.

**Goal:** Database advisor discovery is honest about what could not be inspected. Incomplete evidence (missing
driver name, version, or URL; failed ORM model discovery; or cut/failed PostgreSQL relation inventory) never reads
as a clean scan (`SCANNED`), but stays `PARTIAL` with explicit `WARNING` diagnostics and incomplete coverage. Absent
SQLAlchemy models remain a neutral `INFO` skip that does not degrade an otherwise complete scan.

**Architecture:**
- Driver evidence (`engine.dialect.driver`, the DBAPI module's `__version__`, `engine.url`): missing or blank
  emits BootUI's exact warning text, marking the datasource and overall scan as `PARTIAL`.
- ORM metadata: absence of models/registries is confirmed absent (`INFO` diagnostic), while an exception or
  failure during model discovery emits a `WARNING` diagnostic and marks the scan `PARTIAL`, even with zero models.
- PostgreSQL relation inventory: an incomplete inventory (cut by bounds or statement failure) adds a `WARNING`
  diagnostic and marks scope unverified; a complete empty inventory (0 tables) leaves an otherwise complete
  datasource `AVAILABLE` and `SCANNED`.
- Masking: every diagnostic message passes through the masker; URLs and credentials never appear in diagnostics.

## Scenarios

| Scenario | Expected Behaviour |
|---|---|
| Absent ORM models (`models=()`) | Neutral `INFO` diagnostic on `SQLAlchemy metadata`; clean scan (`SCANNED`) when physical schema is complete |
| Failed ORM model discovery (raises `Exception`) | `WARNING` diagnostic on `SQLAlchemy metadata`; scan status `PARTIAL`; `coverageComplete=False`, even with 0 entities |
| Missing driver name (`dialect.driver = None` or `""`) | `WARNING` diagnostic `"The JDBC driver name was unavailable; driver settings are not evaluated."`; status `PARTIAL` |
| Missing driver version (DBAPI `__version__` absent or `""`) | `WARNING` diagnostic `"The JDBC driver version was unavailable."`; status `PARTIAL` |
| Missing or unreadable URL (`url = None` or read raises) | `WARNING` diagnostic (`"The driver reported no JDBC URL..."` or `"The JDBC URL could not be read..."`); status `PARTIAL` |
| Complete empty relation inventory (0 tables) | Datasource status `AVAILABLE`, `complete=True`; scan status `SCANNED`; does not make datasource `PARTIAL` |
| Incomplete PostgreSQL relation inventory (cut/failed) | `WARNING` diagnostic `"The PostgreSQL relation inventory is incomplete; some relations may be missing."`; scope unverified |
| Secret masking in diagnostics | No cleartext password or unmasked URL appears in any new diagnostic |

## Tasks

### Task 1: Driver metadata incomplete evidence checks

**Files:** `src/sharpit/engine/sqla/inspect.py`, `src/sharpit/engine/collectors/database_advisor/catalog.py`,
`tests/engine/collectors/database_advisor/test_incomplete_discovery.py`.

- [x] **Step 1:** Write the failing tests in `tests/engine/collectors/database_advisor/test_incomplete_discovery.py`:
  - `test_missing_driver_metadata_is_reported_as_incomplete_evidence` (`# ported: SchemaIntrospectorTests.missingDriverMetadataIsReportedAsIncompleteEvidence`)
  - `test_null_driver_name_is_reported_as_incomplete_evidence` (`# ported: SchemaIntrospectorTests.nullDriverNameIsReportedAsIncompleteEvidence`)
  - `test_null_driver_version_is_reported_as_incomplete_evidence` (`# ported: SchemaIntrospectorTests.nullDriverVersionIsReportedAsIncompleteEvidence`)
  - `test_a_null_url_is_a_warning_and_makes_evidence_incomplete` (`# ported: SchemaIntrospectorDriverEvidenceTests.aNullUrlIsAWarningAndMakesEvidenceIncomplete`)
- [x] **Step 2:** Verify the reds with `uv run python scripts/dev/red_check.py`.
- [x] **Step 3:** Implement driver metadata evaluation in `src/sharpit/engine/sqla/inspect.py` and `catalog.py`.
- [x] **Step 4:** Run tests and commit `feat: report missing driver metadata as incomplete evidence`.

### Task 2: ORM / SQLAlchemy Model Discovery (Absent vs Failed)

**Files:** `src/sharpit/engine/collectors/database_advisor/rules_orm.py`, `src/sharpit/engine/collectors/database_advisor/report.py`,
`tests/engine/collectors/database_advisor/test_incomplete_discovery.py`.

- [x] **Step 1:** Write the failing test:
  - `test_distinguishes_absent_jpa_from_a_zero_entity_discovery_failure` (`# ported: DatabaseAdvisorScannerTests.distinguishesAbsentJpaFromAZeroEntityDiscoveryFailure`)
- [x] **Step 2:** Verify the red with `uv run python scripts/dev/red_check.py`.
- [x] **Step 3:** Implement confirmed absent (`INFO`) vs failed (`WARNING`) in `rules_orm.facts` and `report.evaluate`.
- [x] **Step 4:** Run tests and commit `feat: distinguish absent ORM metadata from failed model discovery`.

### Task 3: PostgreSQL relation inventory and empty inventory handling

**Files:** `src/sharpit/engine/collectors/database_advisor/catalog.py`, `src/sharpit/engine/collectors/database_advisor/report.py`,
`tests/engine/collectors/database_advisor/test_incomplete_discovery.py`.

- [x] **Step 1:** Write the failing tests:
  - `test_incomplete_postgres_relation_inventory_is_not_complete_evidence` (`# ported: SchemaIntrospectorTests.incompletePostgresRelationInventoryIsNotCompleteEvidence`)
  - `test_complete_empty_relation_inventory_does_not_make_an_otherwise_complete_datasource_partial` (`# ported: SchemaIntrospectorTests.completeEmptyRelationInventoryDoesNotMakeAnOtherwiseCompleteDatasourcePartial`)
- [x] **Step 2:** Verify the reds with `uv run python scripts/dev/red_check.py`.
- [x] **Step 3:** Implement PostgreSQL relation inventory check and message diagnostics in `report.py` / `catalog.py`.
- [x] **Step 4:** Run tests and commit `feat: report incomplete PostgreSQL relation inventory`.

### Task 4: Masking, Parity matrix update, CHANGELOG, and gate verification

**Files:** `docs/reference/matrix-updates/a4-db-advisor.tsv`, `CHANGELOG.md`, `tests/masking/test_a_database_advisor_masking.py`,
`tests/engine/collectors/database_advisor/test_incomplete_discovery.py`.

- [x] **Step 1:** Add a masking test asserting no unmasked URLs or credentials in any new diagnostic.
- [x] **Step 2:** Create `docs/reference/matrix-updates/a4-db-advisor.tsv` with Python adaptations and partitioned tables deviation.
- [x] **Step 3:** Update `CHANGELOG.md` under `[Unreleased]`.
- [x] **Step 4:** Run full lane gates, lint (`ruff check`), format (`ruff format --check`), and type check (`pyright`).
- [x] **Step 5:** Commit docs and matrix updates.
