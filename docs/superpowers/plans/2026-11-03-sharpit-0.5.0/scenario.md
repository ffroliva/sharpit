# Scenario: sharpit 0.5.0, full parity with BootUI 2.2.0

Run of `skills/scenario/SKILL.md` after `predict.md` (CAUTION 6/10); r2 after council round 1 (spec §15): lane
names updated (F5 → F5-gate/F5a/F5b; A-database-advisor → A-dbadv-1/2), drift rows 42–45 added, row 27 lowered. One table for the release; the `Lane` column
says which lane owns the test. Critical and High rows are the must-cover list: each is a named pytest function in
the owning lane plan. A ported BootUI case keeps its `# ported:` citation in the lane plan, not here.

## Coverage map

| Dim | Active? | Why |
|---|---|---|
| D1 Safe mode fails closed | yes | eight new panels must 404 when inactive and when `implemented=False` |
| D2 Guard | yes | new POST scans and actions (read-only flag, token), new SSE stream (security-logs) |
| D3 Masking | yes | security-logs data values, advisor violation snippets, MySQL statement text, workload report, transactions `errorMessage` |
| D4 Contract parity | yes | goldens for 7 panels; pre-scan vs post-scan; nullable keys |
| D5 Introspection drift | yes | fastapi-security walker, security and fastapi advisors, architecture package discovery |
| D6 No side effects | yes | scans on POST only; memory instrumentation is global state |
| D7 OSV/EPSS | yes | D4 extends the vulnerabilities panel |
| D8 Host integration | yes | MySQL drivers, async engines, factory apps, `src/` layouts, gc/tracemalloc in the host |
| D9 Scale | yes | advisor bounds (files, tables), transactions ring, security-logs ring, workload request count |
| D10 MCP/CLI parity | yes | each panel's tools; scans and memray action CLI-only |

## Scenario table

