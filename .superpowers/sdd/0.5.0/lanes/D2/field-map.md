# D2 field map: BootUI 2.2.0 capture drift keys

Implementer: Claude Code subagent (claude-opus-5-5)

Every drifted key, where sharpit fills it, and why when it is null. Nullable reasons live in
`tests/fixtures/bootui/2.2.0/<panel>/nullable.json`.

## http-exchanges (`GET /http-exchanges`, `GET /http-exchanges/routes`)

| BootUI key | sharpit source | Notes |
|---|---|---|
| `HttpExchangeDto.route` | `engine/capture/exchanges.py::exchange_row` via `engine/capture/routes.py::route_of` | FastAPI's matched `scope["route"].path` (behind its mounts, `fastapi/capture.py::_route_template`), else `mask_route` of the masked path |
| `HttpExchangeDto.routeSource` | same | `FRAMEWORK_TEMPLATE` or `MASKED_PATH`; `DECLARED_MAPPING` is not produced (no declared-route matching for unmatched paths) |
| `HttpExchangeDto.requestId` | `exchange_row(request_id=...)` | sharpit's correlation id (= `id`) |
| `HttpExchangesReport.retention` | `HttpExchangeBuffer._retention` | `capacity`, `retained`, `evicted` real; `reservedCapacity`, `reserved`, `slowThresholdMillis` null (no reserved share, no slow threshold): nullable.json |
| `GET /http-exchanges?route=` | `HttpExchangeBuffer.report(route=)` | exact match, before paging |
| `HttpRoutesReport.*` | `engine/capture/routes.py::summarize_http_routes` | `window`, `routes`, `topPerCriterion` (clamped 1..100, default 25), `routesTruncated`, `distinctRoutes`, `notes` |
| `HttpRouteWindowDto.oldestTimestamp/newestTimestamp` | `routes.py::_window` | null on an empty ring: nullable.json |
| `HttpRouteDto.*` | `routes.py::_route_dto` | nearest-rank p50/p95/p99; `errorCount` = status >= 400 or a failed send; `topFor` from REQUESTS, TOTAL_DURATION, P95_DURATION |
| MCP `get_http_routes` | `engine/tools.py` | `LIMIT` schema, panel `http-exchanges`, read-only; CLI `http routes` |

## exceptions

| BootUI key | sharpit source | Notes |
|---|---|---|
| `ExceptionsReport.caughtInCode` | `ExceptionStore.report`, `tools.exceptions_report` | always null: no caught-exceptions sensor (golden has null) |
| `GET /exceptions/caught` (`CaughtExceptionsReport`) | `engine/capture/exceptions.py::caught_report`, `fastapi/routes/exceptions.py` | `available: false` with the plan's reason; served ahead of `/exceptions/{id}` |

## sql-trace

| BootUI key | sharpit source | Notes |
|---|---|---|
| `SqlTraceEntryDto.durationMicros` | `SqlTraceRecorder.record`: `duration_ns // 1_000` | computed once at capture; `durationMillis` unchanged |
| `SqlTraceReport.retention` | `SqlTraceRecorder.report` | `capacity`, `retained`, `evicted`, `slowThresholdMillis` real; `reservedCapacity`, `reserved` null (no reserved share); null while unavailable |
| MCP `get_sql_traces` | `engine/tools.py::_sql_traces_view` | `QUERY_LIMIT`: entries filtered by sql/error/call site, capped, plus `page` |

## log-tail

| BootUI key | sharpit source | Notes |
|---|---|---|
| `LogLineDto.messageOmitted` | `SharpitLogHandler.line` | `masked is None`: true only under METADATA_ONLY |
| MCP `get_log_tail` | `engine/tools.py::_log_tail_view` | `QUERY_LIMIT`: newest matching lines, oldest first, plus `page` |

## activity

| BootUI key | sharpit source | Notes |
|---|---|---|
| `RequestProfileDto.restCalls/cacheAccesses/sections/correlationTiers` | `activity.request_profile`, `_unavailable_profile` | empty lists: sharpit captures no outbound calls or cache operations |
| `RequestProfileDto.approximate` | same | true when a statement finished after the response (the existing heuristic) |
| `GET /activity` `source/route/run/requestId/noRequest` | `fastapi/routes/activity.py`, `activity_report(journal_filters=)` | the feed is always the buffers: journal-only filters add the verbatim BootUI warning |
| `RuntimeJournalStatusDto` (`GET /activity/journal`) | `activity.journal_status_dto` | `enabled: false`, zeros; `runId`, `oldestRetainedAt`, `recorded` null: nullable.json; `previousRunsUnavailable` says why |
| `RuntimeResourcesDto` (`GET /activity/resources`) | `activity.resources_dto` | `available: false`; `totals` null until U20 samples memory/CPU: nullable.json |
| MCP `get_live_activity` | `engine/tools.py` | schema `LIMIT` -> `QUERY_LIMIT`, `query` is the feed's `q` |
| MCP `get_request_profile` | `engine/tools.py` | `ID` schema, panel `activity`, read-only; CLI `activity profile` |

Not built (reasons in handoff.md): `POST /activity/journal/clear`, `GET /activity/request/{id}/journal`, MCP compacted
default limits (20/25/50), `DECLARED_MAPPING` route source, sql-trace entry keys `requestId/executionId/threadKind/requestPhase`.
