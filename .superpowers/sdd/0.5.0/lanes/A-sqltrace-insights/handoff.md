# A-sqltrace-insights handoff

Implementer: Claude subagent (claude-opus-5-5)
Branch `lane/0.5.0-A-sqltrace-insights` from `release/0.5.0` 836d3fd. Status: all three tasks done; one open question.

## Commits

| Task | Red | Fix |
|---|---|---|
| 1 engine `sqlinsights.py` | d8097d872e09f4b71a49932295f2478a1a5d4a8c (16 reds) | 8637d672aa80d1f8381c3bcfbfcff7ae9003b062 |
| 2 route, MCP, safety, masking, `nullable.json` | 7c8a1658f1ae5bacce9c6a0085d3d632b4970df0 (6 reds, 1 pin) | 415689ac10f8091816121159b20d599ea76b5974 |
| 3 Insights tab + static bundle | 4510cfa28bce06e45c0dd627bf47b2a2aba30338 (3 vitest reds) | 6885ce7713edf6e428718ba4afac145b93d98d67 |

Red tables, the pin and rule mutations: `findings.md`.

## Must-cover

| Test | Exists | Passes at head |
|---|---|---|
| `tests/fastapi/test_sql_trace_insights_api.py::test_insights_golden_parity` | yes | yes |
| `tests/safety/test_a_sqltrace_insights_safety.py::test_insights_get_no_side_effects` | yes | yes |
| `tests/masking/test_a_sqltrace_insights_masking.py::test_insights_statement_text_masked` | yes | yes |
| `tests/fastapi/test_sql_trace_insights_api.py::test_mcp_tools_list_has_only_get` | yes | yes |

## OPEN QUESTION for the coordinator (file outside May-touch, not edited)

`tests/fastapi/test_sql_trace_api.py::test_insights_404` (0.3.0) pins `GET /sql-trace/insights` -> 404 and now fails
(200), as this lane's goal requires. It is outside May-touch, so it is not edited here. Proposed resolution: delete
it; `test_insights_golden_parity` and `test_insights_unavailable_when_tracing_off` supersede it (with tracing off the
route answers 200 `available:false`, as BootUI does, so no 404 variant remains to pin).

## Decisions (deviations from the 0.4.0 lane plan, logged)

1. `supportedCorrelations == ["TRACE_ID"]`, not `["request"]`: BootUI's enum name for the exact join sharpit does
   (row `traceId` = capture request id = exchange `id`). Thread and time-window tiers are not offered (counts 0).
2. `MAX_ROUTES = 20` (BootUI `SqlRouteAttribution.MAX_ROUTES`), not "top 10" from the plan's constraint line.
3. Routes are grouped by masked path (`RoutePathMasker` port), `routeSource = MASKED_PATH`: exchange rows carry only
   an endpoint qualname, no route template, and `fastapi/capture.py` is outside May-touch.
4. `potentialNPlusOne` uses 5 (BootUI uses `DEFAULT_N_PLUS_ONE_THRESHOLD` here, not the setting).
5. `window.evicted`/`totalCaptured` come from the public `recorder.report([])`, not the private `_evicted`.
6. With HTTP exchange capture off (`capture.exchanges is None`) attribution is `available:false` with a sharpit
   reason; the statement rankings stay available (BootUI's "cannot supply request evidence" path).
7. The BootUI note advising OpenTelemetry for trace ids is adapted (sharpit's request id comes from its own middleware).
8. The MCP tool `get_sql_trace_insights` (read) and CLI command `sql-trace insights` are sharpit-only: BootUI has no
   insights MCP tool. The UI types live in `SqlTrace.svelte` (types.ts is not in May-touch).
9. Brief overrides COMMON: `npm run build` ran and the rebuilt `src/sharpit/ui/static/` bundle is committed in 6885ce7.

## Live check

In-process (no port), `examples/fastapi_sqla.create_app(db_dir=<tmp>, enabled="ON")` with its lifespan, script
`live.py` in the session scratchpad:
`GET /owners` 200, `GET /owners/n-plus-one` 200 x2, `GET /owners/7` 404, then `GET /sharpit/api/sql-trace/insights` 200:
window 10 retained of 200, 4 distinct statements, routes `GET /owners` (1 request, 2 executions) and
`GET /owners/n-plus-one` (2 requests, 4 executions), 4 unattributed (lifespan seeding), notes as BootUI.
`GET /sharpit/` 200. All durations 0 ms on SQLite (whole-ms ring; findings.md).

## Gates (lane run)

- `ruff check`: All checks passed. `ruff format --check`: 553 files already formatted. `pyright`: 0 errors.
- vitest `sqlTraceInsights.test.ts` + `sqlTrace.test.ts`: 10 passed; `npm run check` clean; `npm run build` done.
- Full suite `pytest -q -n 4` at 6885ce7 (log `0.5.0-integration/.superpowers/sdd/0.5.0/logs/A-sqltrace-insights-pytest.log`):
  5 failed, 4677 passed, 9 skipped, 2 errors. Triage:
  - `test_sql_trace_api.py::test_insights_404`: expected, the open question above.
  - 2 errors (`test_epss.py::test_invalid_rows_fail[rows2]`, `test_log_tail_api.py::test_get_log_tail_mcp`): mine, but
    process only: I wrote these evidence files into the worktree during the run (`cwd changed: ...checklist.md`).
    Rerun alone: pass.
  - `test_n_plus_one_overhead.py` and `test_overhead_harness.py::test_every_budget_module_runs_last`: pass on rerun
    alone (log `A-sqltrace-insights-rerun.log`).
  - `test_capture_overhead.py::test_request_overhead_budget`, `test_sql_trace_overhead.py::test_statement_overhead_budget`:
    still fail alone, and fail identically on the untouched base 836d3fd in a detached worktree (0.209 ms / 54.6 us vs
    budgets 0.200 ms / 50 us, "within the noise: suspect a busy machine"). Not this lane: it adds no hot-path code.
    Budgets untouched.

## How to resume

Nothing left but the coordinator's answer above, review, and the merge gate.
