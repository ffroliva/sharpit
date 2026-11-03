# Findings: lane C-fastapi

Reds replayed at each red SHA in a detached worktree with `scripts/dev/red_check.py`: every row `RED (assertion under tests/)`
(log `0.5.0-integration/.superpowers/sdd/0.5.0/logs/C-fastapi-replay.log`). The "remove the rule" proof for every rule is its red:
the red commit ships the rule as a function returning `[]`.

## Reds

| finding | test (node id) | Red SHA | red output (last assertion line) | disposition |
|---|---|---|---|---|
| catalogue missing from registry | tests/test_fastapi_docs_table.py::test_docs_table_matches_registry | da8318e739329286869571edfe751b7f28755fef | `assert [('FASTAPI-AS... model'), ...] == []` | fixed in f61b005 |
| decorator wrapper not unwrapped | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_handlers.py::test_decorated_handler_resolved_to_inner_function | d712ab1417e8e6b0cd2435b606dcf31ee931c70c | `assert [] == ['app_pkg.main:read_items']` | fixed in 5050893 |
| callable instance not reported | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_handlers.py::test_callable_instance_endpoint_skipped_without_getattr | d712ab1417e8e6b0cd2435b606dcf31ee931c70c | `assert [] != []` | fixed in 5050893 |
| partial/library handler not reported | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_handlers.py::test_partial_and_library_handlers_skipped_with_limitation | d712ab1417e8e6b0cd2435b606dcf31ee931c70c | `assert 0 == 1` | fixed in 5050893 |
| blocking call in async | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_blocking_call_in_async_flagged | 3239b0c6513dc13ae17d9197d91785300725a9e9 | `assert 0 == 1` | fixed in 72e6504 |
| sync endpoint I/O | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_sync_endpoint_doing_io_flagged | 3239b0c6513dc13ae17d9197d91785300725a9e9 | `assert 0 == 1` | fixed in 72e6504 |
| heavy background task | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_background_task_heavy_work | 3239b0c6513dc13ae17d9197d91785300725a9e9 | `assert 0 == 1` | fixed in 72e6504 |
| requests without timeout | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_requests_without_timeout_flagged | 3239b0c6513dc13ae17d9197d91785300725a9e9 | `assert 0 == 1` | fixed in 72e6504 |
| inner class Config | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_models.py::test_pydantic_v1_config_class_flagged | 7987b7dca1895549cb6b00db4273b3c4379ddc22 | `assert 0 == 1` | fixed in a021e42 |
| orm_mode | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_models.py::test_orm_mode_flagged | 7987b7dca1895549cb6b00db4273b3c4379ddc22 | `assert 0 == 1` | fixed in a021e42 |
| dict without response model | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_models.py::test_missing_response_model_on_dict_return | 7987b7dca1895549cb6b00db4273b3c4379ddc22 | `assert 0 == 1` | fixed in a021e42 |
| on_event hooks | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_app.py::test_on_event_instead_of_lifespan | f25403ea337e81801ec43d506d67ff595da941bb | `assert 0 == 1` | fixed in 9c9af9f |
| broad except in handler | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_app.py::test_broad_except_in_handler | f25403ea337e81801ec43d506d67ff595da941bb | `assert 0 == 1` | fixed in 9c9af9f |
| debug=True | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_app.py::test_debug_mode_flagged | f25403ea337e81801ec43d506d67ff595da941bb | `assert 0 == 1` | fixed in 9c9af9f |
| default title | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_app.py::test_default_title_flagged | f25403ea337e81801ec43d506d67ff595da941bb | `assert 0 == 1` | fixed in 9c9af9f |
| violations leak no secret (every category flagged) | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_app.py::test_violation_never_contains_literal_secret | f25403ea337e81801ec43d506d67ff595da941bb | `assert 'FASTAPI-EXC-001' in {'FASTAPI-ASYNC-001', 'FASTAPI-ASYNC-002', 'FASTAPI-HTTP-001', 'FASTAPI-PYD-001'}` | fixed in 9c9af9f |
| scan reads only the app package | tests/fastapi/test_fastapi_advisor_api.py::test_scan_reads_only_app_package | d3e2768762ece15fc6e746782fe8034c672c44a6 | `assert 404 == 200` | fixed in 8b70c7b |
| scan uses the one resolver | tests/fastapi/test_fastapi_advisor_api.py::test_scan_uses_the_one_resolver | d3e2768762ece15fc6e746782fe8034c672c44a6 | `assert 404 == 200` | fixed in 8b70c7b |
| scan flags + violations page | tests/fastapi/test_fastapi_advisor_api.py::test_scan_flags_blocking_call_and_pages_violations | d3e2768762ece15fc6e746782fe8034c672c44a6 | `assert 404 == 200` | fixed in 8b70c7b |
| GET after scan opens no source | tests/fastapi/test_fastapi_advisor_api.py::test_get_after_scan_opens_no_source_file | d3e2768762ece15fc6e746782fe8034c672c44a6 | `assert 404 == 200` | fixed in 8b70c7b |
| GET no side effects | tests/fastapi/test_fastapi_advisor_api.py::test_fastapi_get_no_side_effects | d3e2768762ece15fc6e746782fe8034c672c44a6 | `assert 404 == 200` | fixed in 8b70c7b |
| read-only blocks scan | tests/fastapi/test_fastapi_advisor_api.py::test_read_only_blocks_scan | d3e2768762ece15fc6e746782fe8034c672c44a6 | `assert 404 == 200` | fixed in 8b70c7b |
| MCP lists reads only | tests/fastapi/test_fastapi_advisor_api.py::test_mcp_tools_list_has_only_get | d3e2768762ece15fc6e746782fe8034c672c44a6 | `assert 'get_fastapi_report' in set()` | fixed in 8b70c7b |
| CLI scan runs | tests/fastapi/test_fastapi_advisor_api.py::test_cli_scan_runs_the_advisor | d3e2768762ece15fc6e746782fe8034c672c44a6 | `assert 404 == 200` | fixed in 8b70c7b |

