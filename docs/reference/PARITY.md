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

## 0.7.0 against BootUI 2.4.0: deviations

Every deviation, partial implementation, adapted behavior, gap, or not-applicable item recorded across
the 0.7.0 lane fragments in `docs/reference/matrix-updates/` (29 entries):

| Lane | Key | Status | Reason |
|---|---|---|---|
| A1 | dto:CaughtExceptionsSummaryDto | gap | BootUI 2.4.0 added insufficient and partial integer counters; status gap: no caught-exception sensor in sharpit; src/sharpit/engine/capture/exceptions.py |
| A1 | dto:CaughtExceptionRowDto | gap | BootUI 2.4.0 added status, notRethrownOrLoggedRequests, minimumRequests; status gap: no caught-exception sensor in sharpit; src/sharpit/engine/capture/exceptions.py |
| A3 | rule:SEC-STATIC-001:description | adapted | Rule description adapted: Maven parent and Gradle applied script limitations replaced by Python boundaries (ruff.toml extend not followed, requirements -r includes not followed, remote or organization-managed configuration not resolved). |
| A4 | xc:database-advisor.partitioned-tables | partial | SQLAlchemy Inspector get_table_names() queries PostgreSQL relations in a single query without a separate getTableTypes() query or fallback; sharpit only warns of incomplete relation inventory when a dedicated relation_inventory_complete=False signal is present, never on generic truncated or complete=False |
| A4 | xc:database-advisor.driver-wording | adapted | BootUI JDBC driver diagnostic wording adapted to Python database terms (The database driver name was unavailable..., The database driver version was unavailable., The database URL could not be read..., The driver reported no database URL...) |
| A4 | xc:database-advisor.relation-inventory-observability | partial | The dedicated relation_inventory_complete signal has no producer under src/; incomplete PostgreSQL relation inventory is not yet observable |
| A5a | journal:late-attribution-completed-execution | n-a | BootUI 2.4.0 #1598 adds rememberCompletedExecution and a bounded expired-id set to JournalAggregates (JournalAggregatesTests.completedExecutionAttributesLateSqlToItsCompletedWork and two siblings). sharpit keeps no running aggregates and no producer sets executionId: SQL and connection events join their request by requestId at read time (engine/collectors/insights/requests.py), so a late event lands on its own request or stays unattributed and never opens an execution. Port with the aggregates if sharpit gains them. |
| A5a | journal:request-profile-timeline-tie-break | n-a | BootUI 2.4.0 orders the request-profile timeline by offsetMillis, then SQL execution start, then sequence (RequestJournalProfiles.java; RequestJournalProfilesTests.delayedSqlTimelineTiesUseExecutionStartRatherThanPublicationSequence, sqlMonotonicTieBreakDoesNotMoveItAheadOfNonSqlItems). sharpit's request profile (engine/capture/activity.py request_profile) has no journal timeline yet, so there is nothing to order; the comparator is ported with the timeline (a 0.7.0 gap). |
| A6 | ui:overview-run-all | n-a | BootUI 2.4.0 #1602 adds run-all scanner execution honoring panel action policy in Overview.vue; sharpit Overview displays application and sharpit status facts only without technology scanner scorecards or run-all button, so run-all panel policy filtering is not applicable |
| A7 | feature:http-exchange-recording-null-headers | n-a | BootUI 2.4.0 skips null header names in HttpServletRequest/HttpServletResponse (BootUiHttpExchangesFilterTests.skipsNullRequestHeaderNamesWithoutLosingValidHeaders, skipsNullResponseHeaderNamesWithoutLosingValidHeadersOrTheServedBody); in ASGI 3.0, scope and response headers are binary (bytes, bytes) pairs and null header names cannot occur. |
| A7 | feature:http-exchange-recording-warning-text | partial | BootUI logs "BootUI skipped an HTTP exchange capture (X)" through one message for every recording failure; sharpit logs one warning per hook name ("sharpit capture hook request end failed (X); capture continues", "request start", "response"), so the failing step is named and a repeat of the same failure stays quiet; both log the exception class only. |
| A7 | feature:http-exchange-recording-response-stamp | partial | When only the response-capture clock read fails, BootUI records no exchange (callbackRegistrationFailureStillServesTheResponse); sharpit logs the "response" hook failure, serves the response and still records the exchange at request end with the finish time taken there, because the row needs no callback registration. |
| B1 | kind:unbatched-write-loop | partial | Request ids gate correlation; unreadable SQL that might be a write and executed writes without batch size remain uncounted, with their reason reported. |
| B1 | kind:unbatched-write-loop:grouping | partial | sharpit does not group SQL executions by transaction, so the BootUI transaction grouping limitation is reported and counts remain per request. |
| B1 | kind:unbatched-write-loop:advice | partial | Java framework and JDBC batching advice is adapted to SQLAlchemy and DB-API equivalents. |
| B1 | kind:unbatched-write-loop:masked-sentence | partial | When the recorded SQL shape contains the mask marker, the sentence uses a generic shape label to keep the mask from truncating or exposing the surrounding sentence. |
| B1 | kind:repeated-selects | partial | Request ids gate correlation; masked or unsupported SQL, set operations and truncated statements are counted as unreadable. |
| B1 | kind:repeated-selects:masked-sentence | partial | When the recorded SQL shape contains the mask marker, the sentence uses a generic shape label to keep the mask from truncating or exposing the surrounding sentence. |
| B1 | kind:repeated-selects:transaction-columns | partial | sharpit does not record BootUI request phase or transaction placement for SQL rows; both columns remain present with the unknown value. |
| B1 | kind:repeated-selects:call-site | partial | sharpit journal rows provide one call-site value per execution but no issuing-method stamps; the most frequent recorded call site is shown. |
| B1 | kind:paged-without-order | partial | Deferred until BootUI SQL row-limit and shape analysis is ported; regex approximation is inaccurate under default masking. |
| B1 | kind:proxy-bypass | n-a | sharpit SQL events do not record application frames, so annotated proxy boundaries cannot be resolved. |
| B1 | kind:event-loop-blocking | n-a | sharpit SQL events do not classify threads as event-loop threads; a thread name cannot prove that JDBC blocked an event loop. |
| E1 | gate:advisor-partial-status | partial | BootUI 2.4.0 FailOn exits 3 on a counted finding; sharpit leaves the exit status to pytest and exits 1 (AGENTS.md: pytest owns the exit code) |
| E1 | gate:advisor-merge-partial | partial | sharpit's own: session, app and worker statuses merge worst first, FAILED, UNKNOWN, SKIPPED, PARTIAL, PASSED, and one warning per partial app; BootUI has one scan |
| E1 | gate:advisor-rule-error | partial | BootUI reports a rule that throws as a PARTIAL scan; sharpit keeps the advisor UNKNOWN because the rule that errored may be the one that finds the problem (the REST API report still says PARTIAL) |
| E1 | gate:advisor-unusable-no-limitation | partial | An advisor that is not usable and lists no limitation is unchanged (PASSED when coverage is complete); BootUI treats zero usable evidence as unevaluable |
| E1 | gate:advisor-introspection-failure | partial | Only an opaque mounted app makes an advisor PARTIAL; an unread router, exception handler or route is sharpit failing to assess (safety model 5) and stays UNKNOWN; BootUI lists every limitation as PARTIAL |
| E2 | advisor-finding-identity:sharpit.swallowed-exception | partial | A fix of an open sharpit bug (#66, the identity held the line of the except header), not a port: BootUI 2.4.0 has no counterpart to settle it, its caught-exception site key keeps the line (CaughtOutcomes.java:746-748, siteKey). The identity follows the principle of AdvisorFindingIdentity.java (structure-derived, never from the order of observation) in sharpit's own plain form <path>:<scope qualified name>:<Type>#<key>, at most 512 characters, with no v1: version prefix and no percent-encoding, because the dismissedFindings store of 0.4.0 to 0.6.0 already holds plain identities. The key is a hash of the clause's try body and handler without positions, so a swap or a log moved between clauses cannot hand a dismissal over; the line-keyed form no longer dismisses and only produces a warning. |
