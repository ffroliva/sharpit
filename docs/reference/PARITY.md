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
| C | cli:fail-on-tools-dropped | adapted | crac, graalvm, hibernate, memory, spring advisor tools dropped as absent from sharpit; pentest_scan and get_pentest_report are kept |
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

## 0.8.0 against BootUI 2.5.0: deviations

Every deviation, partial implementation, adapted behavior, gap, or not-applicable item recorded across
the 0.8.0 lane fragments in `docs/reference/matrix-updates/` (116 entries):

| Lane | Key | Status | Reason |
|---|---|---|---|
| A1 | rule:SEC-SESSION-007 | adapted | Retirement rationale summarized for the security-advisor-checks table; the Spring session rule has no Python evaluation. |
| A1 | rule:SEC-HEAD-010 | adapted | Retirement rationale summarized for the security-advisor-checks table; cross-origin isolation is optional and outside this source scan. |
| A1 | rule:SEC-ACT-004 | adapted | Retirement documented as a duplicate of BootUI SPRING-MGMT-003; Actuator is not evaluated by sharpit. |
| A1 | rule:SEC-CONFIG-005 | adapted | Retirement documented as a duplicate of BootUI SPRING-WEB-004; the sharpit security rule covers Starlette debug tracebacks. |
| A2 | mappings:basePath | adapted | FastAPI exposes the ASGI application's root_path through AppInfo; the empty string represents the root mount, instead of composing framework-specific prefixes. |
| A2 | ui:http-probe.route-picker | adapted | Svelte uses a keyboard-accessible combobox backed by q and limit=50; selecting a route applies its basePath, method, media headers and an empty JSON body when needed, without sending. Route parameters remain editable in the path field. |
| A2 | tool:get_request_profile.authorizations | partial | The ported tool description includes authorization evidence, but sharpit has no request-journal authorization source; this remains with lane B4. |
| A3 | insight:route-latency-outliers | partial | BootUI fingerprints raw SQL statements; sharpit only retains masked SQL shapes, so it groups their case-insensitive normalized journal text and displays only that literal-free shape; src/sharpit/engine/collectors/insights/kinds/route_latency_outliers.py |
| A4a | binding-diagnostics | adapted | FastAPI extracts only Pydantic type/loc values in the adapter and redacts unknown path segments at capture time because route metadata and exposure are adapter-specific; BootUI SpringBindingDiagnosticsExtractor and ExceptionStore |
| A4a | binding-error-type | adapted | Unknown Pydantic custom error types become Invalid below FULL because validator-defined reason strings are untrusted; BootUI SpringBindingDiagnosticsExtractorTests |
| A4a | validation-message | adapted | Every exposure stores only the validation error count because Pydantic's rendered exception includes input, msg, and ctx; BootUI 52ae2b63f |
| A4a | diagnostic-exposure-timing | adapted | Non-FULL paths are redacted before storage; FULL preserves request-controlled map and unknown property names, following MessageExposure.current (MessageExposure.java:192-201) and ExceptionStore.exposeFieldPath (ExceptionStore.java:813-827), because the design permits them at FULL |
| A4a | request-controlled-error-id | adapted | Unknown exception group errors include the requested id as specified by the error contract; BootUI ExceptionStore has no equivalent error string |
| A4a | binding-parameter-paths | adapted | FastAPI validation locations retain declared query, path, header and cookie parameter names and their aliases; when no body model can be resolved, the location prefix remains and every following segment is redacted because Python route metadata supplies an explicit allowlist; BootUI SpringBindingDiagnosticsExtractor.resolveParameterName |
| A4a | validation-exception-path | adapted | Outside FULL, the validation exception record uses the matched FastAPI route template while the shared request context, request profile, and journal retain the raw path; FULL retains the raw exception path as BootUI does (BootUiExceptionHandlerResolver.resolveException). The non-FULL adaptation prevents rejected path values from being echoed in exception records. |
| A5 | ArchiveNames | n-a | Jar archive naming applies to Maven archives; PyPI distributions have no archive inventory in this scan. |
| A5 | PackageUrls | n-a | Maven package URL production has no PyPI counterpart in sharpit's distribution inventory. |
| A5 | VulnerabilityReach | n-a | BootUI runtime reach depends on Code Inventory and Maven dependency edges, neither of which sharpit exposes for PyPI. |
| A5 | AdvisorySymbols | n-a | BootUI symbols are populated from Maven/Code Inventory evidence; PyPI advisory symbols remain unavailable. |
| A5 | malicious-package-summary | missing | No MAL- or malicious-package guidance exists in sharpit; no malicious-package feature is added. |
| A6 | RAPI-MAP-012 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | RAPI-MAP-013 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | RAPI-VER-008 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | RAPI-VALID-007 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | RAPI-PAGE-004 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | DB-SCHEMA-011 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | DB-PG-006 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | DB-POOL-005 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | DB-SERVER-008 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | DB-MYSQL-004 | missing | BootUI 2.5.0 defines this applicable rule; tracked for a later sharpit release. |
| A6 | ARCH-CODE-019 | n-a | JDK formatter and XML processor thread-safety is specific to Java static and shared-bean fields. |
| A6 | DB-DRIVER-010 | n-a | MySQL Connector/J autoReconnect is specific to the Java JDBC driver. |
| A6 | rule:DB-SCHEMA-007 | partial | PostgreSQL serial2 is recognized as the smallint alias using SQLAlchemy inspector type names; broader JDBC metadata ranking remains specific to BootUI. |
| A6 | rule:DB-HIB-005 | n-a | SQLAlchemy's supported model facts expose mapped tables and columns but no binding from an entity to one of multiple datasources, so datasource-attributed uniqueness cannot be resolved safely. |
| A6 | rule:DB-CATALOG-ORACLE | n-a | Sharpit has no Oracle catalog reader; the applicable bounded and uncertainty-aware PostgreSQL and MySQL catalog behavior is ported. |
| A6 | rule:RAPI-VALID-003 | n-a | FastAPI and Pydantic treat omitted optional Header and Cookie primitive values as valid None/default bindings; Spring's resolver failure for Java primitives does not apply. |
| A6 | rule:ARCH-PKG-001 | adapted | Python detects cycles between resolved package imports directly, so BootUI's configured Java slice-root expansion is unnecessary; cross-root cycle behavior is covered by the existing package-cycle rule. |
| A7 | request-profile-stepping | adapted | Activity steps between profileable entries in the loaded feed; BootUI's LiveActivityTest.opens the request profile an HTTP Exchanges link names covers profile opening, while stepping is a sharpit UI adaptation. |
| A7 | request-profile-drawer-controls | n-a | The request profile is inline in sharpit's Activity panel, so BootUI's drawer width toggle and drawer section tabs have no corresponding container. |
| A7 | request-profile-journal-highlights | n-a | BootUI's highlights and work breakdown require journal authorization, baseline, REST, and ORM fields that sharpit's RequestProfile DTO does not expose. |
| A7 | http-route-exchange-drawer | adapted | Uses sharpit's existing GET /http-exchanges/routes ranking DTO and route-filtered GET /http-exchanges; the route drawer uses a native dialog and the existing paged table. |
| A7 | runtime-insights-navigation | n-a | sharpit has no Runtime Insights panel or observation DTO to filter, group, or pivot. |
| A7 | button-shaped-link-icons | n-a | sharpit's UI has no button-shaped navigation anchors; navigation uses plain anchors and actions use buttons. |
| A8 | request-id-header-name | deviation | BootUI uses X-BootUI-Request-Id; sharpit uses the requested X-Sharpit-Request-Id name. |
| A8 | request-id-header-trust | deviation | Trusted-proxy peers and forwarded headers do not grant trust; the existing raw-peer guard is the sole trust test. |
| A8 | request-id-header-server-error | deviation | An unhandled exception response generated by Starlette ServerErrorMiddleware sits outside CaptureMiddleware and has no request-id header. |
| A8 | request-id-header-response-start | deviation | ASGI adds the header to a copied response-start message, following the Quarkus capture-filter shape rather than Spring's response wrapper. |
| A8 | request-id-header-exchanges-buffer-gate | deviation | The header is emitted only while the in-process HTTP exchange buffer is available so every emitted id resolves to a recorded exchange; BootUI has no buffer-availability gate. |
| A9 | dto:activity.request-journal.authorizations | missing | GET /activity/request/{id}/journal is not implemented; authorization evidence depends on the journal authorization source. |
| A9 | dto:activity.request-journal.baselineComparison | missing | GET /activity/request/{id}/journal is not implemented; same-route baseline comparison is recorded with that route gap. |
| A9 | dto:runtime-insights.resource-profile.virtualThreadPinningSupported | partial | Reports false because Python has no BootUI JFR pinning capability. |
| A9 | dto:runtime-insights.resource-profile.pinnedEvents | partial | Reports 0 until a pinning event source exists. |
| A9 | dto:runtime-insights.resource-profile.outsidePinnedEvents | partial | Reports 0 until a pinning event source exists. |
| A9 | dto:runtime-insights.resource-profile.pinnedDurationMicros | partial | Reports 0 until a pinning event source exists. |
| A9 | dto:exceptions.occurrences.requestId | partial | Duplicates sharpit's request id; BootUI distinguishes requestId from traceId, but sharpit has no separate request/trace identity. |
| A10 | pentesting:transport | adapted | Invoke the FastAPI/Starlette app object passed to install(), running its internal middleware without a socket; external ASGI wrappers and lifespan work are outside the probe. Listener-added headers and TLS are unobservable. Apply BootUI's 8 KiB body, decoded body and header-retention limits; connect timeout and redirect handling are inapplicable to direct ASGI calls. |
| A10 | pentesting:deadline | adapted | Apply BootUI's 2-second timeout per request to cooperative async work; synchronous event-loop blocking delays timeout delivery, while an AnyIO threadpool handler may continue after timeout and single-flight release. The elapsed scan time is not a hard bound. |
| A10 | pentesting:trusted-host | adapted | Send BootUI's literal loopback Host; a host TrustedHost rejection is incomplete evidence rather than a scan of its 400 error page. |
| A10 | pentesting:body-evidence | adapted | Do not expose raw body, exception text, or unsafe response header values; retain only bounded sanitized evidence to preserve sharpit's masking boundary. |
| A10 | pentesting:non-404 | adapted | A non-404 response without a positive disclosure marker leaves a no-finding conclusion indeterminate with the status recorded; positive stack or cause markers still produce PT-A05-006, and 3xx responses follow BootUI's rule-specific checks. |
| A10 | pentesting:event-loop | adapted | Run the in-process ASGI probe on the host loop; acquire SingleFlight.try_acquire and release in finally after cancellation. A timed-out AnyIO threadpool callable may still run after release, so another scan can begin while it finishes. |
| A10 | pentesting:tool-wait | adapted | MCP and CLI worker threads wait at most 5 seconds for the host-loop coroutine (two BootUI request budgets plus margin); timeout returns 504 without cancelling the coroutine, whose flight remains held until the loop releases it. |
| A10 | pentesting:framework-evidence | adapted | The Python adapter evaluates the bounded HTTP response checks of the security-header and error-disclosure families on the GET probe, the TRACE advertisement and the CORS preflight checks (PT-A05-007, PT-A05-008, PT-A05-023, PT-A05-065) on the OPTIONS probe, and the CORS expose-headers check (PT-A05-073) on both probes. Spring Security, servlet configuration, JVM serialization, and Actuator metadata have no Python source equivalent and remain explicit coverage limitations. |
| A10 | pentesting:error-marker | adapted | PT-A05-006 uses BootUI's JVM stack-frame and qualified-exception patterns plus the Python traceback header; a body under HTTP 400 without a stack frame or a cause line is not reported. The finding names no marker text. A truncated body is evaluated on its retained text and the truncation is a separate limitation. |
| A10 | pentesting:browser-document | adapted | A response without a Content-Type is classified by its body, as in BootUI; BootUI's Spring whitelabel 404 exclusion has no Python equivalent and is not applied. |
| A10 | pentesting:remediation-text | adapted | Finding titles, severities and remediation texts are BootUI's, including Spring-specific wording; header and body values are named, never echoed. |
| A11 | pentesting:cors-transport | adapted | The CORS checks evaluate the response of the in-process ASGI app to BootUI's fixed preflight (origin https://evil.example, request method GET), not a loopback HTTP response; the report labels it heuristic synthetic evidence and does not claim browser, proxy or deployed-edge behaviour. The PT-A05-069 recommendation keeps the A10 wording because no loopback listener exists. Reason: no socket may be opened (consistent with pentesting:transport). |
| A11 | pentesting:a02-description | adapted | The A02 coverage descriptions are BootUI's wording with the Spring and Quarkus sentences replaced by "Servlet mappings and servlet-security evidence are unavailable on this adapter." and "Route authorization and Actuator configuration are not assessed by this adapter."; statuses and precedence are BootUI's (a finding gives REVIEW, incomplete evidence gives INDETERMINATE, otherwise INFO). Reason: the Python ASGI adapter has neither framework. |
| A11 | pentesting:cors-expose-limitation | adapted | A fixed limitation names PT-A05-073 as indeterminate when either of its probe halves is withheld; BootUI's PT-A05-069 text omits it. Reason: fail closed, at no parity cost; the 069 finding text is BootUI's. |
| A11 | pentesting:cors-evidence-masking | adapted | Host-echoed fragments in CORS evidence (an origin, a header token) are masked one by one before the 240-character cut and become [masked] under METADATA_ONLY; BootUI does not mask evidence. Fixed text is never masked. Reason: secrets are masked before any output. |
| A11 | pentesting:a10-truncated-get-inventory | gap | A10 is not INDETERMINATE on a truncated GET header inventory (BootUI: getFailed \|\| getBodyTruncated \|\| optionsFailed). Reason: outside lane A11. |
| A11 | pentesting:a10-get-incomplete-order | gap | A GET-incomplete result overrides an A10 finding in coverage; BootUI checks findings first. The finding stays in the report; only the coverage label is more cautious (PT-A10-001 from an OPTIONS 5xx with a truncated GET 404 reports INDETERMINATE where BootUI reports REVIEW). A complete GET 5xx that fires PT-A10-001 is INDETERMINATE through the separate no-disclosure clause. Reason: outside lane A11; the OPTIONS input added by A11 follows BootUI's order. |
| A11 | pentesting:coverage-review-vs-info | gap | A04, A10 and A03 report REVIEW where BootUI reports INFO; A02 follows BootUI. Reason: outside lane A11. |
| A11 | pentesting:cors-starlette-methods | adapted | Starlette CORSMiddleware never sends Access-Control-Allow-Methods: *; PT-A05-023 reports only hosts that send the literal wildcard. Reason: framework behaviour; the check is ported as is. |
| A12 | pentesting:cookie-values | adapted | Set-Cookie values and the raw header text are discarded at the probe boundary: the synthetic GET response keeps only a value-free observation per cookie (a name label, flag presence, a classified SameSite and a Path=/ boolean), and its header map has no set-cookie key. Reason: a cookie value is a secret (safety model 3). |
| A12 | pentesting:cookie-attributes | adapted | SameSite is a closed enum (lax, strict, none, other) and Path a boolean; no attribute value is retained. BootUI's checks read only those classifications. Reason: safety model 3. |
| A12 | pentesting:cookie-name-unnamed | adapted | A first segment with no = after its first character is shown as (unnamed); BootUI shows the whole segment, which can be the cookie value. Reason: safety model 3. |
| A12 | pentesting:cookie-name-redacted | adapted | a cookie name that the secret-value detector matches, tested on the full name before the 80-character shortening, is shown as (redacted); the engine otherwise treats names as non-secret, so this is stricter than it. Severity logic sees an INFO label. Reason: fail closed. |
| A12 | pentesting:cookie-name-echo | adapted | Cookie names and the mount paths of the session checks pass through the masker one by one before the 240-character cut and read [masked] under METADATA_ONLY; classification runs on the unmasked label. Reason: safety model 3, consistent with pentesting:cors-evidence-masking. |
| A12 | pentesting:cookie-name-residual | adapted | a nameless padded base64 value (dGVzdA==; Secure) keeps its unpadded part as the label, as RFC 6265bis reads a name; it cannot be told from a name and is pinned by a test. Under FULL exposure a long name the secret detector does not match (for example several concatenated tokens) is shown as its first 80 characters. |
| A12 | pentesting:cache-control-evidence | adapted | PT-A02-008 evidence lists the recognised Cache-Control directive names (numeric arguments of at most ten digits for max-age, s-maxage and the stale-* directives only) and a count of the other directives, not the raw header text that BootUI joins. Reason: header values are never echoed (the A10 module invariant) and masking cannot keep the text readable. |
| A12 | pentesting:cookie-capture-full | adapted | the capture middleware of the host records the probe exchange like any exchange of the host. Under FULL its Set-Cookie value is shown, and under MASKED and FULL its Cache-Control value is recorded as sent because header masking decides by header name; MASKED and METADATA_ONLY records hold no cookie value. Pentesting evidence never echoes either header value. Reason: FULL is the opt-in to unmasked text, and changing header masking is a separate decision. |
| A12 | pentesting:session-config | adapted | PT-A02-004 and PT-A02-006 read the SessionMiddleware keyword options (https_only passed as False, same_site none) from the static security facts instead of server.servlet.session.cookie.*; the target, evidence and recommendation name the middleware option, and the evidence names the echoed mount path of a mounted sub-application, never an option value. IDs, titles, severities, confidence and categories are BootUI's. Reason: the Spring properties do not exist. |
| A12 | pentesting:session-config-gap | adapted | facts that are absent or carry any limitation record BootUI's gap (Framework configuration evidence was incomplete.) and make the scan PARTIAL; the limitation text, which can carry a mount path, is never copied, and counting every limitation rather than only the session-related ones is the conservative default. |
| A12 | pentesting:flask-session-config | gap | The session configuration checks are not ported for Flask: app.config always holds SESSION_COOKIE_SECURE and SESSION_COOKIE_SAMESITE with defaults, so an explicit false cannot be told from the default, and the Flask adapter has no pentesting scan. |
| A12 | pentesting:cookie-overlap | adapted | The Security panel rules SEC-SESSION-002 and SEC-SESSION-004 stay; the pentesting checks report separate evidence under their own IDs, as BootUI's two panels do. |
| A13 | pentesting:exposure-docs-source | adapted | PT-A05-041 matches the registered OpenAPI, Swagger UI and ReDoc handlers (FastAPI's own, by module and qualified name) and reports their route paths, instead of BootUI's fixed prefix list /v3/api-docs, /v2/api-docs, /swagger-ui, /graphiql. Reason: the Java prefixes name Spring libraries; paths are configurable in FastAPI, so the handler is the stable fact. A documentation route served by a host's own handler is not recognised, and a declared OpenAPI URL with no recognised handler is a stated gap. |
| A13 | pentesting:exposure-graphiql | n-a | The GraphiQL marker is dropped. Reason: a GraphQL library serves its IDE and its API on one route; the route table cannot distinguish them. |
| A13 | pentesting:exposure-docs-text | adapted | PT-A05-041 target is Application route table (BootUI: Spring MVC mappings); the recommendation and the learn-more link name FastAPI's conditional OpenAPI guidance and omit the H2 sentence; id, title, category, severity and confidence are BootUI's. Reason: the H2 console has no Python equivalent and there is no Spring MVC. |
| A13 | pentesting:exposure-proxy | adapted | PT-A05-044 evaluates uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware on the application stack (root and mounted) instead of server.forward-headers-strategy; its title is ProxyHeadersMiddleware trusts X-Forwarded-* headers, its target ProxyHeadersMiddleware, its evidence names the root application and each mount, and its recommendation is BootUI's with the Spring and Tomcat names replaced; id, category, severity and confidence are BootUI's. Reason: the Spring property does not exist; uvicorn's server flags are not observable and are stated in the third standing sentence. |
| A13 | pentesting:exposure-unavailable | adapted | An exception or a missing introspector method from the route read gives BootUI's endpoint gap, a partial scan and, with no A02 finding, A02 INDETERMINATE; unavailable security facts, a non-FastAPI host or any facts limitation gives BootUI's configuration gap and a partial scan, PT-A05-044 unevaluated and documentation still reported. Reason: BootUI's failed provider is truncated and its absent provider silent; here every unreadable evidence fails closed because FastAPI internals vary by version and a wrapped mount is visible only as limitation text. |
| A13 | pentesting:exposure-masking | adapted | Documentation route paths and mount paths in the PT-A05-041 and PT-A05-044 evidence pass through the context masker one by one before the 240-character cut and become [masked] under METADATA_ONLY; BootUI masks nothing here. Fixed text is never masked. Reason: safety model 3, same rule as pentesting:cors-evidence-masking. |
| A13 | pentesting:exposure-coverage-a07 | adapted | Sharpit labels A07 coverage NOT_APPLICABLE where BootUI labels the same branch HANDOFF; the behaviour is ported (the hand-off branch precedes the indeterminate branch), so endpoint truncation leaves A07 unchanged and the ported assertion of PentestingScannerTests.truncatedEndpointMetadataMakesA07IndeterminateButNotA04 changes from INDETERMINATE to NOT_APPLICABLE. Reason: the BootUI test runs with Spring metadata present; sharpit has none, so its A07 is the hand-off branch. |
| A13 | pentesting:exposure-gap-placement | adapted | Gaps are entries of evidence.limitations with BootUI's wording; the scan message stays fixed text and usable stays the GET probe's usability; this lane adds one new string and no standing entry because the measured worst case already uses 19 of the 20 unique entries and every promised statement must stay. Reason: BootUI appends gaps to its scan message and ORs per-check usability; sharpit's message, usable and cap are the pentesting report's. |
| A13 | pentesting:exposure-config-gap | adapted | A mount wrapped in ProxyHeadersMiddleware, absent security facts and a non-FastAPI host give BootUI's configuration gap through a boolean on the facts' limitations; the limitation text is never read. Reason: the introspector records a wrapped mount only as text, the boolean is shared with the session checks, and the text can carry a mount label. |
| A13 | pentesting:exposure-bound | adapted | The 4096-pattern inspection bound and its gap text are BootUI's; the 64-handler-mapping bound has no analogue. Reason: Starlette has one route tree, not a list of handler mappings. |
| A13 | pentesting:exposure-html-mappings | n-a | htmlMappingsPresent is not ported. Reason: it only gates BootUI's Spring whitelabel 404 exclusion, which the scan does not apply (pentesting:browser-document). |
| A13 | pentesting:exposure-actuator | n-a | PT-A05-016, PT-A05-019, PT-A05-027, PT-A05-028, PT-A05-032, PT-A05-033, PT-A05-034, PT-A05-035, PT-A05-036, PT-A05-037, PT-A05-038, PT-A05-039, PT-A05-049, PT-A05-052, PT-A05-053, PT-A05-054, PT-A05-055, PT-A05-056. Reason: there is no management-endpoint model in FastAPI or Starlette. |
| A13 | pentesting:exposure-prometheus | n-a | PT-A05-040. Reason: BootUI binds it to the Actuator base path; a prometheus_client ASGI app is an opaque mount at a host-chosen path, not a framework convention. |
| A13 | pentesting:exposure-h2 | n-a | PT-A05-017. Reason: there is no embedded database console. |
| A13 | pentesting:exposure-actuator-cors | n-a | PT-A05-029. Reason: it is a Spring property; generic CORS is evaluated by the CORS checks. |
| A13 | pentesting:exposure-request-logging | n-a | PT-A05-051. Reason: there is no application-level request-detail logging toggle; server logging verbosity is outside the app object and a logger level is process-global state a read must not change. |
| A13 | pentesting:exposure-devtools | n-a | PT-A05-062. Reason: there is no remote-restart secret; the Werkzeug debugger is not visible on the app object. |
| A13 | pentesting:exposure-firewall | n-a | PT-A05-042. Reason: Starlette has no request firewall. |
| A13 | pentesting:exposure-management-port | n-a | PT-A05-043. Reason: there is no separate management port. |
| A13 | pentesting:exposure-spring-security | n-a | PT-A07-001, PT-A07-002, PT-A07-003, PT-A07-004, PT-A07-005, PT-A01-001. Reason: Spring Security is not ported. |
| A13 | pentesting:exposure-oauth2-issuer | adapted | PT-A07-006 is covered by the security advisor's SEC-OAUTH-004 and SEC-OAUTH-006, which exempt loopback hosts and are production-only; BootUI flags any http:// issuer. Reason: the scheme-URL facts already exist in the security advisor; no pentesting finding is added. |
| A13 | pentesting:exposure-oauth2-grant | n-a | PT-A07-007. Reason: the OAuth2 flow type is not captured by the introspector. |
| A13 | pentesting:exposure-jvm | n-a | PT-A08-001. Reason: JVM serialization. |
| A13 | pentesting:exposure-flask | pending | Flask documentation routes and the Werkzeug debugger are not checked. Reason: the pentesting scan as a whole is wired to the FastAPI adapter only. |
| F1 | adapter:flask-route-metadata | adapted | BootUI 2.5.0 has no Flask route model; Flask route metadata is read statically, unreadable maps report UNKNOWN, and callable views are identified by class without invocation; docs/reference/FLASK-ROUTE-MODEL.md |
| T1 | feature:http-security-observer | n-a | Sharpit-only pytest HTTP security observer; BootUI 2.5.0 has no equivalent per-test observation or configured endpoint expectation contract. |
| T1 | rule:HTTP-SEC-001 | n-a | Sharpit-only rule for a configured missing response header (HIGH); no BootUI 2.5.0 counterpart. |
| T1 | rule:HTTP-SEC-002 | n-a | Sharpit-only rule for a configured unexpected status (HIGH); no BootUI 2.5.0 counterpart. |
| SHIPFIX | masking:matrix-session-id-names | adapted | UriMasking.maskPath keeps a ;jsessionid, ;sid or ;session matrix value unless its name matches a sensitive key; sharpit also masks jsessionid, phpsessid, session, sessionid and sid under MASKED, matching the trace and journal path masks that hide every matrix value |
| SHIPFIX | rule:DB-SCHEMA-005 | adapted | BootUI reads the primary key backing index from JDBC index metadata; SQLAlchemy never lists it, so the primary key constraint stands in as the backing index and an ordinary unique index on exactly the primary key columns is reported |

## 0.9.0 against BootUI 2.5.0: deviations

Every deviation, partial implementation, adapted behavior, gap, or not-applicable item recorded across
the 0.9.0 lane fragments in `docs/reference/matrix-updates/` (24 entries):

| Lane | Key | Status | Reason |
|---|---|---|---|
| M1 | RAPI-MAP-012 | n-a | An unannotated Spring parameter binds as a query parameter; FastAPI binds a parameter named like a path token to the path. |
| M1 | RAPI-MAP-013 | n-a | Spring's RequestMethodsRequestCondition.combine() unions the class-level and method-level HTTP methods; neither FastAPI nor Flask has a class-level method mapping to combine with a route's own methods. |
| M1 | RAPI-VER-008 | n-a | FastAPI has no restrictive consumes condition counterpart. |
| M1 | RAPI-VALID-007 | n-a | Bean Validation skips nested objects without @Valid; pydantic validates nested models. |
| M1 | RAPI-PAGE-004 | n-a | Spring Data Page serialization is specific to Spring Data. |
| M2 | DB-SCHEMA-011 | ported | Ported from BootUI 2.5.0 ForeignKeySetNullOnNotNullColumnRule. |
| M2 | DB-PG-006 | adapted | Scans current_schema() only, like the other PostgreSQL vendor rules, whereas BootUI scans all non-system schemas. |
| M2 | DB-SERVER-008 | adapted | Ported from BootUI 2.5.0 MySqlStrictSqlModeRule; the recommendation names SQLAlchemy's places for session SQL (an init_command connect argument, a connect event) in place of the JDBC URL's sessionVariables and the pool's connectionInitSql, which a Python application does not have. |
| M2 | DB-MYSQL-004 | ported | Ported from BootUI 2.5.0 MySqlUnenforcedCheckConstraintRule. |
| M2 | DB-POOL-005 | adapted | BootUI reads the HikariCP and Agroal acquisition timeouts; sharpit reads SQLAlchemy's QueuePool timeout, where None, an infinite timeout or one too large for milliseconds disables the timeout and 0 fails immediately rather than waiting indefinitely; a pool class with no acquisition timeout (NullPool, StaticPool, SingletonThreadPool) is not evaluated. The texts name SQLAlchemy's pool_timeout in place of HikariCP's connectionTimeout. |
| R0 | route:GET /activity/request/{id}/journal | missing | Route added in BootUI 2.5.0 route catalog; sharpit has no route at /sharpit/api/activity/request/{id}/journal (HTTP 404). |
| R0 | route:GET /conditions | n-a | JVM-only: Spring/Quarkus conditional bean evaluation has no Python counterpart. |
| R0 | route:GET /crac | n-a | JVM-only: CRaC (Coordinated Restore at Checkpoint) checkpoints have no Python counterpart. |
| R0 | route:GET /dev-services | n-a | JVM-only: Quarkus Dev Services container orchestration has no Python counterpart. |
| R0 | route:GET /devtools | n-a | JVM-only: Spring Boot DevTools restart and live-reload have no Python counterpart. |
| R0 | route:GET /graalvm | n-a | JVM-only: GraalVM native image analysis has no Python counterpart. |
| R0 | route:GET /graalvm/metadata | n-a | JVM-only: GraalVM native image reachability metadata has no Python counterpart. |
| R0 | route:GET /graalvm/scan-progress | n-a | JVM-only: GraalVM native image scan progress has no Python counterpart. |
| R0 | route:GET /heap-dump | n-a | JVM-only: HotSpot JVM heap dump generation has no Python counterpart. |
| R0 | route:GET /jvm-tuning | n-a | JVM-only: JVM runtime flags and garbage collection tuning have no Python counterpart. |
| R0 | route:GET /liquibase/changesets | n-a | JVM-only: Liquibase migration engine has no Python counterpart. |
| S3/S4 | xc:sql-trace-panel-availability | adapted | BootUI checks recorder.hasWrappedDataSource() after SqlTraceDataSourceBeanPostProcessor wraps a Spring DataSource bean; Python has no container DataSource beans, so sharpit treats the SQL source as wrapped once SQLAlchemy statement listeners are attached (or sqlite3 is traced, or an engine is registered on an attached context) and returns "No DataSource has been wrapped for tracing yet." otherwise |
| S3/S4 | journal-source:connection | adapted | Pool connect/checkout/checkin listeners publish ConnectionPayload on checkin with dataSource, waitNanos, statements and obtainedNanos; executed statements pay no per-statement cost: the count is derived at check-in, only from the SQL Trace rows recorded since the checkout, which carry the connection; the count is exact or -1: -1 when there is no SQL Trace recorder, when the rows since checkout left the SQL Trace ring, or when the SQL Trace panel was paused (BootUI keeps counting then); the journal's sql events carry no connection and are never used for the count; one gap remains: with no sql journal source, a SQL Trace panel paused for part of a checkout undercounts it |
| S3/S4 | xc:insights-sqlcapture-not-recorded | adapted | BootUI calls SqlTraceRecorder.registerDataSource only after DataSource proxy wrapping succeeds; sharpit rolls back sqla.add on listener attach failure and requires attached (or explicitly suspended) statement listeners before a registered engine counts as a recorded SQLAlchemy source |

## 0.10.0 against BootUI 2.5.0: deviations

Every deviation, partial implementation, adapted behavior, gap, or not-applicable item recorded across
the 0.10.0 lane fragments in `docs/reference/matrix-updates/` (15 entries):

| Lane | Key | Status | Reason |
|---|---|---|---|
| #305 | pentesting:PT-A05-002:recommendation | adapted | BootUI says "Enable content type sniffing protection through Spring Security headers or equivalent middleware." sharpit names security-header middleware. |
| #305 | pentesting:PT-A05-006:learnMoreUrl | adapted | BootUI links to https://docs.spring.io/spring-boot/reference/web/servlet.html. sharpit links to FastAPI's error-handling guide. |
| #305 | pentesting:A01:initial-description | adapted | BootUI says "Spring MVC mappings have not been inspected yet." sharpit states that the local scan does not assess route authorization. |
| #305 | pentesting:A02:initial-description | adapted | BootUI says "Security headers, cookies, CORS, errors, and actuator mappings have not been inspected yet." sharpit refers to route exposure. |
| #305 | pentesting:A05:description | adapted | BootUI says "BootUI does not send injection payloads. Use a dedicated scanner and manual review." sharpit substitutes its own name. |
| #305 | pentesting:A06:description | adapted | BootUI says "BootUI cannot infer the host application's threat model or business logic design." sharpit substitutes its own name. |
| #305 | pentesting:A07:initial-description | adapted | BootUI says "Spring Security wiring has not been inspected yet." sharpit checks the synthetic GET response headers for HTTP Basic or Digest challenges. |
| #305 | pentesting:A08:initial-description | adapted | BootUI says "Deserialization and serialization-filter posture have not been inspected yet." sharpit states that the local scan does not assess deserialization safeguards. |
| #305 | pentesting:static-evidence-limitation | adapted | sharpit's ASGI limitation has no verbatim BootUI counterpart. The note states the limits of static route and middleware evidence. |
| #305 | pentesting:A01:scanned-description | adapted | BootUI says "Spring Security wiring, handler mappings, and SecurityFilterChain CSRF posture were inspected for authorization review prompts." sharpit's scan does not assess route authorization. |
| #305 | pentesting:A02:scanned-description:review | adapted | BootUI uses "No findings were produced by the evaluated synthetic-response, Spring configuration, and Spring MVC mapping checks. This does not establish that every route, authorization rule, or deployment edge is configured safely." sharpit's review note names the synthetic GET, CORS preflight, and available route-table and middleware configuration checks. |
| #305 | pentesting:A02:scanned-description:clean | adapted | BootUI uses "No findings were produced by the evaluated synthetic-response, Spring configuration, and Spring MVC mapping checks. This does not establish that every route, authorization rule, or deployment edge is configured safely." sharpit's no-finding note refers to the synthetic GET, CORS preflight, and available route-table and middleware configuration checks. |
| #305 | pentesting:A07:scanned-description | adapted | BootUI says "No findings were produced by the evaluated Spring authentication metadata. Endpoint authentication, account policy, and runtime login behavior were not tested." sharpit states whether Basic or Digest headers in the synthetic GET response produced a review finding. The note explains the limit on dependency-based authentication and qualifies incomplete evidence. |
| #305 | pentesting:A08:scanned-description | adapted | BootUI says "No findings were produced by the evaluated Jackson default-typing and JVM ObjectInputFilter checks. Custom deserializers, update integrity, and trusted artifact boundaries still require manual review." sharpit's local scan does not assess deserialization safeguards. |
| exchanges-principal | http-exchanges:principal | adapted | BootUI names the authenticated principal from Spring Security. sharpit reads scope["user"] as plain data and never runs a property, descriptor or __getattr__: Starlette's SimpleUser, or a subclass that keeps its is_authenticated and display_name, gives its username; UnauthenticatedUser gives none; any other user is named only when is_authenticated is exactly True and display_name exactly a str, both plain attributes or __slots__ fields. A computed name, a str subclass or a truthy non-bool flag gives no principal. |
