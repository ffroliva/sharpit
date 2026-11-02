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
| SQL cleanup truncated non-SQL tracebacks | `tests/engine/capture/test_traces.py::test_non_sql_stacktrace_keeps_its_frames` | `d1a2bf2a45203c950ce013bb923aec36c1b87cf4` | `assert shown == trace` (traceback reduced to header) | Fixed in `0fd9a2cca974a3a8e07232f03d72e096b1c7a841` |
| SQL cleanup rewrote non-SQL exception messages | `tests/engine/capture/test_traces.py::test_non_sql_exception_message_uses_text_masking_only` | `d1a2bf2a45203c950ce013bb923aec36c1b87cf4` | `assert shown == message` (`'abc'` changed to `?`) | Fixed in `0fd9a2cca974a3a8e07232f03d72e096b1c7a841` |
| SQL traceback cleanup dropped Python frames | `tests/engine/capture/test_traces.py::test_sql_exception_stacktrace_keeps_python_frames` | `10d35a242ef7cde7af331f386b3485406f61d4cf` | `assert 'File "app.py", line 3' in shown` | Fixed in `0fd9a2cca974a3a8e07232f03d72e096b1c7a841` |

## Superseded

| Test | Historical SHA | Why |
|---|---|---|
| `tests/safety/test_a_traces_safety.py::test_get_no_side_effects` | `8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52` | compared the armed sinks after the lifespan shutdown (which correctly disarms); replaced in `5a78185` by `test_get_never_attaches_or_writes`, which reads them inside the lifespan |

## UI reds

| Test | Commit | Assertion message | Disposition |
|---|---|---|---|
| `ui/tests/component/traces.test.ts` (3 tests) | `e71dbc2d979f9ecdb09afd90263888cf2ce9549c` | `expected 'TracesThis panel's view is not built…' to contain 'GET /owners'` | Fixed in the Task 4 commit |

## Fix round 1 reds

| Test | Red SHA | Assertion | Disposition |
|---|---|---|---|
| `tests/engine/capture/test_traces.py::test_otel_normalised_set_cookie_header_is_masked` | `2a4dacb585dc6f49e31cd67cc2a01c37a35ef3a4` | `assert '[sid=abc123; HttpOnly]' == '[******]'` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_header_attribute_values_go_through_text_masking` | `2a4dacb585dc6f49e31cd67cc2a01c37a35ef3a4` | `assert 'hunter2' not in 'retry after login password=hunter2'` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_status_message_drops_driver_echoed_values` | `02fad99cd50e9d8d1e640a1fc315b98ddc9728c2` | `assert 'alice@example.com' not in statusMessage` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_status_message_normalises_the_sql_statement` | `02fad99cd50e9d8d1e640a1fc315b98ddc9728c2` | `assert 'hunter2' not in statusMessage` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_exception_event_message_gets_the_sql_handling` | `02fad99cd50e9d8d1e640a1fc315b98ddc9728c2` | `assert 'alice@example.com' not in event message` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_exception_event_stacktrace_gets_the_sql_handling` | `02fad99cd50e9d8d1e640a1fc315b98ddc9728c2` | `assert 'hunter2' not in event stacktrace` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_db_statement_parameters_hidden_unless_capture_parameters` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert "[('alice@example.com',)]" == '******'` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_db_query_parameter_hidden_unless_capture_parameters` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert 'alice@example.com' == '******'` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_bind_parameter_attributes_shown_with_capture_parameters` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert '******' == 'alice@example.com'` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_full_exposure_without_capture_parameters_still_hides_sql_literals` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert "... 'hunter2'" == '... ?'` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_capture_parameters_shows_sql_literals` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert '... ?' == "... 'alice'"` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_detail_applies_the_live_capture_parameters_policy_on_every_read` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert 'alice' in first` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_span_name_goes_through_text_masking` | `a3042175862b87ced81fdd96c2ae5dbfc77fe8b7` | `assert 'hunter2' not in span name` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_root_span_name_goes_through_text_masking` | `a3042175862b87ced81fdd96c2ae5dbfc77fe8b7` | `assert 'hunter2' not in root span name` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_event_name_goes_through_text_masking` | `a3042175862b87ced81fdd96c2ae5dbfc77fe8b7` | `assert 's3cr3tvalue1' not in event name` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/test_otel.py::test_unset_provider_is_never_resolved_through_the_getter` | `89e4808460958904cc755e2609779a5d51bcb600` | `assert calls == []` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/test_otel.py::test_unset_provider_is_unavailable` | `89e4808460958904cc755e2609779a5d51bcb600` | `assert None == NOT_SDK_PROVIDER` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/test_otel.py::test_set_provider_is_read_from_the_global` | `89e4808460958904cc755e2609779a5d51bcb600` | `assert calls == []` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_spans_of_sharpit_internal_work_never_reach_the_buffer` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert retained == 0` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_spans_of_sharpit_event_streams_never_reach_the_buffer` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert retained == 0` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_a_sharpit_server_span_takes_no_capacity` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert [] == [trace A]` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_the_self_path_check_strips_the_root_path` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert traces == []` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_children_of_a_sharpit_request_take_no_capacity` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert [] == [trace A]` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_reason_when_the_attacher_never_ran` | `4e55e328b373dfea0a4dfe44a12d3e57220bf910` | `assert '...restart...' == ''` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_reason_after_detach` | `4e55e328b373dfea0a4dfe44a12d3e57220bf910` | `assert '...restart...' == ''` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/engine/capture/test_traces.py::test_reason_when_the_provider_was_set_late` | `4e55e328b373dfea0a4dfe44a12d3e57220bf910` | `assert '...restart...' == NOT_ARMED` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/fastapi/test_traces_api.py::test_detail_matches_the_bootui_span_records` | `02073e24a9d701c16710786a918e7d9000da9713` | `assert problems == []` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `tests/fastapi/test_traces_api.py::test_server_root_path_hides_sharpit_server_spans` | `02073e24a9d701c16710786a918e7d9000da9713` | `assert body['traces'] == []` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |

### Historical SHA

| Test | Historical SHA | Assertion | Reason |
|---|---|---|---|
| `tests/engine/capture/test_traces.py::test_detail_applies_the_live_exposure_policy_on_every_read` | `be3658575fbfb67a17ed15f0aaa57572d87e78f2` | `assert None is not None` | superseded: literals keyed on capture_parameters (fix round 1) |

### UI reds

| Test | Commit | Assertion | Disposition |
|---|---|---|---|
| `ui/tests/component/traces.test.ts::shows span status and event details` | `654544674d606cf4a6510897049067396df2edea` | expected rendered detail to contain `unique violation detail` | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
| `ui/tests/component/traces.test.ts::ignores a stale detail response after another trace was opened` | `654544674d606cf4a6510897049067396df2edea` | expected newest detail to remain `span new` after stale response | Fixed in `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578` |
