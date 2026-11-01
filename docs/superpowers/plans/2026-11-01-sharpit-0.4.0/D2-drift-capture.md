# Lane D2: 2.2.0 Capture Panels Drift (`activity`, `http-exchanges`, `exceptions`, `sql-trace`, `log-tail`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `D2`
- **Evidence folder:** `.superpowers/sdd/0.4.0/lanes/D2/`
- **Goal:** Upgrade the five capture panels (`activity`, `http-exchanges`, `exceptions`, `sql-trace`, `log-tail`) and their MCP/CLI tools to the BootUI 2.2.0 contract (`GET /http-exchanges/routes`, `GET /exceptions/caught`, `GET /activity/journal`, `GET /activity/resources`, `retention` metadata, `durationMicros`, `messageOmitted`, and `get_http_routes` / `get_request_profile` tools).
- **Spec sections:** §9 D2 (best effort 11), §6.1 (definition of done), §10.2, §10.3 (lane gate); contract `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§10–14.
- **Worker profile:** **M**, **mechanical/moderate** (additive DTO keys, route rollup math, and MCP query/limit views; hot capture overhead budgets in `tests/fastapi/test_capture_overhead.py` and `tests/fastapi/test_sql_trace_overhead.py` must not regress; default worker in `PLAN.md`: `agy / codex`).
- **Depends on:** `D1, every A-* merged or parked, B-security-logs if it runs (both edit fastapi/capture.py)`. **Ordering rule:** `B-security-logs` runs before `D2` if both run because both edit `src/sharpit/fastapi/capture.py`.
- **Foundation interfaces consumed (`F-foundation.md` §"Foundation consumer interface table"):**
  - `sharpit.fastapi.routes.<id>` (`activity`, `http_exchanges`, `exceptions`, `sql_trace`, `log_tail`) and `sharpit.fastapi.adapter`
  - `sharpit.engine.capture.exchanges.HttpExchangeBuffer.report` (`(self, q, method, status_class, offset, limit) -> dict[str, Any]`)
  - `sharpit.engine.tool_stubs.<id>` and `sharpit.engine.tools` (`_build_registry`, `execute_tool`)
  - `tests.golden.assert_parity` (`def assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` + `tests/fixtures/bootui/2.2.0/ids.json`)
  - `tests/safety/` and `tests/masking/` packages (`tests/safety/test_d2_safety.py`, `tests/masking/test_d2_masking.py`)
  - `scripts/dev/lane_gate.py` (`python scripts/dev/lane_gate.py D2`)
- **Files this lane MAY touch:**
  - `src/sharpit/engine/capture/exchanges.py`, `src/sharpit/engine/capture/routes.py` (new), `src/sharpit/engine/capture/sqltrace.py`, `src/sharpit/engine/capture/logtail.py`, `src/sharpit/engine/capture/exceptions.py`, `src/sharpit/engine/capture/activity.py`
  - `src/sharpit/engine/tools.py` (and `src/sharpit/engine/tool_stubs/{activity,http_exchanges,sql_trace,log_tail,exceptions}.py` if split by `F`)
  - `src/sharpit/fastapi/capture.py`, `src/sharpit/fastapi/adapter.py`, `src/sharpit/fastapi/routes/{activity,http_exchanges,exceptions,sql_trace,log_tail}.py`
  - `tests/engine/capture/test_exchanges.py`, `tests/engine/capture/test_http_routes.py` (new), `tests/engine/capture/test_sqltrace.py`, `tests/engine/capture/test_logtail.py`, `tests/engine/capture/test_exceptions.py`, `tests/engine/capture/test_activity.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_http_exchanges_api.py`, `tests/fastapi/test_activity_api.py`, `tests/fastapi/test_exceptions_api.py`, `tests/fastapi/test_sql_trace_api.py`, `tests/fastapi/test_log_tail_api.py`, `tests/safety/test_d2_safety.py` (new), `tests/masking/test_d2_masking.py` (new)
  - `tests/fixtures/bootui/2.2.0/{activity,http-exchanges,exceptions,sql-trace,log-tail}/nullable.json` (O2: panel lanes own `nullable.json`)
  - `.superpowers/sdd/0.4.0/lanes/D2/{handoff.md,findings.md,field-map.md,checklist.md,docs.md}` (O3: any user-facing text goes in `docs.md`)
- **Files this lane MUST NOT touch (spec §10.3, conventions C2/C5, ownership rules O1–O4):**
  - `src/sharpit/engine/sqla.py` (O1: owned by `A-postgresql`; `F` creates `add_connection_listener`).
  - `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or `<name>.captured.json`), `tests/fixtures/bootui/2.2.0/meta.json` (O2: owned by `G0a`), and `tests/fixtures/bootui/2.2.0/<sharpit-id>/provisional.json` (O2: written by a different worker than the lane).
  - `README.md`, `skills/sharpit/SKILL.md`, `examples/fastapi_sqla/`, `tests/test_example_app.py` (O3: write user-facing docs only to `.superpowers/sdd/0.4.0/lanes/D2/docs.md`).
  - `src/sharpit/engine/panels04/*`, `ui/src/lib/panels04/*`, `src/sharpit/engine/panels.py` (`PANELS`), and `ui/src/lib/nav.ts` (O4).
  - `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json` (unless every touched value strictly decreases or an entry is removed), `sonar-baseline.txt`, `tests/engine/test_import_boundary.py` rules, overhead budget constants in `tests/fastapi/test_capture_overhead.py` and `tests/fastapi/test_sql_trace_overhead.py`, `uv.lock`, `pyproject.toml`, `guard.py` (`D1`), `pools.py`/`alembic.py`/`health.py`/`threads.py` (`D3`), `vulns/*`/`mcp.py`/`restapi/*` (`D4`).
  - `tests/test_safety_matrix.py` and `tests/test_masking_corpus.py` (C5: add D2 rows only in `tests/safety/test_d2_safety.py` and `tests/masking/test_d2_masking.py`).
  - `.superpowers/sdd/0.4.0/lanes/*/review.md` and `.superpowers/sdd/0.4.0/lanes/*/gate/*` or `live-verify.md` (C2: written only by the coordinator/reviewer in the integration worktree; `lane_gate.py` refuses lane diffs touching them).

