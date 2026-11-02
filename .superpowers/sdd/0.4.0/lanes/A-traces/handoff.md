# Lane A-traces handoff

Implementer: Codex gpt-6-luna (high)
Lane plan: `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/A-traces.md`
Branch / worktree: `lane/0.4.0-A-traces` in `C:\development\github\sharpit-wt\0.4.0-A-traces`, from `release/0.4.0` at `34f1689`

## Fix round 1 (2026-11-02)

- Fix commit: `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578`; UI red commit: `654544674d606cf4a6510897049067396df2edea`.
- Status: DONE_WITH_CONCERNS. All requested changes are implemented except the conflicting legacy FULL-exposure
  assertion, which cannot be edited under red-body immutability and contradicts the new `capture_parameters=False`
  assertion. The new behavior follows SQL Trace and the fix-round requirement; this is recorded as parked in findings.md.
- Results: ruff check and format passed; pyright 0 errors; safety/masking matrix 1027 passed; focused trace tests 65
  passed / 1 legacy failure; UI check clean and vitest 35 files / 280 passed; isolated trace/SQL/request overhead tests
  3 passed. Full suite (-n 4, OTel SDK extra) 4271 passed, 9 skipped, 3 failed: the legacy assertion and host-wide
  SQL/request budgets (parallel run; isolated rerun passed, 3/3).
- The tests at each fix-round red SHA and their assertion messages are recorded below. No test body was edited after its
  red commit. Lowest-direct and no-SQLAlchemy remain coordinator gates.

### Fix round 1 Python reds

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/capture/test_traces.py::test_otel_normalised_set_cookie_header_is_masked` | `2a4dacb585dc6f49e31cd67cc2a01c37a35ef3a4` | `assert '[sid=abc123; HttpOnly]' == '[******]'` |
| `tests/engine/capture/test_traces.py::test_header_attribute_values_go_through_text_masking` | `2a4dacb585dc6f49e31cd67cc2a01c37a35ef3a4` | `assert 'hunter2' not in 'retry after login password=hunter2'` |
| `tests/engine/capture/test_traces.py::test_status_message_drops_driver_echoed_values` | `02fad99cd50e9d8d1e640a1fc315b98ddc9728c2` | `assert 'alice@example.com' not in statusMessage` |
| `tests/engine/capture/test_traces.py::test_status_message_normalises_the_sql_statement` | `02fad99cd50e9d8d1e640a1fc315b98ddc9728c2` | `assert 'hunter2' not in statusMessage` |
| `tests/engine/capture/test_traces.py::test_exception_event_message_gets_the_sql_handling` | `02fad99cd50e9d8d1e640a1fc315b98ddc9728c2` | `assert 'alice@example.com' not in event message` |
| `tests/engine/capture/test_traces.py::test_exception_event_stacktrace_gets_the_sql_handling` | `02fad99cd50e9d8d1e640a1fc315b98ddc9728c2` | `assert 'hunter2' not in event stacktrace` |
| `tests/engine/capture/test_traces.py::test_db_statement_parameters_hidden_unless_capture_parameters` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert "('alice@example.com',)" == '******'` |
| `tests/engine/capture/test_traces.py::test_db_query_parameter_hidden_unless_capture_parameters` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert 'alice@example.com' == '******'` |
| `tests/engine/capture/test_traces.py::test_bind_parameter_attributes_shown_with_capture_parameters` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert '******' == 'alice@example.com'` |
| `tests/engine/capture/test_traces.py::test_full_exposure_without_capture_parameters_still_hides_sql_literals` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert "... 'hunter2'" == '... ?'` |
| `tests/engine/capture/test_traces.py::test_capture_parameters_shows_sql_literals` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert '... ?' == "... 'alice'"` |
| `tests/engine/capture/test_traces.py::test_detail_applies_the_live_capture_parameters_policy_on_every_read` | `a5395192b4721875d9cfbb5ac44e9246efaee642` | `assert 'alice' in first` |
| `tests/engine/capture/test_traces.py::test_span_name_goes_through_text_masking` | `a3042175862b87ced81fdd96c2ae5dbfc77fe8b7` | `assert 'hunter2' not in span name` |
| `tests/engine/capture/test_traces.py::test_root_span_name_goes_through_text_masking` | `a3042175862b87ced81fdd96c2ae5dbfc77fe8b7` | `assert 'hunter2' not in root span name` |
| `tests/engine/capture/test_traces.py::test_event_name_goes_through_text_masking` | `a3042175862b87ced81fdd96c2ae5dbfc77fe8b7` | `assert 's3cr3tvalue1' not in event name` |
| `tests/engine/test_otel.py::test_unset_provider_is_never_resolved_through_the_getter` | `89e4808460958904cc755e2609779a5d51bcb600` | `assert calls == []` |
| `tests/engine/test_otel.py::test_unset_provider_is_unavailable` | `89e4808460958904cc755e2609779a5d51bcb600` | `assert None == NOT_SDK_PROVIDER` |
| `tests/engine/test_otel.py::test_set_provider_is_read_from_the_global` | `89e4808460958904cc755e2609779a5d51bcb600` | `assert calls == []` |
| `tests/engine/capture/test_traces.py::test_spans_of_sharpit_internal_work_never_reach_the_buffer` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert retained == 0` |
| `tests/engine/capture/test_traces.py::test_spans_of_sharpit_event_streams_never_reach_the_buffer` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert retained == 0` |
| `tests/engine/capture/test_traces.py::test_a_sharpit_server_span_takes_no_capacity` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert [] == [trace A]` |
| `tests/engine/capture/test_traces.py::test_the_self_path_check_strips_the_root_path` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert traces == []` |
| `tests/engine/capture/test_traces.py::test_children_of_a_sharpit_request_take_no_capacity` | `aa6749489d3fab8ea99a4ae7ae28827bfb45de63` | `assert [] == [trace A]` |
| `tests/engine/capture/test_traces.py::test_reason_when_the_attacher_never_ran` | `4e55e328b373dfea0a4dfe44a12d3e57220bf910` | `assert '...restart...' == ''` |
| `tests/engine/capture/test_traces.py::test_reason_after_detach` | `4e55e328b373dfea0a4dfe44a12d3e57220bf910` | `assert '...restart...' == ''` |
| `tests/engine/capture/test_traces.py::test_reason_when_the_provider_was_set_late` | `4e55e328b373dfea0a4dfe44a12d3e57220bf910` | `assert '...restart...' == NOT_ARMED` |
| `tests/fastapi/test_traces_api.py::test_detail_matches_the_bootui_span_records` | `02073e24a9d701c16710786a918e7d9000da9713` | `assert problems == []` |
| `tests/fastapi/test_traces_api.py::test_server_root_path_hides_sharpit_server_spans` | `02073e24a9d701c16710786a918e7d9000da9713` | `assert body['traces'] == []` |

