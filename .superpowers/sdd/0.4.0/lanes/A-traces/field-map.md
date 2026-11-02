# Field map: traces (contract §7)

Spans are SDK `ReadableSpan`s read duck-typed at request time (`src/sharpit/engine/capture/traces.py`).

## TracesReport

| Key | Python source |
|---|---|
| `enabled` | `unavailableReason is null` (the buffer is armed on the application's SDK provider) |
| `unavailableReason` | sharpit extension (not in BootUI's DTO): `otel.NO_SDK`, `otel.NOT_SDK_PROVIDER`, or `NOT_ARMED` (provider set after startup) |
| `retained` | number of traces in the buffer after hiding sharpit's own traces |
| `capacity` | the buffer bound, **in spans** (1000); BootUI bounds traces. Memory scales with spans, so sharpit bounds those |
| `traces` | one summary per trace id, newest start first, `limit` clamped 1..500 |

## TraceSummaryDto

| Key | Source |
|---|---|
| `traceId` | `span.context.trace_id`, 32 lower-case hex digits |
| `rootSpanName` | earliest span whose parent is absent from the trace; name through `Masker.mask_path` |
| `httpPath` | root SERVER span, else the first SERVER span with `http.route`, `url.path`, `http.target`, `url.full` or `http.url`; authority and query dropped, matrix params masked; `null` when none (`nullable.json`) |
| `services` | sorted distinct `resource.attributes["service.name"]`, at most 20 (`MAX_SUMMARY_SERVICES`) |
| `startEpochNanos` / `endEpochNanos` / `durationNanos` | min `start_time`, max `end_time`, their difference (epoch ns) |
| `spanCount` | spans retained for the trace |
| `hasError` | any `status.status_code.name == "ERROR"` |
| `hasAi` | any span attribute key starting `gen_ai.` |

## SpanDto

| Key | Source |
|---|---|
| `traceId` / `spanId` / `parentSpanId` | `context.trace_id` (32 hex), `context.span_id` (16 hex), `parent.span_id` or `null` |
| `name` | `span.name` through `mask_path` |
| `kind` | `span.kind.name` (`SERVER`, `CLIENT`, `INTERNAL`, `PRODUCER`, `CONSUMER`) |
| `serviceName` | `resource.attributes["service.name"]` or `null` |
| `scope` | `instrumentation_scope.name` or `null` |
| `startEpochNanos` / `endEpochNanos` / `durationNanos` | `start_time`, `end_time`, difference |
| `statusCode` / `statusMessage` | `status.status_code.name`; `status.description` through `mask_text` (nullable) |
| `attributes[]` | `{key, type, value}`: `type` is the Java `AttributeType` name (`STRING`, `BOOLEAN`, `LONG`, `DOUBLE`, `*_ARRAY`); `value` a masked string |
| `events[]` | `{name, timeOffsetNanos = event.timestamp - span.start_time, attributes[]}` |

Attribute masking at read: `db.statement`/`db.query.text` via `mask_text`; `http.request.header.*` /
`http.response.header.*` via `mask_header`; `url.full`/`http.url` lose scheme and authority; `url.query` via `mask_query`;
everything else via `mask` then `mask_text`.

No `detail` golden exists (G0a captured only the list), so detail parity is unchecked; the DTO keys are pinned by
`tests/engine/capture/test_traces.py::test_summary_and_span_dto_keys`.
