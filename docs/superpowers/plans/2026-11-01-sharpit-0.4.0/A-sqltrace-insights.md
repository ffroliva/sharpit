# Lane A-sqltrace-insights: `GET /sql-trace/insights` (best effort)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development, one task at a time,
> `/sharpit:check` before every commit.

| | |
|---|---|
| **Lane id** | `A-sqltrace-insights` (worktree `...\0.4.0-A-sqltrace-insights`, branch `lane/0.4.0-A-sqltrace-insights`); best effort |
| **Goal** | BootUI's `SqlTraceInsightsReport`: statement rankings by seven criteria and route attribution, computed on demand from the retained SQL Trace ring — the route skipped in 0.2.0. |
| **Spec** | §2 (best effort), §4, §6.1, §7 row `sql-trace insights`, §11 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §8; BootUI `SqlTraceInsightsService.java`, `SqlStatementRanking.java` (`TOP_PER_CRITERION = 10`, `MAX_RANKED_STATEMENTS = 70`, `Criterion`: `TOTAL_DURATION, MAX_DURATION, EXECUTIONS, AVG_DURATION, ERROR_COUNT, P95_DURATION, P99_DURATION`), `SqlRouteAttribution.java`, DTOs `SqlTraceInsightsReport`, `SqlTraceWindowDto`, `SqlStatementRankingDto`, `SqlRouteAttributionDto`, `SqlRouteRankingDto`, `SqlAttributionBucketDto` |
| **Worker** | M, mechanical port → agy |
| **Depends on** | F, D1, **A-sqlalchemy-statistics merged** (it last touched `sqltrace.py`); D2 follows this lane |
| **May touch** | `src/sharpit/engine/capture/sqlinsights.py` (new), the insights route in F's `fastapi/routes/sql_trace.py` module, `get_sql_trace_insights` MCP stub, `ui/src/views/SqlTrace.svelte` (an Insights tab only), `tests/engine/capture/test_sqlinsights.py`, `tests/fastapi/test_sql_trace_insights_api.py`, goldens, lane folder |
| **Must NOT touch** | §10.3 protected files; `engine/capture/sqltrace.py` (read its public API only); other panels' collectors |

