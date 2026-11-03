# D2 findings

Implementer: Claude Code subagent (claude-opus-5-5)

Every red below was checked with `scripts/dev/red_check.py` before its `test:` commit: all `RED (assertion under tests/)`.

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/capture/test_http_routes.py::test_summarize_groups_by_method_and_route_and_computes_percentiles | e1895b79a2a52339feacc76c40339e77168e2073 | the window covers every retained exchange | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/engine/capture/test_http_routes.py::test_summarize_keeps_the_top_routes_per_criterion_and_a_pinned_route | e1895b79a2a52339feacc76c40339e77168e2073 | only the top route per criterion | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/engine/capture/test_http_routes.py::test_summarize_clamps_the_limit | e1895b79a2a52339feacc76c40339e77168e2073 | a limit below 1 clamps to 1 | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/engine/capture/test_http_routes.py::test_summarize_reports_unavailable_without_capture | e1895b79a2a52339feacc76c40339e77168e2073 | no buffer: the report says why | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/engine/capture/test_exchanges.py::test_exchange_row_emits_route_route_source_request_id_and_retention | e1895b79a2a52339feacc76c40339e77168e2073 | a matched template is the route | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/fastapi/test_http_exchanges_api.py::test_http_routes_golden_parity | e1895b79a2a52339feacc76c40339e77168e2073 | GET /http-exchanges/routes is served | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/fastapi/test_http_exchanges_api.py::test_http_exchanges_report_golden_parity | e1895b79a2a52339feacc76c40339e77168e2073 | the 2.2.0 report carries its retention | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/fastapi/test_http_exchanges_api.py::test_capture_records_the_template_or_the_masked_path | e1895b79a2a52339feacc76c40339e77168e2073 | a matched route is labelled by its template | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/fastapi/test_http_exchanges_api.py::test_http_routes_limit_must_be_an_integer | e1895b79a2a52339feacc76c40339e77168e2073 | a non-integer limit is a bad request | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/fastapi/test_http_exchanges_api.py::test_get_http_routes_mcp_tool | e1895b79a2a52339feacc76c40339e77168e2073 | the MCP answer has a result (Unknown tool error) | Fixed in ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| tests/engine/capture/test_sqltrace.py::test_sql_trace_entry_includes_duration_micros_and_report_retention | f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 | durationMicros is the exact nanosecond timing, truncated | Fixed in 4d5a2a3c6ec25d7c15b4ab866756124b50182477 |
| tests/engine/capture/test_logtail.py::test_log_tail_line_sets_message_omitted_in_metadata_only_mode | f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 | a withheld message says so | Fixed in 4d5a2a3c6ec25d7c15b4ab866756124b50182477 |
| tests/engine/capture/test_exceptions.py::test_exceptions_report_includes_caught_in_code_null | f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 | the 2.2.0 report carries caughtInCode | Fixed in 4d5a2a3c6ec25d7c15b4ab866756124b50182477 |
| tests/fastapi/test_exceptions_api.py::test_exceptions_caught_golden_parity | f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 | GET /exceptions/caught is served, not read as a group id | Fixed in 4d5a2a3c6ec25d7c15b4ab866756124b50182477 |
| tests/fastapi/test_exceptions_api.py::test_exceptions_report_carries_caught_in_code | f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 | the 2.2.0 report carries caughtInCode | Fixed in 4d5a2a3c6ec25d7c15b4ab866756124b50182477 |
| tests/fastapi/test_log_tail_api.py::test_log_tail_recent_golden_parity | f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 | a shown message is not omitted | Fixed in 4d5a2a3c6ec25d7c15b4ab866756124b50182477 |
| tests/engine/test_tools.py::test_mcp_sql_traces_and_log_tail_accept_query_and_limit_with_page_metadata | f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 | the MCP sql-trace view has no page metadata | Fixed in 4d5a2a3c6ec25d7c15b4ab866756124b50182477 |
| tests/engine/capture/test_activity.py::test_request_profile_emits_2_2_0_keys_and_get_request_profile_tool | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | the 2.2.0 collections are empty lists | Fixed in 37d49a25acf902fd5c49918740b30bc72d79385f |
| tests/engine/capture/test_activity.py::test_activity_buffer_source_emits_warning_on_journal_only_filters | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | journal-only filters on the buffer feed say they do not apply | Fixed in 37d49a25acf902fd5c49918740b30bc72d79385f |
| tests/fastapi/test_activity_api.py::test_activity_journal_golden_parity | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | GET /activity/journal is served | Fixed in 37d49a25acf902fd5c49918740b30bc72d79385f |
| tests/fastapi/test_activity_api.py::test_activity_resources_golden_parity | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | GET /activity/resources is served | Fixed in 37d49a25acf902fd5c49918740b30bc72d79385f |
| tests/fastapi/test_activity_api.py::test_activity_journal_filters_warn_on_the_buffer_feed | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | the route filter adds no journal warning | Fixed in 37d49a25acf902fd5c49918740b30bc72d79385f |
| tests/fastapi/test_activity_api.py::test_get_request_profile_mcp_tool | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | the MCP answer has a result (Unknown tool error) | Fixed in 37d49a25acf902fd5c49918740b30bc72d79385f |
| tests/safety/test_d2_safety.py::test_capture_drift_get_no_side_effects | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | every 2.2.0 capture GET is served | Fixed in 37d49a25acf902fd5c49918740b30bc72d79385f |
| tests/safety/test_d2_safety.py::test_new_tools_read_only | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | both 2.2.0 capture tools are listed | Fixed in 37d49a25acf902fd5c49918740b30bc72d79385f |

