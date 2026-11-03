# Field map: `SqlTraceInsightsReport` (`GET /sql-trace/insights`)

Source: `src/sharpit/engine/capture/sqlinsights.py` over `SqlTraceRecorder.rows()` / `.report([])` and
`HttpExchangeBuffer.rows()`. Golden: `tests/fixtures/bootui/2.2.0/sql-trace/insights.captured.json`.

| Key | Source / value |
|---|---|
| available, unavailableReason | `sqla.sql_trace_unavailable_reason(ctx)` (tracing off, SQLAlchemy absent) -> `false` + reason |
| capturing | `recorder.recording` |
| window.retainedStatements, bufferSize | `len(rows())`, `recorder.max_entries` |
| window.evicted, totalCaptured | `recorder.report([])["stats"]["evicted"]`, `["totalCaptured"]` |
| window.oldestTimestamp, newestTimestamp | min/max row `timestamp` (epoch ns -> ms); `null` on an empty ring (`nullable.json`) |
| window.totalDurationMillis | sum of whole-ms row durations |
| statements[].id / sql | `normalize(row["sql"])` fingerprint / normalized text (never the stored literal) |
| statements[].category, executions, total/max/avg, errorCount | per group; avg rounded 2 dp |
| statements[].p50/p95/p99DurationMillis | nearest-rank over the group's whole-ms durations |
| statements[].shareOfRetainedTimePercent | `SqlShares.percent` (0 with no measurable time) |
| statements[].topFor | criterion enum names verbatim |
| statements[].potentialNPlusOne | SELECT and executions >= 5 (BootUI's default threshold, not the setting) |
| statements[].callSites, entryIds, entryIdsTruncated | row `callSite` (max 5), row `id` (max 500) |
| topPerCriterion, statementsTruncated, distinctStatements | 10; distinct > ranked; group count |
| attribution.supportedCorrelations | `["TRACE_ID"]` (row `traceId` = request id, joined to exchange `id`) |
| attribution.requestsConsidered | retained exchange rows |
| attribution.routes[].id/method/route | `"<METHOD> <masked path>"`; exchange row `method` / `mask_route(path)` |
| attribution.routes[].routeSource | always `MASKED_PATH`: exchange rows carry no route template |
| attribution.routes[].requests, traceCorrelated | distinct request ids; = executions |
| attribution.routes[].threadCorrelated, timeWindowCorrelated | `0`: tiers not offered |
| attribution.routes[].topStatements[] | top 5 groups per route (`statementId`, `sql`, ...) |
| attribution.unattributed | rows without a request id or whose exchange was evicted; BootUI reason verbatim |
| attribution.ambiguous | always 0: a request id names one exchange; reason with BootUI -> sharpit |
| attribution.unattributed.reason, ambiguous.reason | `null` while attribution is unavailable (`nullable.json`) |
| attribution.available/unavailableReason | `false` + reason when HTTP exchange capture is off (`capture.exchanges is None`) |
| attribution.notes, notes | BootUI strings; BootUI -> sharpit; the OpenTelemetry advice note adapted to request ids |