**Architecture:** A pure function over `SqlTraceRecorder.rows()` (`sqltrace.py:532`, oldest first, epoch-ns
timestamps) and `HttpExchangeBuffer.get(request_id)`. Statements group by `normalize(row["sql"]).fingerprint`
(`sqltrace.py:231`); route attribution joins rows' `traceId` (the request id) to exchange rows (`method`, `endpoint`);
the only correlation sharpit supports is `"request"` (BootUI's trace correlation), so `threadCorrelated` and
`timeWindowCorrelated` are `0` and `supportedCorrelations == ["request"]` (logged §11). No new capture, no SQL, no
socket.

## Global Constraints

- GET only, in-memory, bounded (`MAX_RANKED_STATEMENTS = 70`, routes top 10 by total time); no side effects.
- **Never exposes bound parameters, even with parameter capture on** (BootUI test of that name): `sql` is
  `normalize(...).sql`, not the stored row text.
- Durations: ring rows hold whole `durationMillis`; percentiles are nearest-rank over those values (BootUI uses
  micros; logged §11 — sharpit stores ms).
- Every DTO key emitted. `# ported:` citations. Red is an assertion. PT018.

## Review Focus

1. **Parameter capture on**: stored rows carry masked literal SQL. Expect rankings keyed and shown by the normalised
   text; no literal. Pinned in Task 1: `test_never_exposes_bound_parameters_even_when_capture_is_on`
   (`# ported: SqlTraceInsightsServiceTests.neverExposesBoundParametersEvenWhenParameterCaptureIsOn`).
2. **Ties** across criteria (equal totals, equal counts). Expect a stable order (metric desc, then `sql` asc) so two
   GETs return identical bytes. Pinned in Task 1: `test_rankings_are_deterministic_on_ties`.
3. **Statements outside any request / exchange evicted.** Expect the `unattributed` bucket with a reason, not a route
   named `null`. Pinned in Task 1: `test_unattributed_bucket_reason`.
4. **Paused recording / evicted rows.** Expect BootUI's notes (window, not lifetime). Pinned in Task 1 (ported tests).
5. **Tracing off or SQLAlchemy absent.** Expect `available:false` with `tools.sql_trace_unavailable_reason`
   (`engine/tools.py:253`). Pinned in Task 1: `reportsUnavailableWhenTracingIsOff`.

---

### Task 1: `engine/capture/sqlinsights.py`

**Interfaces:** `insights_report(recorder: SqlTraceRecorder | None, exchanges: HttpExchangeBuffer | None, reason: str |
None) -> dict[str, Any]`; `rank(groups: list[Group]) -> list[dict[str, Any]]`; `percentile(sorted_ms: list[int], p:
int) -> float`; `topFor` values are the enum names verbatim (`"TOTAL_DURATION"`, …, `"P99_DURATION"`;
`SqlStatementRanking.java:145` adds `criterion.name()`).

- [ ] **Step 1:** Ported tests (`SqlTraceInsightsServiceTests`): `reportsUnavailableWhenTracingIsOff`,
  `stillRanksStatementsWhenTheRuntimeCannotSupplyRequestEvidence`, `describesTheBoundedWindowTheRankingsCover`,
  `warnsWhenOlderExecutionsHaveAlreadyBeenEvicted`, `saysTheFiguresDescribeTheRetainedWindowRatherThanLifetimeTotals`,
  `reportsPausedRecordingSoAStaleWindowIsNotMistakenForAQuietSystem`,
  `neverExposesBoundParametersEvenWhenParameterCaptureIsOn`, `attributesRecordedStatementsToTheSuppliedRequests`; plus
  the Review Focus tests. Note strings copied verbatim from the Java service.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: sql trace insights rankings and route attribution`.

### Task 2: Route, MCP, safety

**Interfaces:** `GET {api}/sql-trace/insights` (panel `sql-trace`, already `actionCapable=True`); MCP
`get_sql_trace_insights` (read).

- [ ] **Step 1:** Tests `test_insights_golden_parity` (`tests/fixtures/bootui/2.2.0/sql-trace/insights.json`),
  `test_insights_no_side_effects`, `test_insights_respects_panel_disabled`, `test_mcp_read_tool_only`, a masking
  corpus row (literal secret under `capture_parameters=true` absent from `/insights`).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS + full gate. Commit `feat: sql-trace insights route and MCP read tool`.

### Task 3: UI tab, live check, evidence

- [ ] **Step 1:** Insights tab in `ui/src/views/SqlTrace.svelte` (+ vitest: criterion switcher, route table, notes
  shown). `npm --prefix ui run check` PASS.
- [ ] **Step 2:** Live on `examples/fastapi_sqla` after a few requests; `live-verify.md`. Commit `feat: sql-trace insights tab and lane evidence`.

## §6.1 → task

1 parity + field map: 2 · 2 citations: 1 · 3 safety/masking: 1 (RF1), 2 · 4 gatekeeper: n/a (no library) · 5 budget:
n/a (no hot path; GET compute bounded by the ring size) · 6 MCP read-only: 2 · 7 Svelte: 3 · 8 gates: 2–3 · 9 live: 3 ·
10 handoff: every commit.

## Lane evidence checklist (`.superpowers/sdd/0.4.0/lanes/A-sqltrace-insights/`)

`handoff.md` · `field-map.md` · `checklist.md` · `findings.md` · `review.md` (`VERDICT: APPROVE`, reviewer ≠ implementer,
head SHA) · `gate/` (four gates, lowest-direct, no-SQLAlchemy logs, each naming the head SHA) · `live-verify.md`.
