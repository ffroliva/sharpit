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
| **Depends on** | F (PLAN.md). Consumes these rows of F's consumer interface table (`F-foundation.md`): `sharpit.fastapi.capture.CaptureWiring.span_processor`, `sharpit.fastapi.routes.<id>` (`routes/traces.py`), "implemented flag files" (`engine/panels04/<id>.py` + `ui/src/lib/panels04/<id>.ts`, O4, here `traces`), `sharpit.engine.tools04.<id>` (`engine/tools04/traces.py`, `TOOLS = ()` until this lane fills it, R3), `tests.golden.assert_parity` (O2), the `ui/src/views/Traces.svelte` placeholder; the `"opentelemetry": {"sharpit/engine/otel.py"}` row in `GATEKEEPERS` (`tests/engine/test_import_boundary.py:25`); F's `examples/fastapi_sqla` wiring (O3: an optional SDK provider behind the test extra). **The OTel SDK test extra is an F-rest piece** (F's minimum cut keeps only `psycopg[binary]`); `pyproject.toml`/`uv.lock` and the import-boundary rules are protected, so this lane starts only after F-rest (or F) has merged both; the coordinator checks before launch. `tests/safety/` + `tests/masking/` are F-rest too: if absent, the lane creates its own two test files. **Ordering (R0):** the May-touch lists overlap on `fastapi/capture.py` with B-security-logs and D2, so the chain is serial and this lane is first: `A-traces → B-security-logs → D2`; the coordinator starts the next only after this lane's merge |
| **May touch** | `src/sharpit/engine/otel.py` (new gatekeeper), `src/sharpit/engine/capture/traces.py` (new), the `CaptureWiring.span_processor` assignment in `src/sharpit/fastapi/capture.py` (F's slot only), `src/sharpit/fastapi/routes/traces.py` (F stub), `src/sharpit/engine/panels04/traces.py` and `ui/src/lib/panels04/traces.ts` (flag flip only, O4), `src/sharpit/engine/tools04/traces.py` (the `get_traces` tool replaces F's `TOOLS = ()`), `ui/src/views/Traces.svelte` (replace F's placeholder) + `.test.ts`, `tests/engine/test_otel.py`, `tests/engine/capture/test_traces.py`, `tests/fastapi/test_traces_api.py`, `tests/fastapi/test_traces_overhead.py`, `tests/safety/test_a_traces_safety.py`, `tests/masking/test_a_traces_masking.py`, `tests/fixtures/bootui/2.2.0/traces/nullable.json` (O2), the implementer files in the lane folder (C2) plus `docs.md` (O3) |
| **Must NOT touch** | §10.3 protected files (incl. the import-boundary rules and dependency lists); other lanes' modules; any OTel import outside `engine/otel.py`; `fastapi/capture.py` beyond F's span slot; `engine/tools.py` (R3); `PANELS`, `nav.ts`, `App.svelte`, `types.ts` (O4); `captured.json` / `provisional.json` (O2); `README.md`, `skills/sharpit/SKILL.md`, `examples/fastapi_sqla/`, `tests/test_example_app.py` (O3); `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (C5); any `review.md` or `gate/` path |

**Architecture:** `engine/otel.py` reads `sys.modules` (never imports `opentelemetry` unless already imported, like
`sqla.sqlalchemy_module`, `sqla.py:41`) and exposes the processor: one module-level `SharpitSpanProcessor` instance
whose `on_end` forwards `ReadableSpan`s to the armed contexts' `SpanBuffer` (`engine/capture/traces.py`, bounded by
traces, masked at read). `CaptureWiring.attach_at_install` and `on_startup` (`fastapi/capture.py:172,203`) call
`otel.attach(ctx)` through F's `CaptureWiring.span_processor` slot; never a request or GET. at attach it appends `lambda: otel.disarm(ctx)` to `ctx.capture.teardowns` (R17; no edit to `CaptureWiring.detach`, which runs
the teardowns); a later attach re-arms the same processor (the SDK cannot
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
- Nanosecond timestamps (contract), not epoch ms (logged §11). `# ported:` citations.
- Red is an assertion (R2): each task's red is a **red commit** (subject starts `test:`) with the failing tests plus the
  minimal stubs that make them import; a stub returns a wrong value, never raises `NotImplementedError`. Record its SHA
  per red test in `findings.md` and `handoff.md`; `lane_gate.py` replays each test at that SHA (needs `AssertionError`)
  and at the lane head (must pass). Every "FAIL" step below means this red commit.

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
   and a row in `tests/masking/test_a_traces_masking.py`.
5. **Limit edge values** `limit=0`, `-5`, `10000`, `abc`. Expect clamp 1..500; non-integer → 400 via
   `engine/paging.py::parse_int_param`. Pinned in Task 3: `test_limit_clamped`.

---

### Task 1: Gatekeeper `engine/otel.py`

**Files:** Create `src/sharpit/engine/otel.py`; Test `tests/engine/test_otel.py`.

**Interfaces:** `otel_sdk() -> Any | None`; `unavailable_reason() -> str | None` (`"OpenTelemetry SDK is not imported
by this application"`, `"The global tracer provider is not an SDK TracerProvider"`); `attach(ctx) -> bool`;
`disarm(ctx) -> None`; `PROCESSOR: SharpitSpanProcessor` (module-level).

- [ ] **Step 1:** Tests `test_no_sdk_is_unavailable`, `test_proxy_provider_is_unavailable`, `test_attach_adds_once`,
  `test_disarm_stops_delivery`, `test_on_end_raising_is_swallowed`. **Step 2:** FAIL. **Step 3:** implement.
- [ ] **Step 4:** PASS; `tests/engine/test_import_boundary.py` green with F's `opentelemetry` row (unchanged). Commit `feat: OpenTelemetry gatekeeper and span processor`.

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

**Files:** F's `CaptureWiring.span_processor` slot in `fastapi/capture.py`; `fastapi/routes/traces.py`;
`engine/panels04/traces.py` `IMPLEMENTED = True` (O4); Tests
`tests/fastapi/test_traces_api.py`, `tests/fastapi/test_traces_overhead.py`, `tests/safety/test_a_traces_safety.py`,
`tests/masking/test_a_traces_masking.py` (C5).

**Interfaces:** `GET {api}/traces?limit=100`, `GET {api}/traces/{traceId}` (404 `{"error": "trace <id> not found"}`),
`DELETE {api}/traces` (204, read-only → 403). `limit` parsed with `engine/paging.py:15::parse_int_param`. MCP `get_traces` (read, `limit`); `clear_traces` `action=True`.
`actionCapable=True`.

- [ ] **Step 1:** Tests `test_golden_parity` (`assert_parity("traces", "list", body)` and `("traces", "detail", …)`;
  per O2 a multi-endpoint panel: the loader reads G0a's `tests/fixtures/bootui/2.2.0/traces/{list,detail}.captured.json`,
  else another worker's `<name>.provisional.json` (result marked unverified); the lane writes only `nullable.json`), `test_limit_clamped`, `test_unknown_trace_404`, `test_clear_204`,
  `test_get_no_side_effects` (also asserts `PROCESSOR` attach count unchanged by GET), `test_mcp_read_tool_only`,
  `test_attach_never_during_request`; budget `BUDGET_NS = 20_000` per `on_end` (a new constant in the new file; paired
  with `tests/overhead.py::paired` and `check_budget`).
- [ ] **Step 2:** FAIL on assertions (F's unimplemented panel answers 404; never an `ImportError`, C4) → **Step 3:** implement → **Step 4:** PASS + full gate. Commit `feat: traces panel routes and MCP read tool`.

### Task 4: Svelte view, live check, evidence

- [ ] **Step 1:** Replace F's placeholder `ui/src/views/Traces.svelte`, set `implemented = true` in
  `ui/src/lib/panels04/traces.ts` (O4; `nav.ts` untouched); vitest (list → detail waterfall; nanos rendered as ms; `enabled:false`
  shows the reason). `npm --prefix ui run check` PASS.
- [ ] **Step 2:** Live: `examples/fastapi_sqla` with the optional SDK provider F wired behind the test extra (O3; no
  example change; else tiny-ledger-py, whose OTel goes to the reference compose's collector, §12.8). User-facing text
  goes to the lane folder's `docs.md` (O3). Record requests in
  `handoff.md` §Live check (`live-verify.md` is the coordinator's, C2); lowest-direct + no-SQLAlchemy as a local
  pre-check only.
- [ ] **Step 3:** Commit `feat: traces view and lane evidence`.

## §6.1 → task (spec order; `checklist.md` adds the evidence paths)

| Item | Task |
|---|---|
| 1 golden parity, `nullable.json`, field map | 2–3 (+ field map in `field-map.md`) |
| 2 `# ported:` citations | 2 |
| 3 safety + masking (span attributes, headers) | 2–3 |
| 4 gatekeeper `engine/otel.py` | 1 |
| 5 overhead budget | 3 |
| 6 MCP read-only | 3 |
| 7 Svelte view | 4 |
| 8 four gates + lowest-direct + no-SQLAlchemy | 3–4 (gated logs: coordinator) |
| 9 live check | 4 |
| 10 handoff current | every commit |

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/A-traces/`)

- **Implementer, in the lane worktree:** `handoff.md` (last green command, next step, open findings, live-check
  requests), `findings.md` (`finding → test → red output`, each row `fixed` + red-test name or `parked` + reason),
  `field-map.md` (every `TraceSummaryDto`/`SpanDto` key → its OTel source or `null` + reason), `checklist.md` (the ten §6.1 items above in the spec's order, each with an evidence
  path or `N/A` + reason).
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`, reviewer id ≠
  implementer id, head SHA), `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path (`lane_gate.py` refuses it).
