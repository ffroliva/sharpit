# BootUI 2.2.0 panel parity

Every panel id in BootUI 2.2.0 (`tests/fixtures/bootui/2.2.0/ids.json`) and where sharpit stands on it at 0.4.0.

| Status | Meaning |
|---|---|
| `existing (0.3.0)` | shipped before 0.4.0 |
| `parity` | implemented in 0.4.0; a golden `captured.json` exists and the panel's parity test passes |
| `unverified` | implemented in 0.4.0; no golden, a provisional one, or a golden the parity test cannot check item by item |
| `parked` | lane started and parked in the 0.4.0 night; not available |
| `not started` | planned for 0.4.x; no implementation |

| BootUI id | sharpit id | Status | Evidence |
|---|---|---|---|
| `overview` | `overview` | existing (0.3.0) | |
| `config` | `config` | existing (0.3.0) | |
| `mappings` | `mappings` | existing (0.3.0) | |
| `loggers` | `loggers` | existing (0.3.0) | |
| `beans` | `beans` | existing (0.3.0) | |
| `vulnerabilities` | `vulnerabilities` | existing (0.3.0) | |
| `mcp-server` | `mcp-server` | existing (0.3.0) | |
| `cli` | `cli` | existing (0.3.0) | |
| `activity` | `activity` | existing (0.3.0) | |
| `http-exchanges` | `http-exchanges` | existing (0.3.0) | |
| `exceptions` | `exceptions` | existing (0.3.0) | |
| `sql-trace` | `sql-trace` | existing (0.3.0) | |
| `log-tail` | `log-tail` | existing (0.3.0) | |
| `flyway` | `alembic` | existing (0.3.0) | no 2.2.0 golden: BootUI's capture app runs Liquibase (`meta.json` `uncaptured`) |
| `database-connection-pools` | `database-connection-pools` | existing (0.3.0) | |
| `health` | `health` | existing (0.3.0) | |
| `threads` | `threads` | existing (0.3.0) | |
| `rest-api` | `rest-api` | existing (0.3.0) | |
| `http-probe` | `http-probe` | existing (0.3.0) | |
| `data` | `data` | unverified | `data/repositories.captured.json` exists and `tests/fastapi/test_data_api.py::test_repositories_golden_parity` passes, but the golden list is empty (`total: 0`), so items are unchecked (`UnverifiedParityWarning`) |
| `transactions` | `transactions` | parked | lane parked 2026-11-02 (review changes, design-level fixes) |
| `postgresql` | `postgresql` | parity | `postgresql/captured.json`; `tests/fastapi/test_postgresql_api.py::test_golden_parity` passes; field map in the A-postgresql lane |
| `mysql` | `mysql` | not started | |
| `traces` | `traces` | parity | `traces/captured.json`; `tests/fastapi/test_traces_api.py::test_golden_parity` and `::test_detail_matches_the_bootui_span_records` pass; needs the OpenTelemetry SDK in the host app |
| `security` | `security` | not started | |
| `security-logs` | `security-logs` | not started | |
| `database-advisor` | `database-advisor` | not started | |
| `architecture` | `architecture` | not started | |
| `hibernate-statistics` | `sqlalchemy-statistics` | unverified | implemented in 0.4.0; no BootUI golden: tiny-ledger has no Hibernate statistics (`tests/fixtures/bootui/2.2.0/meta.json` `uncaptured`) |
| `spring-security` | `fastapi-security` | not started | |
| `spring` | `fastapi` | not started | |

Counts (31 panels): existing (0.3.0) 19, parity 2, unverified 2, parked 1, not started 7.

Not a panel, shipped in 0.4.0: the GitHub Action and job summary (lane G3).

Each 0.4 panel's implemented flag is in `src/sharpit/engine/panels04/<id>.py`; `GET /sharpit/api/panels` is the
runtime answer.
