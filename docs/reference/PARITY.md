# BootUI 2.2.0 panel parity

> The 0.5.0 record against BootUI 2.2.0. For where sharpit stands now (0.6.0 against BootUI 2.3.0 and 2.4.0), see
> [ROADMAP.md](../../ROADMAP.md).

Every panel id in BootUI 2.2.0 (`tests/fixtures/bootui/2.2.0/ids.json`) and where sharpit stands on it at 0.5.0.

The D2 and D4 drift lanes (capture panels; `vulnerabilities`, `mcp-server`, `rest-api`) added no new golden captures. The goldens in `tests/fixtures/bootui/2.2.0/` are the 2026-11-02 captures; the drift lanes added `nullable.json` key reasons and parity or key-presence tests against those captures, so the counts below did not move. "Drift done" means every key and route in the drift plans that sharpit can fill; what it cannot (memory keys and the journal on `activity`, CVSS v4.0 score selection and `sampleLocations` on `vulnerabilities` and `rest-api`) is in the 0.5.0 changelog.

Not built on panels counted `shipped`: `GET /activity/service-map`, `GET /activity/request/{id}/journal` and `GET /rest-api/error-contract`. `service-map.captured.json` and `error-contract.captured.json` are the only captured goldens with no live parity call, named in `tests/test_conformance.py::NOT_LIVE_2_2_0`. `activity` is checked with `typeCounts` completed from the golden, because that map's keys are the types seen; sharpit's feed has no `TRANSACTION`, `SECURITY`, `MESSAGING` or `MARKER` entries.

| Status | Meaning |
|---|---|
| `shipped` | implemented; a golden `captured.json` covers what the panel returns and the panel's parity test passes |
| `shipped (unverified golden)` | implemented; no golden, an empty one, or only a pre-scan/pre-read golden for a panel whose content comes from a scan or read (post-scan golden waits for G0) |
| `not built` | no implementation |

| BootUI id | sharpit id | Status | Lane | Evidence / note |
|---|---|---|---|---|
| `overview` | `overview` | shipped | 0.3.0 | |
| `config` | `config` | shipped | 0.3.0 | source reads moved to the bounded app-source index (F5a-source) |
| `mappings` | `mappings` | shipped | 0.3.0 | introspection hardened (R-fastapi-security) |
| `loggers` | `loggers` | shipped | 0.3.0 | |
| `beans` | `beans` | shipped | 0.3.0 | `resource` no longer reads source (R-fastapi-security) |
| `vulnerabilities` | `vulnerabilities` | shipped (unverified golden) | 0.3.0 | golden is a failed-scan capture, so items are unchecked (`tests/engine/vulns/test_service.py::test_vulnerabilities_golden_parity_after_drift`); post-scan recapture is G0 (owner); 2.2.0 drift done (D4) |
| `mcp-server` | `mcp-server` | shipped | 0.3.0; drift D4 | `tests/fastapi/test_mcp_api.py::test_mcp_server_golden_parity_after_drift`; 2.2.0 drift done |
| `cli` | `cli` | shipped | 0.3.0 | |
| `activity` | `activity` | shipped | 0.3.0 | `captured.json` populated (`test_capture_golden_parity.py`), `journal.captured.json`, `resources.captured.json`; `tests/fastapi/test_activity_api.py::test_activity_journal_golden_parity`, `::test_activity_resources_golden_parity`; 2.2.0 drift done (D2) |
| `http-exchanges` | `http-exchanges` | shipped | 0.3.0 | `routes.captured.json`; `tests/fastapi/test_http_exchanges_api.py::test_http_routes_golden_parity`; 2.2.0 drift done (D2) |
| `exceptions` | `exceptions` | shipped | 0.3.0 | `captured.json` populated (`test_capture_golden_parity.py`), `caught.captured.json`; `tests/fastapi/test_exceptions_api.py::test_exceptions_caught_golden_parity`; 2.2.0 drift done (D2) |
| `sql-trace` | `sql-trace` | shipped | 0.3.0; insights A-sqltrace-insights | `captured.json` populated (`test_capture_golden_parity.py`), `insights.captured.json`; `tests/fastapi/test_sql_trace_insights_api.py::test_insights_golden_parity`; other 2.2.0 drift done (D2) |
| `log-tail` | `log-tail` | shipped | 0.3.0 | `recent.captured.json`; `tests/fastapi/test_log_tail_api.py::test_log_tail_recent_golden_parity`; 2.2.0 drift done (D2) |
| `flyway` | `alembic` | shipped (unverified golden) | 0.3.0; drift D3 | no 2.2.0 golden: BootUI's capture app runs Liquibase (`meta.json` `uncaptured`) |
| `database-connection-pools` | `database-connection-pools` | shipped | 0.3.0; drift D3 | `pools.captured.json` |
| `health` | `health` | shipped | 0.3.0; drift D3 | |
| `threads` | `threads` | shipped | 0.3.0; drift D3 | |
| `rest-api` | `rest-api` | shipped | 0.3.0; core F5a-core; drift D4 | post-scan golden checked by `test_advisor_core_matches_rest_api_post_scan_golden` and `tests/engine/restapi/test_restapi_report.py::test_rest_api_golden_parity_after_drift`; 2.2.0 drift done |
| `http-probe` | `http-probe` | shipped | 0.3.0 | |
| `data` | `data` | shipped (unverified golden) | 0.4.0 A-data | golden list empty (`total: 0`); V-unverified parked until G0 |
| `transactions` | `transactions` | shipped | R-transactions | `transactions/captured.json`; `tests/fastapi/test_transactions_api.py::test_report_golden_parity` |
| `postgresql` | `postgresql` | shipped | 0.4.0 A-postgresql | `postgresql/captured.json`; `tests/fastapi/test_postgresql_api.py::test_golden_parity` |
| `mysql` | `mysql` | shipped (unverified golden) | A-mysql (on F5b) | golden is pre-read (`NOT_READ`); post-read golden needs a MySQL datasource on the reference app (G0, owner); leased MySQL 8.4 tests passed |
| `traces` | `traces` | shipped | 0.4.0 A-traces | `traces/captured.json`; needs the OpenTelemetry SDK in the host app |
| `security` | `security` | shipped (unverified golden) | B-security | pre-scan golden passes; `test_post_scan_golden_parity` skips (G0) |
| `security-logs` | `security-logs` | shipped | B-security-logs | `security-logs/captured.json`; `tests/fastapi/test_security_logs_api.py::test_report_golden_parity` |
| `database-advisor` | `database-advisor` | shipped (unverified golden) | A-dbadv-1, A-dbadv-2 | pre-scan golden passes; `test_post_scan_golden_parity` skips (G0); leased PostgreSQL 17 + MySQL 8.4 passed |
| `architecture` | `architecture` | shipped (unverified golden) | C-architecture | pre-scan golden passes; post-scan golden absent (G0) |
| `hibernate-statistics` | `sqlalchemy-statistics` | shipped (unverified golden) | 0.4.0 A-sqlalchemy-statistics | no BootUI golden: tiny-ledger has no Hibernate statistics (`meta.json` `uncaptured`); V-unverified parked |
| `spring-security` | `fastapi-security` | shipped | R-fastapi-security | `fastapi-security/captured.json`, `endpoints.captured.json`; `tests/fastapi/test_fastapi_security_api.py::test_report_golden_parity`, `::test_endpoints_golden_parity` |
| `spring` | `fastapi` | shipped (unverified golden) | C-fastapi | pre-scan golden passes; post-scan golden absent (G0); 6 rules parked as C-fastapi-2 |

