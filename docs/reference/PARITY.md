# BootUI 2.2.0 panel parity

> The 0.5.0 record against BootUI 2.2.0. For where sharpit stands now (0.8.0 against BootUI 2.5.0), see
> [ROADMAP.md](../../ROADMAP.md). The 0.8.0 static pin targets BootUI 2.5.0; live route status remains measured
> against the 2.3.0 goldens until the 2.5.0 reference-app capture is available.

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
the 0.7.0 lane fragments in `docs/reference/matrix-updates/` (117 entries):

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
| C | cli:bounded-client-api | adapted | Per-call byte caps and timeout overrides are omitted because BootUI uses them only for the excluded `ci` command; normal `get` and `invoke` read the complete response. |
| C | cli-t3-catalog-validation | partial | Catalog validation moved to Client.catalog so every caller receives a validated sharpit catalog. |
| C | cli-t3-outcome-message | partial | Python carries ToolResult.raw_body and payload; classify reads the decoded client payload and applies the client's redaction helpers. |
| C | cli-t3-refusal-shape | partial | The FastAPI guard's /cli/tools refusal body has only error; the reason is therefore taken from that server-provided text. |
| C | cli:data repositories | n-a | sharpit-only tool (get_data_repositories); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:db alembic | n-a | sharpit-only tool (get_alembic_migrations); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:fastapi report | n-a | sharpit-only tool (get_fastapi_report); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:fastapi scan | n-a | sharpit-only tool (fastapi_scan); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:fastapi violations | n-a | sharpit-only tool (get_fastapi_rule_violations); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:fastapi-security | n-a | sharpit-only tool (get_fastapi_security); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:sql-trace insights | n-a | sharpit-only tool (get_sql_trace_insights); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:sqlalchemy-statistics list | n-a | sharpit-only tool (get_sqlalchemy_statistics); no BootUI command, path chosen in sharpit.engine.tools COMMANDS; both tools are sharpit-only, so the read is `<noun> list` beside the action `<noun> <verb>`; the bare noun was a prefix of the action path |
| C | cli:sqlalchemy-statistics enable | n-a | sharpit-only tool (enable_sqlalchemy_statistics); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | manifest:stacks | n-a | BootUI records the stacks that advertise each tool; sharpit has one stack, so the manifest has no stacks field and the stack-specific test is not ported |
| C | manifest:idHelp-queryHelp | gap | BootUI's generator adds idHelp and queryHelp from McpToolGuide; sharpit has no such guide yet, so the fields are omitted (BootUI omits them when it has none) |
| C | manifest:example | partial | BootUI writes a hand-made example per tool (McpToolGuide.example); sharpit generates `sharpit <command>` plus the id and --scan-id placeholders from the schema |
| C | manifest:arguments-required | partial | sharpit adds `arguments` (the wire names, camelCase as the tool schema declares them) and `required` so the CLI sends exactly what is supplied and refuses a missing required argument; BootUI's CLI derives them from the schema name |
| C | cli:argparse-picocli | adapted | Python standard library argparse used instead of JVM picocli to satisfy standard-library-only rule (AGENTS.md rule 4) |
| C | cli:command-ci-docs-update | n-a | BootUI's ci, docs and update commands are excluded from sharpit per design decisions 2 and CLI scope |
| C | cli:tool-compare-thread-analysis | n-a | BootUI's insights compare and thread-analysis commands have no sharpit counterparts, so CommandTreeTests cases for them are skipped |
| C | cli:the-command-listing-tags-action | adapted | action tagging ported on individual tool help; full listing tags deferred to Task 7 HelpListing |
| C | cli:missing-id-hint | adapted | usage error requires <id>; tools.json lacks BootUI idHelp property so detailed id source hint is omitted |
| C | cli:fail-on-tools-fastapi | adapted | fastapi_scan and get_fastapi_report added to ADVISOR_TOOLS for FastAPI framework advisor |
| C | cli:fail-on-tools-dropped | adapted | crac, graalvm, hibernate, memory, pentest, spring advisor tools dropped as absent from sharpit |
| C | cli:fail-on-tools-heap-dump | adapted | BootUI lists get_heap_dump_report in EXCLUDED; dropped because sharpit provides no heap dump analysis tool |
| C | cli:fail-on-exceptions-sensor | adapted | get_exceptions removed from insufficient-criterion tools: sharpit records no caught-in-code evidence, so this gate cannot be evaluated (usage error) |
| C | cli:fail-on-pytest-gate-comparison | n-a | note: CLI follows BootUI exactly (gates on INFO; scan status ERROR exits 1 unevaluable regardless of findings); the pytest gate follows the 0.4.0 ruling (INFO notes-only, ERROR with findings fails) |
| C | cli-t7-render | adapted | Machine output preserves UTF-8 bytes; terminal text replaces unencodable characters; BootUI writes through UTF-8 PrintWriter. |
| C | cli-t7-entry | adapted | Python package and console-script entry points replace BootUI's JVM main entry. |
| C | cli-t7-unknown-tool | adapted | a catalog-listed tool returning 404 keeps its server message; an unlisted tool gets a static hint from local CLI metadata without a /panels request. |
| C | cli-t7-redaction | adapted | Server JSON bytes remain verbatim except at token occurrences: string contents and object keys are replaced in place, and a matching number literal becomes the string "[redacted]". Terminal-rendered payloads and CLI-generated messages are redacted before output; invalid JSON receives plain-text redaction. Token-redacted JSON preserves every nonmatching source byte. |
| C | cli-t7-root-fail-on | adapted | Root-level --fail-on remains hidden for leading-option placement and is validated by the selected tool's FailOn parser. |
| C | cli-t7-unknownToolHint | adapted | When a bundled tool is unlisted, the CLI emits a static version hint without a /panels request; its manifest lacks BootUI stack metadata. |
| C | cli:no-update-ci-docs | n-a | BootUI provides update, ci and docs commands; sharpit omits update (no self-updating network binary), ci (orchestration beyond single-query CLI scope) and docs (no offline JVM documentation server). |
| C | cli:no-update-check | adapted | BootUI checks remote registry for updates on CLI invocations; sharpit performs no update check to prevent unexpected outbound network traffic during local tool invocations (AGENTS.md safety rule 6). |
| C | cli:argparse-picocli | adapted | Python standard library argparse replaces JVM picocli to satisfy standard-library-only rule for the CLI package (AGENTS.md architecture rules 2 and 4). |
| C | cli:token-env-recommendation | adapted | --token CLI option is supported and takes precedence over SHARPIT_TOKEN, but SHARPIT_TOKEN is recommended in documentation because command-line arguments are visible in host process listings to other users. |
| C | cli:sharpit-only-commands | n-a | 9 sharpit-only command paths from manifest: db alembic (get_alembic_migrations), data repositories (get_data_repositories), sqlalchemy-statistics list (get_sqlalchemy_statistics), sqlalchemy-statistics enable (enable_sqlalchemy_statistics), fastapi-security (get_fastapi_security), fastapi report (get_fastapi_report), fastapi violations (get_fastapi_rule_violations), fastapi scan (fastapi_scan), sql-trace insights (get_sql_trace_insights). |
| C | cli:db alembic | n-a | sharpit-only tool (get_alembic_migrations); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:data repositories | n-a | sharpit-only tool (get_data_repositories); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:sqlalchemy-statistics list | n-a | sharpit-only tool (get_sqlalchemy_statistics); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:sqlalchemy-statistics enable | n-a | sharpit-only tool (enable_sqlalchemy_statistics); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:fastapi-security | n-a | sharpit-only tool (get_fastapi_security); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:fastapi report | n-a | sharpit-only tool (get_fastapi_report); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:fastapi violations | n-a | sharpit-only tool (get_fastapi_rule_violations); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:fastapi scan | n-a | sharpit-only tool (fastapi_scan); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| C | cli:sql-trace insights | n-a | sharpit-only tool (get_sql_trace_insights); no BootUI command, path chosen in sharpit.engine.tools COMMANDS |
| E1 | gate:advisor-partial-status | partial | BootUI 2.4.0 FailOn exits 3 on a counted finding; sharpit leaves the exit status to pytest and exits 1 (AGENTS.md: pytest owns the exit code) |
| E1 | gate:advisor-merge-partial | partial | sharpit's own: session, app and worker statuses merge worst first, FAILED, UNKNOWN, SKIPPED, PARTIAL, PASSED, and one warning per partial app; BootUI has one scan |
| E1 | gate:advisor-rule-error | partial | BootUI reports a rule that throws as a PARTIAL scan; sharpit keeps the advisor UNKNOWN because the rule that errored may be the one that finds the problem (the REST API report still says PARTIAL) |
| E1 | gate:advisor-unusable-no-limitation | partial | An advisor that is not usable and lists no limitation is unchanged (PASSED when coverage is complete); BootUI treats zero usable evidence as unevaluable |
| E1 | gate:advisor-introspection-failure | partial | Only an opaque mounted app makes an advisor PARTIAL; an unread router, exception handler or route is sharpit failing to assess (safety model 5) and stays UNKNOWN; BootUI lists every limitation as PARTIAL |
| E2 | advisor-finding-identity:sharpit.swallowed-exception | partial | A fix of an open sharpit bug (#66, the identity held the line of the except header), not a port: BootUI 2.4.0 has no counterpart to settle it, its caught-exception site key keeps the line (CaughtOutcomes.java:746-748, siteKey). The identity follows the principle of AdvisorFindingIdentity.java (structure-derived, never from the order of observation) in sharpit's own plain form <path>:<scope qualified name>:<Type>#<key>, at most 512 characters, with no v1: version prefix and no percent-encoding, because the dismissedFindings store of 0.4.0 to 0.6.0 already holds plain identities. The key is a hash of the clause's try body and handler without positions, so a swap or a log moved between clauses cannot hand a dismissal over; the line-keyed form no longer dismisses and only produces a warning. |
| G1 | docs:playbook-database-efficiency | partial | SQLAlchemy, SQL trace, N+1 and implemented insight kinds ported; Hibernate-specific tools and transaction grouping limitations adapted to SQLAlchemy and DB-API. |
| G1 | docs:playbook-slow-endpoint | partial | Activity, request profile, route rankings, threads and asyncio task inspection ported; BootUI Java bytecode agent code paths tool is not available in sharpit. |
| G1 | docs:playbook-verify-my-changes | partial | Overview, configuration profile diff, runtime insights, request profile, and SQL traces ported; BootUI Java bytecode agent code inventory and side effects tools are not available in sharpit. |
| G1 | docs:playbook-jvm-performance-and-memory | n-a | BootUI playbook covers JVM-specific GC, HPROF heap dumps, JFR profiler, and NMT; replaced by python-performance-and-memory. |
| G1 | docs:playbook-python-performance-and-memory | partial | New Python/FastAPI performance and memory playbook based on real sharpit evidence: threads, asyncio task states, SQL timing, request profile; notes absence of Python heap dumps or bytecode profilers. |
| G1 | docs:recipe-did-my-change-run | partial | sharpit verifies via request configuration profile diff, route replay, and advisor rescans; Java bytecode agent code inventory is not available in sharpit. |
| G1 | docs:recipe-handler-timing | partial | sharpit provides request-profile SQL duration breakdown and thread/asyncio task inspection; Java agent bytecode method self-time code paths are not available. |
| G1 | docs:recipe-attach-java-agent | n-a | Java bytecode agent is specific to Spring Boot and JVM runtimes; sharpit runs in Python and FastAPI with no Java agent. |
| G1 | docs:recipe-check-method-probe | n-a | Java agent method probes with dynamic bytecode instrumentation are not applicable to the Python runtime. |
| G1 | docs:recipe-side-effects | n-a | Java agent side-effect sensors for OS processes, network sockets, and file handles are not implemented in sharpit. |
| G1 | docs:recipe-mysql-operational-evidence | partial | get_mysql_report provides bounded operational metrics and server variables. |
| G1 | docs:recipe-investigate-blocked-thread | partial | get_threads provides thread states, stacks, and asyncio event-loop task await chains. |
| G1 | docs:recipe-tools-agent-can-call | partial | MCP exposes reads; CLI actions require approval. |
| G1 | docs:recipe-compact-answers | partial | Bounded DTOs exist; BootUI compact-answer facility does not. |
| G1 | docs:recipe-protocol-eras | n-a | No corresponding sharpit protocol eras. |
| G2 | mcp:prompt-diagnose_runtime_issue | partial | Replaces BootUI-only code-path inventory and request-input sink evidence with available request profiles, traces, SQL traces, logs, and an explicit unavailable-evidence statement. |
| G2 | mcp:prompt-diagnose_runtime_issue | partial | Changes Java-agent wording and BootUI evidence references to sharpit runtime evidence; sharpit does not collect the named code-path or sink signals. |
| G2 | mcp:prompt-diagnose_runtime_issue | partial | Omits JDK-only deserialization filters, weak-algorithm and trust-manager checks because sharpit has no matching runtime sensor; security findings remain source/configuration checks. |
| G2 | mcp:prompt-diagnose_runtime_issue | partial | Applies sharpit's text masker to supplied argument values before rendering, as required by sharpit's MCP secret-masking invariant. |
| G2 | mcp:prompt-verify_after_change | partial | Sharpit has no changed-code inventory, method probes, runtime-impact query, or previous-run comparison; the prompt directs users to runtime/SQL evidence and states these limits. |
| G2 | mcp:prompt-verify_after_change | partial | Changes Java-agent and Java method-signature examples to Python/FastAPI-neutral change, dependency, and route wording. |
| G2 | mcp:prompt-verify_after_change | partial | Replaces BootUI runtime-run comparison and probe-based invocation claims with available runtime insights, SQL traces, and request profiles; no equivalence is claimed. |
| G2 | mcp:prompt-verify_after_change | partial | Applies sharpit's text masker to supplied argument values before rendering, as required by sharpit's MCP secret-masking invariant. |
| G2 | mcp:prompt-review_application | partial | Sharpit has no memory scan or penetration probe; the prompt names these as unavailable and points to enabled sharpit advisors. |
| G2 | mcp:prompt-review_application | partial | Changes BootUI advisor terminology to sharpit advisor terminology and removes Java-only full-GC wording. |
| G2 | mcp:prompt-review_application | partial | Keeps BootUI's bounded-context and relevant-advisor workflow while omitting Java-specific scan side effects unavailable in sharpit. |
| G2 | mcp:prompt-review_application | partial | Applies sharpit's text masker to supplied argument values before rendering, as required by sharpit's MCP secret-masking invariant. |
| G2 | mcp:prompt-assess_application | partial | Replaces BootUI-only memory scan, penetration probe, and method probe actions with sharpit's vulnerability, database-advisor, and enabled advisor scans; each remains subject to approval. |
| G2 | mcp:prompt-assess_application | partial | Replaces BootUI agent security-sinks sensor settings with an explicit unavailable-evidence note because sharpit has no matching sensor. |
| G2 | mcp:prompt-assess_application | partial | Adapts JVM identity, snapshot, and tracing wording to Python/FastAPI runtime identity, process snapshots, and sharpit's available exception, trace, request, and SQL evidence. |
| G2 | mcp:prompt-assess_application | partial | Limits application identity to sharpit's FastAPI adapter and marks Spring MVC, WebFlux, Quarkus, native-image, and CRaC readiness as outside this lane's observed capabilities. |
| G2 | mcp:prompt-assess_application | partial | Replaces BootUI agent-only code inventory and advisor detail with sharpit's bounded reports, identifiers, and enabled advisor scans. |
| G2 | mcp:prompt-assess_application | partial | Applies sharpit's text masker to supplied argument values before rendering, as required by sharpit's MCP secret-masking invariant. |
| G2 | mcp:prompt-diagnose_runtime_issue | partial | Calls get_low_footprint first because sharpit reports low-footprint state through that tool rather than a lowFootprint field on result rows. |
| G2 | mcp:prompt-verify_after_change | partial | Removes BootUI's previous-run comparison promise because sharpit has no runtime-run comparison or prior-run identifier. |
| G2 | mcp:prompt-verify_after_change | partial | Rewords the route argument for exercising the changed route and using it as a Runtime Insights query; it is not a prior-run comparison key. |
| G2 | mcp:prompt-verify_after_change | partial | Uses sharpit's implemented repeated-selects and lazy-sql-after-handler Runtime Insights queries to check repeated SQL evidence. |
| G2 | mcp:prompt-verify_after_change | partial | Names CLI-only sharpit action tools with their CLI commands because actions are omitted from MCP tools/list. |
| G2 | mcp:prompt-assess_application | partial | Names available sharpit advisor scans with their CLI commands because action tools are omitted from MCP tools/list. |
| G2 | mcp:prompt-diagnose_runtime_issue | partial | Matches Java String.strip/isBlank whitespace behavior, including retaining non-breaking spaces, and bounds at 500 UTF-16 code units without splitting a surrogate pair. |
| G2 | mcp:prompt-verify_after_change | partial | Masks caller-supplied prompt and argument names in JSON-RPC errors, extending the required secret masking to error output. |