## Definition of Done Coverage (Spec §6.1 — C8 Order)

| # | Spec §6.1 Item (in spec order) | Satisfying Task |
|---|---|---|
| 1 | **Golden parity:** `tests/golden.py::assert_parity` against `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or `<name>.captured.json`, else `provisional.json` per O2) + `nullable.json` (owned by D2 per O2), and `field-map.md` | Task 1 (Step 3), Task 2 (Step 3), Task 3 (Step 3) |
| 2 | **Ported tests:** each ported behaviour test cites `# ported: <BootUI class>.<method>` | Task 1 (Step 1), Task 2 (Step 1), Task 3 (Step 1) |
| 3 | **Safety & masking:** `no_side_effects` on every GET; panel in `PANELS` with `actionCapable` and `SHARPIT_PANELS_<ID>_ENABLED/_READ_ONLY`; guard chain on `/http-exchanges/routes`, `/exceptions/caught`, `/activity/journal`, `/activity/resources`; `tests/safety/test_d2_safety.py` & `tests/masking/test_d2_masking.py` | Task 1 (Steps 1, 3), Task 2 (Steps 1, 3), Task 3 (Steps 1, 3) |
| 4 | **Gatekeeper / import boundary:** optional imports via gatekeepers only (§6.3); `tests/engine/test_import_boundary.py` green | Task 3 (Step 4) |
| 5 | **Overhead budget:** hot-path overhead budget tests (`tests/fastapi/test_capture_overhead.py` and `tests/fastapi/test_sql_trace_overhead.py`) untouched and passing | Task 1 (Step 4), Task 2 (Step 4), Task 3 (Step 4) |
| 6 | **MCP read-only:** MCP exposes read tools only (`get_http_routes`, `get_request_profile`, `get_http_exchanges`, `get_sql_traces`, `get_log_tail`, `get_live_activity`); clear actions are POST/CLI-only | Task 1 (Step 3), Task 2 (Step 3), Task 3 (Step 3) |
| 7 | **Svelte 5 view:** `N/A — 2.2.0 capture DTO/route/MCP drift lane; existing capture views remain compatible` | N/A |
| 8 | **Four gates + lowest-direct + no-SQLAlchemy:** `ruff check`, `ruff format --check`, `pyright`, `pytest` green in lane worktree; coordinator records `gate/*.log` in integration worktree | Task 3 (Step 4) |
| 9 | **Live check:** coordinator records `live-verify.md` in integration worktree against `examples/fastapi_sqla` | Task 3 (Step 4) |
| 10 | **Handoff:** `.superpowers/sdd/0.4.0/lanes/D2/handoff.md` current (§10.3) | Task 3 (Step 4) |

