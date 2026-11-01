# Lane D2: 2.2.0 Capture Panels Drift (`activity`, `http-exchanges`, `exceptions`, `sql-trace`, `log-tail`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `D2`
- **Goal:** Upgrade the five capture panels (`activity`, `http-exchanges`, `exceptions`, `sql-trace`, `log-tail`) and their MCP/CLI tools to the BootUI 2.2.0 contract (`GET /http-exchanges/routes`, `GET /exceptions/caught`, `GET /activity/journal`, `GET /activity/resources`, `retention` metadata, `durationMicros`, `messageOmitted`, and `get_http_routes` / `get_request_profile` tools).
- **Spec sections:** §9 D2 (best effort), §6.1 (definition of done), §10.2 (Order 5, after Wave A because it shares `engine/capture/`), §10.3 (lane gate); contract `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§10–14.
- **Worker profile:** **M**, **mechanical/moderate** (additive DTO keys, route rollup math, and MCP query/limit views; hot capture overhead budgets in `tests/engine/test_overhead_budgets.py` must not regress).
- **Dependencies:** Foundation commit **F**, **D1**, and Wave A (`P1`–`P3`) must be merged first.
- **Files this lane MAY touch:**
  - `src/sharpit/engine/capture/exchanges.py`, `src/sharpit/engine/capture/routes.py` (new), `src/sharpit/engine/capture/sqltrace.py`, `src/sharpit/engine/capture/logtail.py`, `src/sharpit/engine/capture/exceptions.py`, `src/sharpit/engine/capture/activity.py`
  - `src/sharpit/engine/tools.py` (or F's split capture MCP/CLI module)
  - `src/sharpit/fastapi/capture.py`, `src/sharpit/fastapi/adapter.py` (or F's split capture route module)
  - `tests/engine/test_exchanges.py`, `tests/engine/test_http_routes.py` (new), `tests/engine/test_sqltrace.py`, `tests/engine/test_logtail.py`, `tests/engine/test_exceptions.py`, `tests/engine/test_activity.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_capture_api.py`, `tests/test_conformance.py`
  - `.superpowers/sdd/0.4.0/lanes/D2/*`
- **Files this lane MUST NOT touch (spec §10.3 protected files & other lanes):**
  - `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json` (except lowering), `sonar-baseline.txt`, `tests/engine/test_import_boundary.py` rules, overhead budget constants (`tests/engine/test_overhead_budgets.py`), `uv.lock`, `pyproject.toml`, `guard.py` (D1), `pools.py`/`alembic.py`/`health.py`/`threads.py` (D3), `vulns/*`/`mcp.py`/`restapi/*` (D4).

## Definition of Done Coverage (Spec §6.1)

| §6.1 Item | Satisfying Task | §6.1 Item | Satisfying Task |
|---|---|---|---|
| 1. Golden parity & `field-map.md` | Task 1, Task 2, Task 3 | 6. Ported `# ported:` tests | Task 1 (Step 1), Task 2 (Step 1), Task 3 (Step 1) |
| 2. Guard chain on new routes | Task 1 (Step 3), Task 2 (Step 3), Task 3 (Step 3) | 7. Optional-dep & lowest-direct gates | Task 3 (Step 4) |
| 3. Masking before route/query filter | Task 1 (Step 1), Task 2 (Step 1) | 8. Capture/SQL overhead budgets pass | Task 1 (Step 4), Task 2 (Step 4) |
| 4. `no_side_effects` on GET/MCP | Task 1 (Step 1), Task 3 (Step 1) | 9. Quality gates (`ruff`, `pyright`, `pytest`) | Task 3 (Step 4) |
| 5. MCP & CLI parity (`get_http_routes`, `get_request_profile`) | Task 1 (Step 3), Task 2 (Step 3), Task 3 (Step 3) | 10. Live verification (`live-verify.log`) | Task 3 (Step 4) |

## Review Focus

1. **Route label masking when no template matches (`exchanges.py`, `routes.py`)**: `routeSource` must be `"FRAMEWORK_TEMPLATE"` when Starlette/FastAPI matched a route template, `"DECLARED_MAPPING"` when matched against known mappings, or `"MASKED_PATH"` with path segments masked before aggregation so raw tokens/IDs in 404 paths never leak into `GET /http-exchanges/routes`. Pinned by `test_summarize_groups_by_method_and_route_and_computes_percentiles` in **Task 1**.
2. **`durationMicros` integer math and SQL listener budget (`sqltrace.py:348-368`)**: `durationMicros` must be `duration_ns // 1_000` computed once on record without adding allocations to the SQL listener hot path, and `retention` (`CaptureRetentionDto`) must be emitted on `report()` (`None` when `available=False`). Pinned by `test_sql_trace_entry_includes_duration_micros_and_report_retention` in **Task 2**.
3. **`messageOmitted` in `METADATA_ONLY` mode (`logtail.py:120-140`)**: `messageOmitted` must be `True` iff `masker.expose_values == "METADATA_ONLY"` (where `message` is `"[hidden]"`) and `False` in `MASKED`/`FULL`. Pinned by `test_log_tail_line_sets_message_omitted_in_metadata_only_mode` in **Task 2**.
4. **Activity buffer-source filter warning & journal/resources Honest-Unavailable stubs (`activity.py`)**: Passing `route`, `run`, `requestId`, or `noRequest=true` when `source="buffers"` (or default without journal) must append `"Route, run, requestId and noRequest filters apply to journal-backed activity; the in-memory buffers returned an unfiltered snapshot."` to `warnings`. Pinned by `test_activity_buffer_source_emits_warning_on_journal_only_filters` in **Task 3**.

---

### Task 1: `http-exchanges` 2.2.0 Drift, `GET /http-exchanges/routes`, and `get_http_routes` Tool

**Files:**
- Modify: `src/sharpit/engine/capture/exchanges.py:26-30, 72-121, 165-191`
- Create: `src/sharpit/engine/capture/routes.py`
- Modify: `src/sharpit/fastapi/capture.py:165-230`, `src/sharpit/fastapi/adapter.py`, `src/sharpit/engine/tools.py`
- Test: `tests/engine/test_exchanges.py`, `tests/engine/test_http_routes.py`, `tests/fastapi/test_capture_api.py`

**Interfaces:**
- Produces in `src/sharpit/engine/capture/exchanges.py`: `exchange_row(..., route: str | None = None, route_source: str | None = None, request_id: str | None = None) -> dict[str, Any]`; `retention_dto(...) -> dict[str, Any]`; `HttpExchangeBuffer.report(*, limit: int | None = None, route: str | None = None) -> dict[str, Any]`.
- Produces in `src/sharpit/engine/capture/routes.py`: `DEFAULT_TOP_PER_CRITERION = 25`, `MAX_TOP_PER_CRITERION = 100`, `summarize_http_routes(report: dict[str, Any], *, limit_per_criterion: int = 25, route_filter: str | None = None) -> dict[str, Any]`.
- Produces route `GET {api}/http-exchanges/routes?limit=&route=` and MCP/CLI tool `get_http_routes` (schema `_LIMIT`, panel `http-exchanges`), plus `HTTP_EXCHANGES_DEFAULT_LIMIT = 25` on MCP `get_http_exchanges`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_exchanges.py` and `tests/engine/test_http_routes.py`**
  - `# ported: HttpRouteSummaryServiceTests.summarizeGroupsByMethodAndRouteAndComputesPercentiles` (`test_summarize_groups_by_method_and_route_and_computes_percentiles`: verifies `REQUESTS`, `TOTAL_DURATION`, `P95_DURATION`, `MAX_DURATION`, `ERROR_COUNT` union, `nearestRank(sorted, 0.95)`, `slowCount`, `status2xx..status5xx`, `sampleIds`, `routeFilter` substring match, and `window` timestamps).
  - `test_exchange_row_emits_route_route_source_request_id_and_retention`: asserts `DTO_KEYS` includes `route`, `routeSource`, `requestId`, and `report()["retention"]` has all 7 `CaptureRetentionDto` keys.
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_exchanges.py tests/engine/test_http_routes.py` and verify RED**
- [ ] **Step 3: Implement `exchanges.py` keys/retention, `routes.py` rollup, `GET /http-exchanges/routes`, and `get_http_routes`**
- [ ] **Step 4: Run tests plus `uv run pytest -q tests/engine/test_overhead_budgets.py` and commit** (`feat(capture): add http-exchanges 2.2.0 route labels, retention, and /routes rollup`).

---

### Task 2: `sql-trace`, `log-tail`, and `exceptions` 2.2.0 Drift

**Files:**
- Modify: `src/sharpit/engine/capture/sqltrace.py:28-39, 348-368, 478-500, 585-598`
- Modify: `src/sharpit/engine/capture/logtail.py:21, 120-140`
- Modify: `src/sharpit/engine/capture/exceptions.py:302-313`
- Modify: `src/sharpit/fastapi/adapter.py`, `src/sharpit/engine/tools.py`
- Test: `tests/engine/test_sqltrace.py`, `tests/engine/test_logtail.py`, `tests/engine/test_exceptions.py`, `tests/engine/test_tools.py`

**Interfaces:**
- Produces: `durationMicros` and `retention` in `sqltrace.py`; `messageOmitted` in `logtail.py`; `"caughtInCode": None` in `ExceptionStore.report()` and `GET {api}/exceptions/caught` returning `CaughtExceptionsReport` (`available: False`, `unavailableReason: "Caught exceptions are recorded by the sharpit agent's caught-exceptions sensor."`, `limitations: []`, `settling: 0`, `occurrences: 0`, `findings: 0`, `rows: []`); `_QUERY_LIMIT` schema on MCP `get_sql_traces` (`SQL_TRACES_DEFAULT_LIMIT = 20`) and `get_log_tail` (`LOG_TAIL_DEFAULT_LIMIT = 50`).

- [ ] **Step 1: Write failing tests in `tests/engine/test_sqltrace.py`, `test_logtail.py`, `test_exceptions.py`, and `test_tools.py`**
  - `test_sql_trace_entry_includes_duration_micros_and_report_retention` (`# ported: SqlTraceStoreTests.recordsDurationMicrosAndRetention`)
  - `test_log_tail_line_sets_message_omitted_in_metadata_only_mode` (`# ported: LogTailStoreTests.setsMessageOmittedWhenMetadataOnly`)
  - `test_exceptions_report_includes_caught_in_code_null_and_caught_endpoint` (`# ported: ExceptionsControllerTests.caughtEndpointReportsUnavailableWithoutSensor`)
  - `test_mcp_sql_traces_and_log_tail_accept_query_and_limit_with_page_metadata` (`# ported: McpAgentViewsTests.sqlTracesAndLogTailFilterAndPage`)
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_sqltrace.py tests/engine/test_logtail.py tests/engine/test_exceptions.py tests/engine/test_tools.py` and verify RED**
- [ ] **Step 3: Implement DTO fields, `GET {api}/exceptions/caught`, and MCP `sqlTraces`/`logTail` query-limit views**
- [ ] **Step 4: Run tests plus `uv run pytest -q tests/engine/test_overhead_budgets.py` and commit** (`feat(capture): align sql-trace, log-tail, and exceptions with BootUI 2.2.0`).

---

### Task 3: `activity` 2.2.0 Profile Keys, `/activity/journal`, `/activity/resources`, and `get_request_profile` Tool

**Files:**
- Modify: `src/sharpit/engine/capture/activity.py:31-34, 138-140, 274-314`
- Modify: `src/sharpit/fastapi/adapter.py`, `src/sharpit/engine/tools.py`
- Test: `tests/engine/test_activity.py`, `tests/fastapi/test_capture_api.py`, `tests/test_conformance.py`

**Interfaces:**
- Produces in `src/sharpit/engine/capture/activity.py`: `RequestProfileDto` keys `restCalls: []`, `cacheAccesses: []`, `sections: []`, `correlationTiers: []`, `approximate: bool`; `journal_status_dto() -> dict[str, Any]`; `journal_clear_dto() -> dict[str, Any]`; `resources_dto() -> dict[str, Any]`.
- Produces routes `GET {api}/activity/journal`, `POST {api}/activity/journal/clear` (read-only gated), `GET {api}/activity/resources`, and MCP/CLI tool `get_request_profile` (`_ID`, panel `activity`) plus `_QUERY_LIMIT` (`LIVE_ACTIVITY_DEFAULT_LIMIT = 25`) on `get_live_activity`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_activity.py` and `tests/fastapi/test_capture_api.py`**
  - `test_request_profile_emits_2_2_0_keys_and_get_request_profile_tool` (`# ported: LiveActivityServiceTests.requestProfileIncludes220Collections`)
  - `test_activity_buffer_source_emits_warning_on_journal_only_filters` (`# ported: LiveActivityControllerTests.warnsWhenJournalFiltersUsedAgainstBuffers`)
  - `test_activity_journal_and_resources_endpoints_and_read_only_clear`
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_activity.py tests/fastapi/test_capture_api.py` and verify RED**
- [ ] **Step 3: Implement `activity.py` 2.2.0 profile fields, journal/resources routes, `get_request_profile`, and `get_live_activity` filter**
- [ ] **Step 4: Run full verification gates (`ruff`, `pyright`, `pytest`, `lowest-direct.log`, `no-sqlalchemy.log`, `live-verify.log`) and commit** (`feat(activity): add 2.2.0 profile keys, journal/resources endpoints, and get_request_profile tool`).

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3)

`.superpowers/sdd/0.4.0/lanes/D2/` MUST contain:
- [ ] `field-map.md` — Every BootUI 2.2.0 key for `activity`, `http-exchanges` (+ `/routes`), `exceptions` (+ `/caught`), `sql-trace`, and `log-tail` mapped to Python source or `nullable.json`.
- [ ] `findings.md` — `finding → test → red` table with all rows `fixed` or `parked`.
- [ ] `checklist.md` — Spec §6.1 items 1–10 with `lowest-direct.log`, `no-sqlalchemy.log`, and `live-verify.log` naming the head SHA.
- [ ] `handoff.md` — Last green command, next step, open findings.
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` naming head SHA, ending with `VERDICT: APPROVE`.