### Fix round 1 UI reds

| Test | Commit | Assertion |
|---|---|---|
| `ui/tests/component/traces.test.ts::shows span status and event details` | `654544674d606cf4a6510897049067396df2edea` | expected `unique violation detail` to render |
| `ui/tests/component/traces.test.ts::ignores a stale detail response after another trace was opened` | `654544674d606cf4a6510897049067396df2edea` | expected newest detail `span new` to survive stale response |

## Status

- Task 1 gatekeeper `engine/otel.py`: red `fc029df`, fix `1ed24eb`.
- Task 2 `SpanBuffer` + DTOs `engine/capture/traces.py`: red `be36585`, fix `311852b`.
- Task 3 routes, MCP tools, flag, safety/masking/budget: red `8ff1c1f`, fix `5a78185`.
- Live-check finding (SQL literal leak): red `c4c7d9d`, fix `c7b269a`.
- Task 4 Svelte view: UI red `e71dbc2`, fix in the evidence commit (`feat: traces view and lane evidence`).
- Status: DONE_WITH_CONCERNS (fix round 1 current results are above; no SDK dependency was added to protected files).

## Gates (implementer, at the lane head)

At `2789561`: `ruff check` all passed; `ruff format --check` 476 files formatted; `pyright` 0 errors;
`pytest -q -n 4` **4246 passed, 9 skipped** in 391 s (log
`C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/A-traces-pytest-final.log`).
UI: `npm --prefix ui run check` clean; `npx vitest run` 35 files / 278 tests passed.
An earlier full run had 5 `no_side_effects` errors caused by my own evidence edits mid-run and the two known
load-sensitive budgets (SQL listener, capture); all 1160 of those files' tests passed in isolation, and the final run
above is clean. Budgets untouched. Lowest-direct / no-SQLAlchemy: not run (coordinator gate).

## Decisions and deviations

This fix-round section at the top supersedes gate counts and detail-parity notes below.

1. **No OTel SDK in the test extra.** The lane plan expected F-rest to add `opentelemetry-sdk` to the test extra; it is
   not there (`pyproject.toml`/`uv.lock` are protected). Every test plants an SDK-shaped provider in `sys.modules` and
   delivers spans through the real `otel.PROCESSOR.on_end`, exactly the SDK's call. A real-SDK smoke run is under Live
   check.