## Review Focus

1. **Route label masking when no template matches (`src/sharpit/engine/capture/exchanges.py:72-121, 165-191`, `src/sharpit/engine/capture/routes.py`)**: `routeSource` must be `"FRAMEWORK_TEMPLATE"` when Starlette/FastAPI matched a route template, `"DECLARED_MAPPING"` when matched against known mappings, or `"MASKED_PATH"` with path segments masked before aggregation so raw tokens/IDs in 404 paths never leak into `GET /http-exchanges/routes`. `HttpExchangeBuffer.report` (`src/sharpit/engine/capture/exchanges.py:165-167`) keeps its five parameters `(self, q: str | None, method: str | None, status_class: str | None, offset: int | None, limit: int | None, route: str | None = None)` unchanged with `route` appended, and `exchange_row` (`exchanges.py:72-121`) / `DTO_KEYS` (`exchanges.py:26-29`) emit `route`, `routeSource`, and `requestId`. Pinned by `test_summarize_groups_by_method_and_route_and_computes_percentiles` in **Task 1**.
2. **`durationMicros` integer math and SQL listener budget (`src/sharpit/engine/capture/sqltrace.py:28-39, 348-368, 443-519, 537-598`)**: `durationMicros` must be `duration_ns // 1_000` computed once in `SqlTraceRecorder.record` (`sqltrace.py:443-519`) and emitted via `ENTRY_KEYS` (`:36-39`) / `entry_dto` (`:366-368`) without regressing `tests/fastapi/test_sql_trace_overhead.py`, and `retention` (`CaptureRetentionDto`) must be emitted in `REPORT_KEYS` (`:28-31`), `SqlTraceRecorder.report` (`:537-598`), and `unavailable_report` (`:348-363`, where `"retention": None`). Pinned by `test_sql_trace_entry_includes_duration_micros_and_report_retention` in **Task 2**.
3. **`messageOmitted` in `METADATA_ONLY` mode (`src/sharpit/engine/capture/logtail.py:21, 120-140`)**: `SharpitLogHandler.line` (`logtail.py:120-140`) calls `masked = self.masker.mask_text(message)` (`:130`) and builds the row matching `LINE_KEYS` (`:21`); in `METADATA_ONLY` mode `masked` is `None`, so `message` is `None` and `messageOmitted` is `True` (`masked is None`), whereas in `MASKED`/`FULL` modes `messageOmitted` is `False`. Pinned by `test_log_tail_line_sets_message_omitted_in_metadata_only_mode` in **Task 2**.
4. **Activity buffer-source filter warning & journal/resources Honest-Unavailable stubs (`src/sharpit/engine/capture/activity.py:274-314`)**: Passing `route`, `run`, `requestId`, or `noRequest=true` when `source="buffers"` (or default without journal) must append the verbatim BootUI 2.2.0 string `"The route, run, request id, and no-request filters apply to the feed rendered from the runtime journal (source=journal); this feed comes from the panel buffers."` to `warnings` (`docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §10.3). Pinned by `test_activity_buffer_source_emits_warning_on_journal_only_filters` in **Task 3**.

---

### Task 1: `http-exchanges` 2.2.0 Drift, `GET /http-exchanges/routes`, and `get_http_routes` Tool

**Files:**
- Modify: `src/sharpit/engine/capture/exchanges.py:26-30, 72-133, 165-191`
- Create: `src/sharpit/engine/capture/routes.py`
- Modify: `src/sharpit/fastapi/capture.py:165-230`, `src/sharpit/fastapi/adapter.py` (or `src/sharpit/fastapi/routes/http_exchanges.py`), `src/sharpit/engine/tools.py:282-295`
- Test: `tests/engine/capture/test_exchanges.py`, `tests/engine/capture/test_http_routes.py` (new), `tests/fastapi/test_http_exchanges_api.py`, `tests/fastapi/test_capture_overhead.py`, `tests/safety/test_d2_safety.py` (new), `tests/masking/test_d2_masking.py` (new)

**Interfaces:**
- Produces in `src/sharpit/engine/capture/exchanges.py`:
  - `DTO_KEYS` (`exchanges.py:26-29`) and `exchange_row(..., *, route: str | None = None, route_source: str | None = None, request_id: str | None = None) -> dict[str, Any]` (`exchanges.py:72-121`) emitting `"route"`, `"routeSource"`, and `"requestId"`.
  - `unavailable_report(reason: str) -> dict[str, Any]` (`exchanges.py:124-133`, adding `"retention": None`) and `HttpExchangeBuffer.report(self, q: str | None, method: str | None, status_class: str | None, offset: int | None, limit: int | None, route: str | None = None) -> dict[str, Any]` (`exchanges.py:165-191`, 5 existing parameters unchanged, `route: str | None = None` appended; top-level report adds `"retention": dict[str, Any]`).
- Produces in `src/sharpit/engine/capture/routes.py`: `DEFAULT_TOP_PER_CRITERION: Final[int] = 25`, `MAX_TOP_PER_CRITERION: Final[int] = 100`, `summarize_http_routes(exchanges: HttpExchangeBuffer, *, limit: int = 25, route: str | None = None) -> dict[str, Any]`.
- Produces route `GET {api}/http-exchanges/routes?limit=&route=` and MCP/CLI tool `get_http_routes` (schema `_LIMIT`, panel `http-exchanges`), plus `HTTP_EXCHANGES_DEFAULT_LIMIT: Final[int] = 25` on MCP `get_http_exchanges`.

- [ ] **Step 1: Add stub `src/sharpit/engine/capture/routes.py`, then write failing tests in `tests/engine/capture/test_exchanges.py`, `tests/engine/capture/test_http_routes.py`, `tests/fastapi/test_http_exchanges_api.py`, `tests/safety/test_d2_safety.py`, and `tests/masking/test_d2_masking.py` (C4: RED is an assertion failure, never `ImportError`)**
  - `# ported: HttpRouteSummaryServiceTests.summarizeGroupsByMethodAndRouteAndComputesPercentiles` (`test_summarize_groups_by_method_and_route_and_computes_percentiles`: verifies `REQUESTS`, `TOTAL_DURATION`, `P95_DURATION`, `MAX_DURATION`, `ERROR_COUNT` union, `nearestRank(sorted, 0.95)`, `slowCount`, `status2xx..status5xx`, `sampleIds`, `routeFilter` substring match, and `window` timestamps).
  - `test_exchange_row_emits_route_route_source_request_id_and_retention`: asserts `exchange_row(...)` includes `route`, `routeSource`, `requestId` matching `DTO_KEYS`, `HttpExchangeBuffer.report(..., route=...)` filters by exact `route` before paging, and `report()["retention"]` has all 7 `CaptureRetentionDto` keys (`assert_parity("http-exchanges", "default", payload)`).
  - Safety/masking rows in `tests/safety/test_d2_safety.py` (`no_side_effects` on `GET /sharpit/api/http-exchanges/routes`) and `tests/masking/test_d2_masking.py` (secret path tokens masked in `MASKED_PATH` route labels).
- [ ] **Step 2: Run `uv run pytest -q tests/engine/capture/test_exchanges.py tests/engine/capture/test_http_routes.py tests/fastapi/test_http_exchanges_api.py tests/safety/test_d2_safety.py tests/masking/test_d2_masking.py` and verify RED**
- [ ] **Step 3: Implement `exchanges.py` keys/retention, `routes.py` rollup, `GET /http-exchanges/routes`, and `get_http_routes`**
- [ ] **Step 4: Run tests plus `uv run pytest -q tests/fastapi/test_capture_overhead.py` and commit** (`feat(capture): add http-exchanges 2.2.0 route labels, retention, and /routes rollup`).

---

### Task 2: `sql-trace`, `log-tail`, and `exceptions` 2.2.0 Drift

**Files:**
- Modify: `src/sharpit/engine/capture/sqltrace.py:28-39, 348-368, 443-519, 537-598`
- Modify: `src/sharpit/engine/capture/logtail.py:21, 120-140`
- Modify: `src/sharpit/engine/capture/exceptions.py:302-313`
- Modify: `src/sharpit/fastapi/adapter.py` (or `src/sharpit/fastapi/routes/{exceptions,sql_trace,log_tail}.py`), `src/sharpit/engine/tools.py`
- Test: `tests/engine/capture/test_sqltrace.py`, `tests/engine/capture/test_logtail.py`, `tests/engine/capture/test_exceptions.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_exceptions_api.py`, `tests/fastapi/test_sql_trace_api.py`, `tests/fastapi/test_log_tail_api.py`, `tests/fastapi/test_sql_trace_overhead.py`

**Interfaces:**
- Produces: `durationMicros` (`int(duration_ns // 1_000)`) in `ENTRY_KEYS` (`sqltrace.py:36-39`), `entry_dto(row)` (`sqltrace.py:366-368`), and `SqlTraceRecorder.record(...)` (`sqltrace.py:443-519`), plus `retention` (`CaptureRetentionDto` or `None` when `available=False`) in `REPORT_KEYS` (`sqltrace.py:28-31`), `unavailable_report(reason)` (`sqltrace.py:348-363`), and `SqlTraceRecorder.report(data_sources)` (`sqltrace.py:537-598`); `messageOmitted: bool` (`masked is None`) in `LINE_KEYS` (`logtail.py:21`) and `SharpitLogHandler.line(self, record)` (`logtail.py:120-140`); `"caughtInCode": None` in `ExceptionStore.report()` (`exceptions.py:302-313`) and `GET {api}/exceptions/caught` returning `CaughtExceptionsReport` (`available: False`, `unavailableReason: "Caught exceptions are recorded by the sharpit agent's caught-exceptions sensor."`, `limitations: []`, `settling: 0`, `occurrences: 0`, `findings: 0`, `rows: []`); `_QUERY_LIMIT` schema on MCP `get_sql_traces` (`SQL_TRACES_DEFAULT_LIMIT: Final[int] = 20`) and `get_log_tail` (`LOG_TAIL_DEFAULT_LIMIT: Final[int] = 50`).

- [ ] **Step 1: Write failing tests in `tests/engine/capture/test_sqltrace.py`, `tests/engine/capture/test_logtail.py`, `tests/engine/capture/test_exceptions.py`, `tests/fastapi/test_exceptions_api.py`, and `tests/engine/test_tools.py`**
  - `test_sql_trace_entry_includes_duration_micros_and_report_retention` (`# ported: SqlTraceStoreTests.recordsDurationMicrosAndRetention`)
  - `test_log_tail_line_sets_message_omitted_in_metadata_only_mode` (`# ported: LogTailStoreTests.setsMessageOmittedWhenMetadataOnly`: asserts `line["message"] is None` and `line["messageOmitted"] is True` in `METADATA_ONLY`, `False` in `MASKED`/`FULL`)
  - `test_exceptions_report_includes_caught_in_code_null_and_caught_endpoint` (`# ported: ExceptionsControllerTests.caughtEndpointReportsUnavailableWithoutSensor`)
  - `test_mcp_sql_traces_and_log_tail_accept_query_and_limit_with_page_metadata` (`# ported: McpAgentViewsTests.sqlTracesAndLogTailFilterAndPage`)
- [ ] **Step 2: Run `uv run pytest -q tests/engine/capture/test_sqltrace.py tests/engine/capture/test_logtail.py tests/engine/capture/test_exceptions.py tests/fastapi/test_exceptions_api.py tests/engine/test_tools.py` and verify RED**
- [ ] **Step 3: Implement DTO fields, `GET {api}/exceptions/caught`, and MCP `sqlTraces`/`logTail` query-limit views**
- [ ] **Step 4: Run tests plus `uv run pytest -q tests/fastapi/test_sql_trace_overhead.py` and commit** (`feat(capture): align sql-trace, log-tail, and exceptions with BootUI 2.2.0`).

---

### Task 3: `activity` 2.2.0 Profile Keys, `/activity/journal`, `/activity/resources`, and `get_request_profile` Tool

**Files:**
- Modify: `src/sharpit/engine/capture/activity.py:31-34, 138-140, 274-314`
- Modify: `src/sharpit/fastapi/adapter.py` (or `src/sharpit/fastapi/routes/activity.py`), `src/sharpit/engine/tools.py`
- Test: `tests/engine/capture/test_activity.py`, `tests/fastapi/test_activity_api.py`, `tests/safety/test_d2_safety.py`

**Interfaces:**
- Produces in `src/sharpit/engine/capture/activity.py`: `RequestProfileDto` keys `restCalls: []`, `cacheAccesses: []`, `sections: []`, `correlationTiers: []`, `approximate: bool`; `journal_status_dto() -> dict[str, Any]`; `journal_clear_dto() -> dict[str, Any]`; `resources_dto() -> dict[str, Any]`.
- Produces routes `GET {api}/activity/journal`, `POST {api}/activity/journal/clear` (read-only gated), `GET {api}/activity/resources`, and MCP/CLI tool `get_request_profile` (`_ID`, panel `activity`) plus `_QUERY_LIMIT` (`LIVE_ACTIVITY_DEFAULT_LIMIT: Final[int] = 25`) on `get_live_activity`.

- [ ] **Step 1: Write failing tests in `tests/engine/capture/test_activity.py` and `tests/fastapi/test_activity_api.py`**
  - `test_request_profile_emits_2_2_0_keys_and_get_request_profile_tool` (`# ported: LiveActivityServiceTests.requestProfileIncludes220Collections`)
  - `test_activity_buffer_source_emits_warning_on_journal_only_filters` (`# ported: LiveActivityControllerTests.warnsWhenJournalFiltersUsedAgainstBuffers`: asserts exact warning `"The route, run, request id, and no-request filters apply to the feed rendered from the runtime journal (source=journal); this feed comes from the panel buffers."`)
  - `test_activity_journal_and_resources_endpoints_and_read_only_clear`
- [ ] **Step 2: Run `uv run pytest -q tests/engine/capture/test_activity.py tests/fastapi/test_activity_api.py` and verify RED**
- [ ] **Step 3: Implement `activity.py` 2.2.0 profile fields, journal/resources routes, `get_request_profile`, and `get_live_activity` filter**
- [ ] **Step 4: Run verification gates in the lane worktree (`ruff check`, `ruff format --check`, `pyright`, `pytest`, including `tests/fastapi/test_capture_overhead.py` and `tests/fastapi/test_sql_trace_overhead.py`), update implementer evidence in `.superpowers/sdd/0.4.0/lanes/D2/`, and commit** (`feat(activity): add 2.2.0 profile keys, journal/resources endpoints, and get_request_profile tool`).

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3 & C2)

**Written by the implementer in the lane worktree (`.superpowers/sdd/0.4.0/lanes/D2/`):**
- [ ] `field-map.md` — Every BootUI 2.2.0 key for `activity`, `http-exchanges` (+ `/routes`), `exceptions` (+ `/caught`), `sql-trace`, and `log-tail` mapped to Python source or `tests/fixtures/bootui/2.2.0/<sharpit-id>/nullable.json`.
- [ ] `findings.md` — `finding → test → red` table with all rows `fixed` or `parked`.
- [ ] `checklist.md` — Spec §6.1's 10 items in spec §6.1's exact order (1 golden parity … 10 handoff), each with an evidence path or `N/A` + reason.
- [ ] `handoff.md` — Last green command, next step (`ready-for-review`), open findings (`none`).

**Written by the coordinator/reviewer in the integration worktree ONLY (never touched by the lane's diff; `lane_gate.py` refuses it):**
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` naming head SHA, ending with `VERDICT: APPROVE`.
- [ ] `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log` and `live-verify.md`.
