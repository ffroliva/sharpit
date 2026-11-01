# Lane A-traces: the `traces` panel (OpenTelemetry spans, best effort)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development, one task at a time,
> `/sharpit:check` before every commit.

| | |
|---|---|
| **Lane id** | `A-traces` (worktree `...\0.4.0-A-traces`, branch `lane/0.4.0-A-traces`); best effort, parks per §10.6 |
| **Goal** | BootUI's `TracesReport` / `TraceDetailDto` from one module-level OTel span processor attached to the app's SDK `TracerProvider`, never installing a provider. |
| **Spec** | §2 (best effort), §4, §6.1, §6.3 (`engine/otel.py` gatekeeper), §7 row `traces`, §11, §15 (round 1 "Traces cannot remove a processor"; round 3 "attach during requests; pile-up") |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §7; BootUI `TracesService.java` (limit clamp 1..500, `MAX_SUMMARY_SERVICES = 20`), `TraceSummaryDto`, `SpanDto`, `SpanAttributeDto(key,type,value)`, `SpanEventDto(name,timeOffsetNanos,attributes)` |
| **Worker** | M, judgement on lifecycle → Opus or codex |
| **Depends on** | F (span-processor slot in the capture wiring, `engine/otel.py` row in `GATEKEEPERS`, OTel SDK in the test extra), D1 |
| **May touch** | `src/sharpit/engine/otel.py` (new gatekeeper), `src/sharpit/engine/capture/traces.py` (new), F's span slot in `src/sharpit/fastapi/capture.py`, `src/sharpit/fastapi/routes/traces.py` (F stub), the panel's pre-registered rows, F's MCP stubs, `ui/src/views/Traces.svelte` (+ test), `tests/engine/capture/test_traces.py`, `tests/fastapi/test_traces_api.py`, `tests/fastapi/test_traces_overhead.py`, goldens, lane folder |
| **Must NOT touch** | §10.3 protected files; other lanes' modules; any OTel import outside `engine/otel.py` |

**Architecture:** `engine/otel.py` reads `sys.modules` (never imports `opentelemetry` unless already imported, like
`sqla.sqlalchemy_module`, `sqla.py:41`) and exposes the processor: one module-level `SharpitSpanProcessor` instance
whose `on_end` forwards `ReadableSpan`s to the armed contexts' `SpanBuffer` (`engine/capture/traces.py`, bounded by
traces, masked at read). `CaptureWiring.attach_at_install` and `on_startup` (`fastapi/capture.py:172,203`) call
`otel.attach(ctx)`; never a request or GET. `detach` disarms; a later attach re-arms the same processor (the SDK cannot
remove one).

## Global Constraints

- Never installs or replaces a `TracerProvider`; only `trace.get_tracer_provider()` that is an SDK provider
  (`hasattr(provider, "add_span_processor")`). A provider set after startup is seen at the next install/restart
  (documented; `unavailableReason` says so).
- At most one sharpit processor per provider, ever (identity check before `add_span_processor`).
- Attach only at install and lifespan startup; GET, MCP, and request paths never attach.
- `on_end` is hot: no masking, no formatting, no lock beyond a deque append; overhead budget test.
- Span attributes masked at read (`db.statement` through `normalize` + `mask_text`; HTTP header attributes through
  the header masker; `url.full`/`http.url` authority dropped, matrix params masked as BootUI).
- Nanosecond timestamps (contract), not epoch ms (logged §11). `# ported:` citations. Red is an assertion.

## Review Focus

1. **Install twice / uninstall then reinstall / two apps on one provider.** Expect exactly one processor in
   `provider._active_span_processor._span_processors` and spans routed to the armed contexts only. Pinned in Task 2:
   `test_one_processor_per_provider_across_reinstall`.
2. **No SDK, or the no-op default provider.** Expect `enabled:false` with the reason, no import of the SDK. Pinned in
   Task 1: `test_no_sdk_is_unavailable`, `test_proxy_provider_is_unavailable`.
3. **sharpit's own requests** (`/sharpit/...` server spans). Expect hidden from list and detail. Pinned in Task 2:
   `test_list_and_detail_hide_sharpit_self_traces` (`# ported: TracesServiceTests.listAndDetailHideBootUiSelfTraces`).
4. **Secrets in attributes** (`db.statement` literal, `http.request.header.authorization`, `url.full` with userinfo).
   Pinned in Task 2: `test_span_reads_mask_nested_values` (`# ported: TracesServiceTests.spanReadsMaskNestedValuesWithoutChangingStoredEvidence`)
   and a masking corpus row.
5. **Limit edge values** `limit=0`, `-5`, `10000`, `abc`. Expect clamp 1..500; non-integer → 400 via
   `engine/paging.py::parse_int_param`. Pinned in Task 3: `test_limit_clamped`.

---

