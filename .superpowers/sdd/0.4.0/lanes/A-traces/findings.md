# Findings

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| No gatekeeper reason without the SDK | `tests/engine/test_otel.py::test_no_sdk_is_unavailable` | `fc029df6ae26c5774cba3684ed56f774d0f185cc` | `assert None == 'OpenTelemetry SDK is not imported by this application'` | Fixed in `1ed24eb` |
| No-op provider not detected | `tests/engine/test_otel.py::test_proxy_provider_is_unavailable` | `fc029df6ae26c5774cba3684ed56f774d0f185cc` | `assert None == 'The global tracer provider is not an SDK TracerProvider'` | Fixed in `1ed24eb` |
| Processor not added to the provider | `tests/engine/test_otel.py::test_attach_adds_once` | `fc029df6ae26c5774cba3684ed56f774d0f185cc` | `assert [] == [<SharpitSpanProcessor>]` | Fixed in `1ed24eb` |
| No remover / disarm | `tests/engine/test_otel.py::test_disarm_stops_delivery` | `fc029df6ae26c5774cba3684ed56f774d0f185cc` | `assert None is not None` | Fixed in `1ed24eb` |
| A failing sink must not stop delivery | `tests/engine/test_otel.py::test_on_end_raising_is_swallowed` | `fc029df6ae26c5774cba3684ed56f774d0f185cc` | `assert [] == ['span']` | Fixed in `1ed24eb` |
| Summary path from root server span | `tests/engine/capture/test_traces.py::test_summary_exposes_http_path_from_root_server_span` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert 0 == 1` | Fixed in `311852b` |
| Path fallback to a server span | `tests/engine/capture/test_traces.py::test_summary_falls_back_to_server_span_when_root_has_no_path` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert 0 == 1` | Fixed in `311852b` |
| Null path without attributes | `tests/engine/capture/test_traces.py::test_summary_leaves_http_path_null_when_no_path_attribute_is_present` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert 0 == 1` | Fixed in `311852b` |
| sharpit's own traces listed | `tests/engine/capture/test_traces.py::test_list_and_detail_hide_sharpit_self_traces` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert [] == ['2ebe213f5ee...4077f5f4dc74']` | Fixed in `311852b` |
| Matrix parameters unmasked | `tests/engine/capture/test_traces.py::test_summary_masks_matrix_parameters_of_the_http_path` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert 0 == 1` | Fixed in `311852b` |
| Absolute URL authority shown | `tests/engine/capture/test_traces.py::test_summary_never_returns_the_authority_of_an_absolute_url` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert 0 == 1` | Fixed in `311852b` |
| Masking not live at read | `tests/engine/capture/test_traces.py::test_detail_applies_the_live_exposure_policy_on_every_read` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert None is not None` | Fixed in `311852b` |
| Nested attribute secrets | `tests/engine/capture/test_traces.py::test_span_reads_mask_nested_values` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert None is not None` | Fixed in `311852b` |
| DTO keys | `tests/engine/capture/test_traces.py::test_summary_and_span_dto_keys` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert 0 == 1` | Fixed in `311852b` |
| Event offsets | `tests/engine/capture/test_traces.py::test_event_offsets_are_relative_to_the_span_start` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert None is not None` | Fixed in `311852b` |
| Order and limit | `tests/engine/capture/test_traces.py::test_list_is_newest_first_and_limited` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert [] == ['c9bdc3cbe2a...355d78db82b4']` | Fixed in `311852b` |
| Unbounded buffer | `tests/engine/capture/test_traces.py::test_capacity_bounds_retained_spans` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert 0 == 2` | Fixed in `311852b` |
| Processor pile-up across reinstall | `tests/engine/capture/test_traces.py::test_one_processor_per_provider_across_reinstall` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert None is not None` | Fixed in `311852b` |
| No unavailable reason | `tests/engine/capture/test_traces.py::test_report_says_why_traces_are_unavailable` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert True is False` | Fixed in `311852b` |
| Panel unimplemented (404) | `tests/fastapi/test_traces_api.py::test_golden_parity` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 200` | Fixed in `5a78185` |
| List route | `tests/fastapi/test_traces_api.py::test_list_reports_enabled_newest_first` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 200` | Fixed in `5a78185` |
| Detail route | `tests/fastapi/test_traces_api.py::test_detail_returns_spans` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 200` | Fixed in `5a78185` |
| Limit clamp | `tests/fastapi/test_traces_api.py::test_limit_clamped` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 200` | Fixed in `5a78185` |
| Non-integer limit | `tests/fastapi/test_traces_api.py::test_limit_not_a_number_is_400` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 400` | Fixed in `5a78185` |
| Unknown trace error body | `tests/fastapi/test_traces_api.py::test_unknown_trace_404` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert {'error': 'Not Found'} == {'error': 'tr...bc not found'}` | Fixed in `5a78185` |
| Clear route | `tests/fastapi/test_traces_api.py::test_clear_204` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 204` | Fixed in `5a78185` |
| Clear when read-only | `tests/fastapi/test_traces_api.py::test_clear_read_only_403` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 403` | Fixed in `5a78185` |
| Unavailable reason over HTTP | `tests/fastapi/test_traces_api.py::test_no_sdk_reports_the_reason` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 200` | Fixed in `5a78185` |
| Never attached at startup | `tests/fastapi/test_traces_api.py::test_attach_never_during_request` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert [] == [<SharpitSpanProcessor>]` | Fixed in `5a78185` |
| Shutdown/restart lifecycle | `tests/fastapi/test_traces_api.py::test_shutdown_disarms_and_restart_rearms` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 404 == 200` | Fixed in `5a78185` |
| MCP read tool | `tests/fastapi/test_traces_api.py::test_mcp_read_tool_only` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert 'get_traces' in [...]` | Fixed in `5a78185` |
| Secrets in span attributes | `tests/masking/test_a_traces_masking.py::test_secrets_in_span_attributes_never_appear` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | `assert '"spanCount":1' in '{"error":"Not Found"}'` | Fixed in `5a78185` |
| Live check: SQL literal in `db.statement` leaked | `tests/engine/capture/test_traces.py::test_sql_literals_in_db_statement_are_masked` | `c4c7d9dff61bc13447f4162e25c14caa7b5c95cb` | `assert "select * fro...w = 'hunter2'" == 'select * fro... where pw = ?'` | Fixed in `c7b269a` |

## Superseded

| Test | Historical SHA | Why |
|---|---|---|
| `tests/safety/test_a_traces_safety.py::test_get_no_side_effects` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | compared the armed sinks after the lifespan shutdown (which correctly disarms); replaced in `5a78185` by `test_get_never_attaches_or_writes`, which reads them inside the lifespan |

## UI reds

| Test | Commit | Assertion message | Disposition |
|---|---|---|---|
| `ui/tests/component/traces.test.ts` (3 tests) | `e71dbc2d979f9ecdb09afd90263888cf2ce9549c` | `expected 'TracesThis panel's view is not built…' to contain 'GET /owners'` | Fixed in the Task 4 commit |