| # | Dim | Lane | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|---|
| 1 | D1 | F5a | A panel flag still `False` after F5a: `/panels`, `tools/list`, CLI, nav | High | absent everywhere, 404 on its path (0.4.0 rule, re-pinned for the 0.5.0 ids) | Integration |
| 2 | D1 | every panel lane | sharpit inactive (`SHARPIT_ENABLED=OFF`): `POST {api}/mysql/read`, `POST {api}/architecture/scan`, `GET {api}/security-logs/stream` | Critical | 404, no body, no DB connection, no file read | Integration |
| 3 | D2 | every scan lane | Scan POST with panel read-only (`SHARPIT_PANELS_<ID>_READ_ONLY=true`) | High | 403 verbatim `read_only_reason`, no scan started, no lock taken | Integration |
| 4 | D2 | every scan lane | Scan POST without token, or cross-site `Sec-Fetch-Site` | Critical | guard rejects before the route, scan never starts | Integration |
| 5 | D2 | B-security-logs | SSE stream from a non-loopback peer or a wrong Host | Critical | guard rejects; no event leaks | Integration |
| 6 | D3 | B-security-logs | `record_security_event(data={"details": "Bearer eyJ..."})` and a 401 exchange carrying `Authorization` | Critical | value masked in GET, stream, MCP; principal kept | Unit + Integration |
| 7 | D3 | B-security, C-fastapi, C-architecture | A violation located on a line holding `API_KEY = "sk-live-..."` | Critical | message names rule and `file:line`, never the literal | Unit |
| 8 | D3 | A-mysql, A-dbadv-1 | `performance_schema` digest text with a literal password; a DSN in a driver error | Critical | statement through the SQL normaliser + masker; DSN password masked in diagnostics | Unit |
| 9 | D3 | W-workload | Workload report from routes whose responses hold tokens | Critical | report holds only masked aggregates, no bodies | Unit |
| 10 | D3 | R-transactions | Failed commit whose error text holds a DSN password | High | `errorMessage` masked (existing `test_error_message_masked`, kept green after resume) | Unit |
| 11 | D4 | G0, each advisor lane | Golden is pre-scan only | High | parity test asserts the pre-scan shape; post-scan asserted only once G0 delivers `scanned.captured.json`; PARITY row says which | Golden |
| 12 | D4 | each advisor lane | Every DTO key present incl. nulls, `severityCounts` lists every severity, epoch ms | High | `assert_parity` green; nullable keys listed in `nullable.json` with a reason | Golden |
| 13 | D4 | R-fastapi-security | Extra keys `limitations`, `rule`, `roles`, `pattern` | Medium | allowed as additive, logged in spec §14 | Golden |
| 14 | D4 | V-unverified | `data` golden with `total: 0`; `sqlalchemy-statistics` with no golden | High | PARITY says `unverified` with the reason; a non-empty golden (if G0 captures one) turns the item check on | Golden |
| 15 | D5 | R-fastapi-security, B-security, C-fastapi | Custom `BaseRoute` subclass with a trap property / method | Critical | never read or called; route reported `unknown` + `bestEffort` | Integration |
| 16 | D5 | R-fastapi-security | Plain Starlette sub-app mounted with its own auth middleware | High | its routes `unknown` + `bestEffort`, never `unsecured` | Integration |
| 17 | D5 | R-fastapi-security, B-security | FastAPI 0.115 (`security_scopes`) vs ≥ 0.120 (`own_oauth_scopes`); `Annotated` dependencies; router-level `dependencies=` | High | same classification on floor and newest | Integration (lowest-direct leg) |
| 18 | D5 | C-architecture | App built in `create_app()` inside `src/pkg/app.py`; namespace package; app module is `__main__` | High | package root from the app object's module; none → `NOT_SCANNED` + reason, never a crash | Unit |
| 19 | D5 | C-fastapi | Sync `def` endpoint calling `requests.get`; `async def` calling `time.sleep`; Pydantic v1 `class Config` | High | rule fires with location; a sync endpoint with no I/O does not | Unit |
| 20 | D6 | every panel lane | GET report / violations / stream under `no_side_effects` | Critical | no socket, no file write, no SQL, no logger/env change | Integration |
| 21 | D6 | C-architecture, B-security, C-fastapi | GET after a POST scan | Critical | served from cache; no source file opened during the GET (spy on `open`/`io.open`/`Path.read_text`) | Integration |
| 22 | D6 | F5b, A-mysql, A-dbadv-1 | POST scan on an AUTOCOMMIT engine, or a driver that cannot set read-only | Critical | `unavailableReason`, no statement sent | Integration (leased MySQL) |
| 23 | D6 | F5b, A-mysql, A-dbadv-1 | A write attempted inside the read-only wrapper (MySQL, MariaDB, SQLite) | Critical | rejected (`ER_CANT_EXECUTE_IN_READ_ONLY_TRANSACTION`; sqlite "readonly database"); other dialects `ReadOnlyUnavailable` | Integration (leased MySQL) + Unit (sqlite) |
| 24 | D6 | F5a (all lanes inherit), U20-memory | Any GET or MCP tool | Critical | interpreter state unchanged (`tracemalloc`, `gc.callbacks`/threshold/enabled, `settrace`/`setprofile`, `sys.monitoring` ids) | Integration (`SideEffectGuard`) |
| 25 | D6 | U20-memory | memray capture POST | High | only with the panel action enabled and not read-only; CLI-only, not in `tools/list`; file under `SHARPIT_STATE_DIR` | Integration |
| 26 | D6 | W-workload | Workload run | Critical | in-process ASGI; sharpit opens no socket and no listener (the app's own DB sockets allowed); non-GET refused without `--allow-writes`; never reachable from a GET or MCP | Integration |
| 27 | D8 | A-mysql | `pymysql`, `mysqlclient`, `asyncmy`, MariaDB 11 | Medium (only `pymysql` is in the test extra; others logged §14) | supported drivers read; an unknown driver → `unavailableReason` naming it | Integration (leased) / Unit |
| 28 | D8 | A-dbadv-1, A-dbadv-2 | SQLite, PostgreSQL, MySQL; an unsupported dialect | High | vendor rules `SKIPPED` with reason; generic schema rules run | Integration |
| 29 | D8 | U20-memory | Normal serving | High | no `gc.callbacks`, no tracemalloc: gen-2 counts from a sampler `gc.get_stats()` diff | Unit |
| 30 | D8 | U20-memory | Windows / macOS (no cgroup, no `/proc`) | Medium | RSS and limit `null` with a reason; no crash | Unit |
| 31 | D9 | R-transactions | 10× capacity begins with no end event | High | ring length ≤ hard cap; oldest open row evicted as `UNKNOWN`, counted in `evicted` | Unit |
| 32 | D9 | R-transactions | Two nested unnamed savepoints (SQLAlchemy 2.1 fires `savepoint(conn, None)`) | High | inner release + outer rollback → outer `ROLLED_BACK` | Unit |
| 33 | D9 | C-architecture | App package with 5,000 modules, a 2 MB generated file, a symlink to `/` | High | bounded file count and size; symlinks outside the root skipped; `PARTIAL` with a limitation | Unit |
| 34 | D9 | A-dbadv-1 | 1,000 tables | High | stops at 300 tables, `truncated: true`, diagnostic | Integration |
| 35 | D9 | W-workload | `--sharpit-workload-requests 100000` | Medium | clamped to a documented maximum; warning | Unit |
| 36 | D10 | every panel lane | MCP `tools/list` has only read tools; scans on `/cli` only, gated by the panel and read-only | High | `test_mcp_tools_list_has_only_get` per lane | Integration |
| 37 | D10 | U20-memory, W-workload | MCP tools for memory facts / workload | High | read-only report tools only if any; capture and run are CLI-only | Integration |
| 38 | D1 | T-swallowed-2 | `pytest --sharpit` on a clean suite with a library that logs WARN then the app swallows (bench D13 twin) | High | finding on the app handler (its body neither raises nor logs) | Integration (pytester) |
| 39 | D4 | P-0.4.1 | N+1 from an explicit loop (`for id in ids: session.get(...)`), no relationship | Medium | message names the first application location and suggests batching (`in_()`); fingerprint unchanged | Integration (pytester) |
| 40 | D1 | P-0.4.1 | Bench corpus clean app without `--sharpit-app` | High | green (`SKIPPED` rest-api, not `unknown`), as G6 shipped: regression pin against the bench twin | Integration (pytester) |
| 41 | D9 | T-unbounded-read-2 | Non-paged route that loads 10,000 rows and returns 10 | Medium | finding only if the spike accepts the body-count cost; otherwise logged as "paged routes only" | Integration |
| 42 | D4 | D2 | `/activity/resources`, `/activity/journal`, `/http-exchanges/routes`, `/exceptions/caught` absent today | High | built at golden parity, extended `no_side_effects` | Golden + Integration |
| 43 | D4 | D3 (precondition) | `pools.py:77` emits `hikariPresent`; golden has `poolLibraryPresent` | High | D3's approved fix merged; pools parity green | Golden |
| 44 | D4 | A-sqltrace-insights | `routes/sql_trace.py` is empty | High | insights route at golden parity; statement text masked | Golden |
| 45 | D7 | D4 | OSV down during a drift-extended scan | High | status reports the failure, lock released | Integration |

## Must-cover before merge (Critical + High)

The authoritative list per lane is that lane plan's `## Must-cover` section, which F5-gate's `lane_gate.py` enforces
(each named test present and passing at the lane head). Row → owning lane test:

| Rows | Lane | Tests |
|---|---|---|
| 1, 24 | F5a | `test_unimplemented_panel_has_no_surface_05`, `test_side_effect_guard_catches_interpreter_state`, `test_appsource_never_imports_or_follows_symlinks`, `test_app_package_setting_never_imports` |
| 22, 23 | F5b | `test_mysql_read_only_wrapper_rejects_write`, `test_sqlite_read_only_wrapper_rejects_write`, `test_mysql_autocommit_refused`, `test_other_dialect_read_only_unavailable` |
| 2–4, 20, 36 | every panel lane | `test_inactive_<id>_paths_404`, `test_<id>_get_no_side_effects`, `test_read_only_blocks_scan`, `test_mcp_tools_list_has_only_get`, `test_report_golden_parity` |
| 10, 31, 32 | R-transactions | `test_error_message_masked`, `test_ring_stays_bounded_when_every_entry_is_open`, `test_nested_unnamed_savepoint_rollback_is_rolled_back`, `test_savepoint_depth_reset_after_error_and_checkin` |
| 15–17 | R-fastapi-security | `test_trap_route_untouched_by_every_introspecting_surface`, `test_custom_apiroute_subclass_still_classified`, `test_plain_starlette_subapp_routes_are_unknown_best_effort`, `test_scopes_floor_and_newest_classify_same`, `test_live_engine_driver_counts_as_covered` |
| 5, 6 | B-security-logs | `test_stream_guarded`, `test_security_event_values_masked_everywhere` |
| 7, 15, 17, 21 | B-security | `test_violation_never_contains_literal_secret`, `test_get_after_scan_opens_no_source_file`, `test_scan_reads_only_app_package`, `test_scopes_floor_and_newest_classify_same` |
| 7, 18, 21, 33 | C-architecture | `test_violation_never_contains_literal_secret`, `test_scan_reads_only_app_package`, `test_package_root_from_factory_app`, `test_namespace_package_root`, `test_main_module_app_not_scanned_through_route`, `test_bounded_files_and_symlinks`, `test_get_after_scan_opens_no_source_file` |
| 7, 15, 19, 21 | C-fastapi | `test_violation_never_contains_literal_secret`, `test_scan_reads_only_app_package`, `test_decorated_handler_resolved_to_inner_function`, `test_sync_endpoint_doing_io_flagged`, `test_blocking_call_in_async_flagged`, `test_get_after_scan_opens_no_source_file` |
| 8, 22, 23 | A-mysql | `test_statement_text_masked`, `test_session_current_statement_masked`, `test_driver_error_dsn_password_masked`, `test_autocommit_engine_is_unavailable`, `test_read_only_wrapper_rejects_write` |
| 8, 22, 23, 28, 34 | A-dbadv-1/2 | `test_driver_error_dsn_password_masked`, `test_query_string_secret_never_read_or_emitted`, `test_autocommit_engine_is_unavailable`, `test_read_only_wrapper_rejects_write`, `test_table_bound_truncates`, `test_unsupported_dialect_skips_vendor_rules`, `test_scan_never_configures_mappers` |
| 42 | D2 | `test_activity_resources_golden_parity`, `test_activity_journal_golden_parity`, `test_http_routes_golden_parity`, `test_exceptions_caught_golden_parity` |
| 44 | A-sqltrace-insights | `test_insights_golden_parity`, `test_insights_statement_text_masked` |
| 45 | D4 | `test_osv_down_releases_lock` |
| 29 | U20-memory (if built) | `test_gen2_count_from_gc_stats_diff`, `test_tracemalloc_started_by_user_is_left_running`, `test_memory_session_failure_restores_state` |
| 9, 26 | W-workload (if built) | `test_sharpit_opens_no_socket_or_listener`, `test_workload_report_masked`, `test_writes_refused_without_allow_writes` |
| 38 | T-swallowed-2 | `test_library_warn_does_not_hide_app_swallow` |
| 40 | P-0.4.1 | `test_bench_clean_app_without_sharpit_app_is_green` |
| 11, 12, 14 | each advisor lane / V-unverified | `test_report_golden_parity` (pre-scan pin; post-scan red on G0) |

## Deferred (Medium + Low): file as issues

Rows 13, 27, 30, 35, 39, 41: each becomes an issue on the 0.5.0 milestone if its lane does not cover it. Row 25
(memray) is out unless O4 says otherwise.

## Known-issues cross-reference

`skills/known-issues/SKILL.md` areas touched: activation (row 2), guard (rows 3–5), masking (rows 6–10),
introspection (rows 15–19), OSV (row 45).