The first task 2 red commit built two exceptions API apps without `install()`, so those tests could never pass. It had
no fix on top: it was soft-reset and replaced by f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 before any implementation was
committed. No test changed after its recorded red SHA.

## Pins (passed before their fix: never claimed as reds)

| Test | Historical SHA | Mutation proof |
|---|---|---|
| tests/engine/capture/test_http_routes.py::test_capture_overhead_budget_unchanged | e1895b79a2a52339feacc76c40339e77168e2073 | scratch copy at f7429da, `BUDGET_MS = 0.3` in test_capture_overhead.py: `AssertionError: test_capture_overhead.py assert 'BUDGET_MS = 0.3' == 'BUDGET_MS = 0.2'` |
| tests/masking/test_d2_masking.py::test_unmatched_path_secret_never_reaches_route_labels | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | scratch copy at f7429da, `route_of` returns the path unmasked and `exchange_row` passes the raw path: `assert 'eyJhbGciOiJ...' not in '{"available...'` (the JWT reaches `/http-exchanges/routes`) |

## Existing pins updated for the 2.2.0 contract (keys added, nothing removed or loosened)

| Test | Change |
|---|---|
| tests/engine/capture/test_exchanges.py::test_shape_keys_match_bootui | `DTO_KEYS` + `route`, `routeSource`, `requestId`; report + `retention` |
| tests/fastapi/test_http_exchanges_api.py::test_http_exchanges_shape | report + `retention` |
| tests/engine/capture/test_logtail.py, tests/fastapi/test_log_tail_api.py `test_shape_keys_match_bootui` | `LINE_KEYS` + `messageOmitted` |
| tests/fastapi/test_sql_trace_api.py::test_shape_keys_match_bootui | `REPORT_KEYS` + `retention`, `ENTRY_KEYS` + `durationMicros` |
| tests/fastapi/test_exceptions_api.py::test_shape_keys_match_bootui | report + `caughtInCode` |
| tests/engine/capture/test_activity.py keys pin, `test_until_cursor_ignored` | `PROFILE_KEYS` + five 2.2.0 keys; signature + `journal_filters` (until/cursor still absent) |
| tests/engine/test_tools.py::test_catalogue_names_panels_actions_and_schemas | + `get_http_routes`, `get_request_profile`; three schemas per 2.2.0 |
| tests/engine/test_tools.py::test_mcp_schema_matches_bootui | `SCHEMAS_2_2_0` overrides the 0.2.0 fixture for `get_log_tail`, `get_sql_traces`, `get_live_activity` |

## Overhead: paired on/off budget runs, base 78706ac vs lane head 37d49a2

Same machine, base and head alternating, 3 runs each, `SHARPIT_OVERHEAD_LOG` records of the unchanged budget tests:

| Budget | base runs (median) | lane runs (median) | Status |
|---|---|---|---|
| capture per request, budget 0.200 ms | 0.0754, 0.0767, 0.0691 (0.0754) | 0.0744, 0.0724, 0.0771 (0.0744) | ok, no measurable change |
| SQL listener per statement, budget 50 us | 24.301, 18.398, 20.351 (20.351) | 21.620, 33.857, 23.892 (23.892) | ok, within run-to-run noise |
| SQLAlchemy transaction listener pair, budget 30 us | 9.914, 10.747, 11.621 (10.747) | 10.298, 13.650, 10.074 (10.298) | ok, path untouched |

The request path adds one `getattr` on `scope["route"]` and three dict keys (`mask_route` only for an unmatched
path); the SQL listener adds one integer division and one key.

## Found in the lane (before review)

The first splice put the drift routes ahead of every route; `tests/test_foundation_suite_equivalence.py` (an existing
pin of the base route order) failed in the full run. Fixed in 1330118895831f2b88d485b5d2f33027f18c1196: a drift route
replaces its base route in place or goes just before its panel's first route; the existing test is the regression test.

## Review-found items

None yet.