### Task 1: Gatekeeper `engine/otel.py`

**Interfaces:** `otel_sdk() -> Any | None`; `unavailable_reason() -> str | None` (`"OpenTelemetry SDK is not imported
by this application"`, `"The global tracer provider is not an SDK TracerProvider"`); `attach(ctx) -> bool`;
`disarm(ctx) -> None`; `PROCESSOR: SharpitSpanProcessor` (module-level).

- [ ] **Step 1:** Tests `test_no_sdk_is_unavailable`, `test_proxy_provider_is_unavailable`, `test_attach_adds_once`,
  `test_disarm_stops_delivery`, `test_on_end_raising_is_swallowed`. **Step 2:** FAIL. **Step 3:** implement.
- [ ] **Step 4:** PASS; boundary test green with F's `opentelemetry` row. Commit `feat: OpenTelemetry gatekeeper and span processor`.

### Task 2: `SpanBuffer` and the trace DTOs

**Files:** `src/sharpit/engine/capture/traces.py`; Test `tests/engine/capture/test_traces.py`.

**Interfaces:** `SpanBuffer(masker, *, capacity: int = 1000)` with `add(span: Any)`, `list(limit: int) -> dict`
(`TracesReport{enabled,retained,capacity,traces}`), `detail(trace_id: str) -> dict | None`, `clear()`. Summary keys
`traceId, rootSpanName, httpPath, services, startEpochNanos, endEpochNanos, durationNanos, spanCount, hasError, hasAi`;
`hasAi` = any span with a `gen_ai.*` attribute.

- [ ] **Step 1:** Ported tests from `TracesServiceTests`: `summaryExposesHttpPathFromRootServerSpan`,
  `summaryFallsBackToServerSpanWhenRootHasNoPath`, `summaryLeavesHttpPathNullWhenNoPathAttributeIsPresent`,
  `listAndDetailHideBootUiSelfTraces`, `summaryMasksMatrixParametersOfTheHttpPath`,
  `summaryNeverReturnsTheAuthorityOfAnAbsoluteUrl`, `detailAppliesTheLiveExposurePolicyOnEveryRead`,
  `spanReadsMaskNestedValuesWithoutChangingStoredEvidence`; plus `test_one_processor_per_provider_across_reinstall`.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: span buffer and trace DTOs`.

### Task 3: Wiring, routes, MCP, safety, budget

**Files:** F's span slot in `fastapi/capture.py`; `fastapi/routes/traces.py`; flag flip; Tests
`tests/fastapi/test_traces_api.py`, `tests/fastapi/test_traces_overhead.py`, safety-matrix and corpus rows.

**Interfaces:** `GET {api}/traces?limit=100`, `GET {api}/traces/{traceId}` (404 `{"error": "trace <id> not found"}`),
`DELETE {api}/traces` (204, read-only → 403). MCP `get_traces` (read, `limit`); `clear_traces` `action=True`.
`actionCapable=True`.

- [ ] **Step 1:** Tests `test_golden_parity`, `test_limit_clamped`, `test_unknown_trace_404`, `test_clear_204`,
  `test_get_no_side_effects` (also asserts `PROCESSOR` attach count unchanged by GET), `test_mcp_read_tool_only`,
  `test_attach_never_during_request`; budget `BUDGET_NS = 20_000` per `on_end` (paired, `tests/overhead.py`).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS + full gate. Commit `feat: traces panel routes and MCP read tool`.

### Task 4: Svelte view, live check, evidence

- [ ] **Step 1:** `ui/src/views/Traces.svelte` + vitest (list → detail waterfall; nanos rendered as ms; `enabled:false`
  shows the reason). `npm --prefix ui run check` PASS.
- [ ] **Step 2:** Live: `examples/fastapi_sqla` with an SDK provider set in the test harness app (no example change
  if it lacks OTel: use tiny-ledger-py, whose OTel goes to the reference compose's collector, §12.8). `live-verify.md`.
- [ ] **Step 3:** Commit `feat: traces view and lane evidence`.

## §6.1 → task

1 parity: 2–3 (+ field map in `field-map.md`) · 2 citations: 2 · 3 safety/masking (span attributes, headers): 2–3 ·
4 gatekeeper `engine/otel.py`: 1 · 5 budget: 3 · 6 MCP read-only: 3 · 7 Svelte: 4 · 8 gates: 3–4 · 9 live: 4 ·
10 handoff: every commit.

## Lane evidence checklist (`.superpowers/sdd/0.4.0/lanes/A-traces/`)

`handoff.md` · `field-map.md` · `checklist.md` · `findings.md` · `review.md` (`VERDICT: APPROVE`, reviewer ≠ implementer,
head SHA) · `gate/` (four gates, lowest-direct, no-SQLAlchemy logs, each naming the head SHA) · `live-verify.md`.