## Counts (31 panels)

| Status | Panels | Count |
|---|---|---|
| shipped | overview, config, mappings, loggers, beans, mcp-server, cli, activity, http-exchanges, exceptions, sql-trace, log-tail, database-connection-pools, health, threads, rest-api, http-probe, transactions, postgresql, traces, security-logs, fastapi-security | 22 |
| shipped (unverified golden) | vulnerabilities, alembic, data, mysql, security, database-advisor, architecture, sqlalchemy-statistics, fastapi | 9 |
| not built | (none) | 0 |

Check: 22 + 9 + 0 = 31.

Parity (panels shipped of 31): (22 + 9) / 31 = 31 / 31 = **100%**.
Verified parity (shipped with a checked golden): 22 / 31 = **71.0%** (22 ÷ 31 = 0.7097).

The 0.5.0 release fix round did not move this count. `activity`, `exceptions` and `sql-trace` were already counted as verified, but only their `journal`, `resources`, `caught` and `insights` goldens were checked: their main reports failed once populated. They now pass populated (`tests/fastapi/test_capture_golden_parity.py`), so those three rows earn the status they already had. `beans`, `cli`, `config`, `dismissed-*`, `http-probe`, `loggers`, `mappings` and `panels` gained their first 2.2.0 live check (`tests/fastapi/test_panel_golden_parity.py`).

For comparison, 0.4.0: implemented 19 + 2 + 2 = 23 of 31 (74.2%); verified 19 + 2 = 21 of 31 (67.7%) as that file
counted the 0.3.0 rows. Under this file's stricter rule (vulnerabilities and alembic unverified), 0.4.0 verified would
be 19 of 31 (61.3%).

New in 0.5.0: transactions, mysql, security, security-logs, database-advisor, architecture, fastapi-security, fastapi
(8 panels). Not a panel, shipped in 0.5.0: SQL Trace insights (part of `sql-trace`), `record_security_event`, the
`sharpit.unbounded-read` gate.

Each 0.4 panel's implemented flag is in `src/sharpit/engine/panels04/<id>.py`; `GET /sharpit/api/panels` is the
runtime answer.