## Pins (pass on first run; mutation-proven in a scratch worktree, `scratchpad/cfa-mutate.py`)

| finding | test (node id) | resolution |
|---|---|---|
| pre-scan golden | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_report.py::test_report_golden_parity | pin: `_scope` without `inspected` -> `fastapi/captured.json parity: inspected: missing from payload` |
| await asyncio.sleep is not blocking | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_await_asyncio_sleep_not_flagged | pin: `_blocking` returns True for any call -> `assert ['GET /fine (...ep (line 13)'] == []` |
| pure sync endpoint not flagged | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_sync_endpoint_without_io_not_flagged | pin: flag every sync handler (`if calls` -> `if True`) -> `assert ['GET /pure (...pure) calls '] == []` |
| inactive paths 404 | tests/fastapi/test_fastapi_advisor_api.py::test_inactive_fastapi_paths_404 | pin: adapter `_not_found` answers 200 instead of raising 404 -> `assert 200 == 404` |
| post-scan golden | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_report.py::test_post_scan_golden_parity | N/A — skips `post-scan golden absent` until G0 |

## Extra mutations on safety rules (fixed code, scratch copy)

| rule | mutation | test that fails |
|---|---|---|
| `type(fn) is FunctionType` before any attribute read | `if not callable(endpoint)` | tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_handlers.py::test_callable_instance_endpoint_skipped_without_getattr (`AttributeError: __code__` raised by the counting `__getattr__`: the instance was asked) |
| scan indexes only the resolved root | index `textwrap.py` instead | tests/fastapi/test_fastapi_advisor_api.py::test_scan_reads_only_app_package (`assert ['C:\Users\...\textwrap.py'] == []`) |

## UI red

| test | Commit | output |
|---|---|---|
| ui/tests/component/Fastapi.test.ts (2 tests) | bbc8d9f435defd68902bde772f84126ee9be52a5 | `AssertionError: expected 'FastAPIThis panel's view is not buil…' to contain 'Not scanned yet'` |


Note: a first draft of the API test commit had three crash reds (KeyError, ValueError); it was reset before any
report and recommitted as d3e2768 with assertion-first checks, so no superseded red exists on the branch.