2. **Interfaces differ from the plan text** (current code wins): `otel.attach(sink) -> remover | None` and
   `otel.disarm(sink)` take the span sink, not `ctx`, so the returned remover plugs straight into F's
   `CaptureState.attachers` contract (a remover arms, `None` retries). `SpanBuffer.arm` is the attacher.
3. **Where the attacher is registered.** `install.py` is outside the May-touch list and runs `attach_at_install` before
   the routes are built, so `routes/traces.py::build_routes` appends `buffer.arm` to `ctx.capture.attachers` and sets
   F's `CaptureWiring.span_processor = otel.PROCESSOR` there. Arming happens at lifespan startup, or at the first request
   when the host has no lifespan (F's attacher mechanism); `fastapi/capture.py` is untouched. A GET/MCP read never
   attaches (`test_attach_never_during_request`, `test_get_never_attaches_or_writes`).
4. **One processor per provider ever**: identity list `PROCESSOR.providers`; shutdown only disarms the sink (the SDK
   cannot remove a processor); restart re-arms (`test_shutdown_disarms_and_restart_rearms`).
5. **`capacity` counts spans** (1000), not traces; `retained` counts traces. Bounding spans bounds memory.
6. **`unavailableReason`** added to `TracesReport` (sharpit extension; the golden comparison ignores extra keys).
7. **Route param is `{id}`** (`/traces/{id}`) so the shared safety matrix uses the existing `_PATH_PARAMS["id"]`; no
   conftest edit.
8. **Detail parity**: G0a captured only the list (`captured.json`); the detail fields are checked against BootUI's
   `TraceDetailDto`, `SpanDto`, `SpanEventDto`, and `SpanAttributeDto` record sources by
   `tests/fastapi/test_traces_api.py::test_detail_matches_the_bootui_span_records`.
9. **`SpanAttributeDto.value` is emitted as a masked string** and `type` is the Java `AttributeType` name; source
   records were read from the read-only `C:\development\github\boot-ui-ref` checkout.
10. The vitest file is `ui/tests/component/traces.test.ts` (repo convention and include pattern), not beside the view.

## Needs from coordinator

1. Add `opentelemetry-sdk` to the test extra (protected `pyproject.toml`/`uv.lock`) if a real-SDK test and the
   `examples/fastapi_sqla` live check should run in CI.
2. `src/sharpit/ui/static/` is not rebuilt (lanes never run `npm run build`).
3. Merge `docs.md` into README / `skills/sharpit/SKILL.md` (O3).

## Red tests

| Test | Red SHA | Assertion |
|---|---|---|
| tests/engine/test_otel.py::test_no_sdk_is_unavailable | fc029df6ae26c5774cba3684ed56f774d0f185cc | `assert None == 'OpenTelemetry SDK is not imported by this application'` |
| tests/engine/test_otel.py::test_proxy_provider_is_unavailable | fc029df6ae26c5774cba3684ed56f774d0f185cc | `assert None == 'The global tracer provider is not an SDK TracerProvider'` |
| tests/engine/test_otel.py::test_attach_adds_once | fc029df6ae26c5774cba3684ed56f774d0f185cc | `assert [] == [<SharpitSpanProcessor>]` |
| tests/engine/test_otel.py::test_disarm_stops_delivery | fc029df6ae26c5774cba3684ed56f774d0f185cc | `assert None is not None` |
| tests/engine/test_otel.py::test_on_end_raising_is_swallowed | fc029df6ae26c5774cba3684ed56f774d0f185cc | `assert [] == ['span']` |
| tests/engine/capture/test_traces.py::test_summary_exposes_http_path_from_root_server_span | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert 0 == 1` |
| tests/engine/capture/test_traces.py::test_summary_falls_back_to_server_span_when_root_has_no_path | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert 0 == 1` |
| tests/engine/capture/test_traces.py::test_summary_leaves_http_path_null_when_no_path_attribute_is_present | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert 0 == 1` |
| tests/engine/capture/test_traces.py::test_list_and_detail_hide_sharpit_self_traces | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert [] == ['2ebe213f5ee...4077f5f4dc74']` |
| tests/engine/capture/test_traces.py::test_summary_masks_matrix_parameters_of_the_http_path | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert 0 == 1` |
| tests/engine/capture/test_traces.py::test_summary_never_returns_the_authority_of_an_absolute_url | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert 0 == 1` |
| tests/engine/capture/test_traces.py::test_detail_applies_the_live_exposure_policy_on_every_read | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert None is not None` |
| tests/engine/capture/test_traces.py::test_span_reads_mask_nested_values | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert None is not None` |
| tests/engine/capture/test_traces.py::test_summary_and_span_dto_keys | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert 0 == 1` |
| tests/engine/capture/test_traces.py::test_event_offsets_are_relative_to_the_span_start | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert None is not None` |
| tests/engine/capture/test_traces.py::test_list_is_newest_first_and_limited | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert [] == ['c9bdc3cbe2a...355d78db82b4']` |
| tests/engine/capture/test_traces.py::test_capacity_bounds_retained_spans | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert 0 == 2` |
| tests/engine/capture/test_traces.py::test_one_processor_per_provider_across_reinstall | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert None is not None` |
| tests/engine/capture/test_traces.py::test_report_says_why_traces_are_unavailable | be3658575fbfb67a17ed15f0aaa57572d87e78f2 | `assert True is False` |
| tests/fastapi/test_traces_api.py::test_golden_parity | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 200` |
| tests/fastapi/test_traces_api.py::test_list_reports_enabled_newest_first | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 200` |
| tests/fastapi/test_traces_api.py::test_detail_returns_spans | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 200` |
| tests/fastapi/test_traces_api.py::test_limit_clamped | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 200` |
| tests/fastapi/test_traces_api.py::test_limit_not_a_number_is_400 | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 400` |
| tests/fastapi/test_traces_api.py::test_unknown_trace_404 | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert {'error': 'Not Found'} == {'error': 'tr...bc not found'}` |
| tests/fastapi/test_traces_api.py::test_clear_204 | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 204` |
| tests/fastapi/test_traces_api.py::test_clear_read_only_403 | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 403` |
| tests/fastapi/test_traces_api.py::test_no_sdk_reports_the_reason | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 200` |
| tests/fastapi/test_traces_api.py::test_attach_never_during_request | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert [] == [<SharpitSpanProcessor>]` |
| tests/fastapi/test_traces_api.py::test_shutdown_disarms_and_restart_rearms | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 404 == 200` |
| tests/fastapi/test_traces_api.py::test_mcp_read_tool_only | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert 'get_traces' in [...]` |
| tests/masking/test_a_traces_masking.py::test_secrets_in_span_attributes_never_appear | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `assert '"spanCount":1' in '{"error":"Not Found"}'` |
| tests/engine/capture/test_traces.py::test_sql_literals_in_db_statement_are_masked | c4c7d9dff61bc13447f4162e25c14caa7b5c95cb | `assert "select * fro...w = 'hunter2'" == 'select * fro... where pw = ?'` |

### Superseded

| Test | Historical SHA | Replaced by |
|---|---|---|
| tests/safety/test_a_traces_safety.py::test_get_no_side_effects | 8ff1c1fcfbdf2d1c4013a7998e5c569f8214cd52 | `test_get_never_attaches_or_writes` (`5a78185`): the old body compared sinks after the lifespan shutdown |

### UI reds

| Test | Commit | Assertion |
|---|---|---|
| ui/tests/component/traces.test.ts (3 tests) | e71dbc2d979f9ecdb09afd90263888cf2ce9549c | `expected 'TracesThis panel's view is not built…' to contain 'GET /owners'` |

## Live check

Real `opentelemetry-sdk` (installed into the lane venv only for this check, then removed with `uv sync --extra test`;
`pyproject.toml` untouched). Script outside the worktree: a FastAPI app sets an SDK `TracerProvider` as the global
provider, `sharpit.install(app, enabled="ON")`, two TestClient lifespans, each `GET /owners` (SERVER span with
`url.full` userinfo + `api_key` query, a CLIENT child with `db.statement` and an event), then list, detail, clear:

- both rounds: list 200 `enabled: true retained: 1`; detail 200 with every span (FastAPI's own INTERNAL spans
  included), durations > 0; `DELETE` 204, then `retained: 0`.
- after two lifespans the provider has exactly one processor: `['SharpitSpanProcessor']`.
- **Finding:** the first run leaked `pw = 'hunter2'` from `db.statement` (`mask_text` masks key=value pairs, not SQL
  literals). Red `c4c7d9d` (`test_sql_literals_in_db_statement_are_masked`), fix `c7b269a` (`normalize_sql` before
  `mask_text`, except FULL exposure). Rerun: no secret in list or detail.

## How to resume

Read `.superpowers/sdd/0.4.0/lanes/A-traces/findings.md`. Current head/evidence commit is
`8f0fced9837f802b6e6204e0ac161876b8c7af3c`; implementation is at `f47d6f2af0d2fff9b71dd5504a9a2a5a62504578`.
The fix-round gates are recorded above; the remaining test conflict
needs a coordinator/owner resolution that respects the immutable red-test rule. The two global budget tests passed
when run alone (`A-traces-overhead-r2.log`). Re-run full suite detached to the integration log directory if a new
policy is chosen. Continue on this lane branch; do not edit review/gate files or push.
