# A-sqltrace-insights findings

Implementer: Claude subagent (claude-opus-5-5)

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/capture/test_sqlinsights.py::test_reports_unavailable_when_tracing_is_off | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert report["available"] is False`: the skeleton answered available | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_still_ranks_statements_when_the_runtime_cannot_supply_request_evidence | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert len(report["statements"]) == 1`: 0 ranked | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_describes_the_bounded_window_the_rankings_cover | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert window["retainedStatements"] == 2`: 0 | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_warns_when_older_executions_have_already_been_evicted | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert report["window"]["retainedStatements"] == 2`: 0 | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_says_the_figures_describe_the_retained_window_rather_than_lifetime_totals | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert any("not lifetime metrics" in note ...)`: no notes | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_reports_paused_recording_so_a_stale_window_is_not_mistaken_for_a_quiet_system | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert report["capturing"] is False`: True | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_never_exposes_bound_parameters_even_when_capture_is_on | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert [s["sql"] ...] == ["select * from users where email = ?"]`: [] | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_attributes_recorded_statements_to_the_supplied_requests | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert [r["route"] ...] == ["/api/orders"]`: [] | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_rankings_are_deterministic_on_ties | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert [s["id"] ...] == ["select * from a", "select * from b", "select * from c"]`: [] | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_unattributed_bucket_reason | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert attribution["unattributed"]["executions"] == 2`: 0 | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_top_for_names_the_criteria_verbatim | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert [s["topFor"] ...] == [[...7 criteria]]`: [] | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_only_the_top_ten_per_criterion_are_listed | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert len(report["statements"]) == 10`: 0 | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_route_without_template_is_grouped_by_masked_path | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert [(id, routeSource, requests)] == [("GET /orders/{value}", "MASKED_PATH", 2)]`: [] | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_n_plus_one_flag_on_repeated_select | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert [s["potentialNPlusOne"] ...] == [True]`: [] | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_percentile_is_nearest_rank | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert percentile(list(range(1, 21)), 95) == 19`: 0 | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/engine/capture/test_sqlinsights.py::test_mask_route_masks_value_segments | d8097d872e09f4b71a49932295f2478a1a5d4a8c | `assert mask_route(...) == "/orders/{value}/items/{value}/{value}/report.pdf"`: path unchanged | Fixed in 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| tests/fastapi/test_sql_trace_insights_api.py::test_insights_golden_parity | 7c8a1658f1ae5bacce9c6a0085d3d632b4970df0 | `assert response.status_code == 200`: 404 (route absent) | Fixed in 415689ac10f8091816121159b20d599ea76b5974 |
| tests/fastapi/test_sql_trace_insights_api.py::test_insights_attributes_requests_to_masked_routes | 7c8a1658f1ae5bacce9c6a0085d3d632b4970df0 | `assert response.status_code == 200`: 404 | Fixed in 415689ac10f8091816121159b20d599ea76b5974 |
| tests/fastapi/test_sql_trace_insights_api.py::test_insights_unavailable_when_tracing_off | 7c8a1658f1ae5bacce9c6a0085d3d632b4970df0 | `assert response.status_code == 200`: 404 | Fixed in 415689ac10f8091816121159b20d599ea76b5974 |
| tests/fastapi/test_sql_trace_insights_api.py::test_mcp_tools_list_has_only_get | 7c8a1658f1ae5bacce9c6a0085d3d632b4970df0 | `assert [n for n in names if "insights" in n] == ["get_sql_trace_insights"]`: [] | Fixed in 415689ac10f8091816121159b20d599ea76b5974 |
| tests/safety/test_a_sqltrace_insights_safety.py::test_insights_get_no_side_effects | 7c8a1658f1ae5bacce9c6a0085d3d632b4970df0 | `assert response.status_code == 200`: 404 | Fixed in 415689ac10f8091816121159b20d599ea76b5974 |
| tests/masking/test_a_sqltrace_insights_masking.py::test_insights_statement_text_masked | 7c8a1658f1ae5bacce9c6a0085d3d632b4970df0 | `assert response.status_code == 200`: 404 | Fixed in 415689ac10f8091816121159b20d599ea76b5974 |

`red_check.py` said RED (assertion under tests/) for all 22 before each `test:` commit. The Task 1 skeleton returned a
fully keyed, empty, *available* report; Task 2's reds hit the absent route (404) and the empty `TOOLS`.

## UI reds (vitest)

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| ui/tests/component/sqlTraceInsights.test.ts > Insights: notes and the window are shown | 4510cfa28bce06e45c0dd627bf47b2a2aba30338 | `expected undefined to be truthy` (no Insights tab) | Fixed in 6885ce7713edf6e428718ba4afac145b93d98d67 |
| ui/tests/component/sqlTraceInsights.test.ts > Insights: the criterion switcher re-ranks the statements | 4510cfa28bce06e45c0dd627bf47b2a2aba30338 | `expected undefined to be truthy` | Fixed in 6885ce7713edf6e428718ba4afac145b93d98d67 |
| ui/tests/component/sqlTraceInsights.test.ts > Insights: the route table and the unattributed bucket | 4510cfa28bce06e45c0dd627bf47b2a2aba30338 | `expected undefined to be truthy` | Fixed in 6885ce7713edf6e428718ba4afac145b93d98d67 |

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|
| tests/fastapi/test_sql_trace_insights_api.py::test_insights_respects_panel_disabled | 7c8a1658f1ae5bacce9c6a0085d3d632b4970df0 | `guard._panel_access`: `if not flags.enabled` -> `if False` (the guard answers 403 by path prefix, so it passed before the route existed) | `assert response.status_code == 403` |

## Rule mutations (each new rule removed in place, the named test run, the file restored with `git checkout`)

| Rule | Mutation | Failing test(s) |
|---|---|---|
| Group and show by re-normalised stored text (never the literal) | `shape = normalize(...)._replace(sql=row["sql"], fingerprint=row["sql"])` | `test_never_exposes_bound_parameters_even_when_capture_is_on`, `test_insights_statement_text_masked` |
| Ties broken by fingerprint ascending | sort key `(-metric, "")` | `test_rankings_are_deterministic_on_ties` |
| A trace id whose exchange is gone stays unattributed | fall back to the first retained request | `test_unattributed_bucket_reason` |
| `null`/`undefined` path segments are values | reserved-word check removed | `test_mask_route_masks_value_segments` |
| MCP tool is read-only | `action=True` | `test_mcp_tools_list_has_only_get` |

## Observations

- SQLite statements on the live check took under 1 ms, so every duration and share is 0 (the ring stores whole ms;
  BootUI uses micros). Rankings still fall back to `EXECUTIONS`; logged as a known limitation.
