# BootUI 2.2.0 JSON contract — sharpit 0.4.0 Wave C (Runtime & Graph Modes)

Source checkout: `C:\development\github\boot-ui-ref` (commit `ddfcb2436`, 2026-10-23). All source paths below are relative to that root. DTOs live in `bootui-engine/src/main/java/io/github/jdubois/bootui/core/dto/`; Spring controllers in `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/`; engine logic in `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/`; UI in `bootui-ui/src/main/frontend/src/`. Sharpit reference: `docs/reference/BOOTUI-CONTRACT-MVP.md` and `docs/reference/BOOTUI-PYTHON-MAPPING.md`. The BootUI adapter uses `/bootui/api`; substitute `/sharpit/api` for sharpit.

Conventions: Jackson emits record component names in camelCase, root DTO without envelope wrapper, and nullable record components as `null` (MVP §1). Primitive numbers and booleans are non-null. Timestamps are epoch milliseconds (`long`) unless specified as nanoseconds (`long` in AI / OTel traces); byte quantities are bare bytes (`long`); durations are milliseconds (`long`) unless specified. JSON examples are constructed directly from Java record components. Error bodies and reason strings are copied verbatim with `BootUI` changed to `sharpit`, per sharpit `AGENTS.md`.

---

## 1. Metrics

Backing panel id: `metrics` (registered in `bootui-engine/.../engine/panel/BootUiPanels.java`). Read-only runtime panel displaying Micrometer metrics with curated provenance explanations.

### 1. Endpoints
- `GET /bootui/api/metrics`:
  - Query parameters:
    - `q` (string, optional, default empty): case-insensitive substring search matching meter name or description.
    - `type` (string, optional, default empty): matches Micrometer `Meter.Type` enum name (`GAUGE`, `COUNTER`, `TIMER`, `LONG_TASK_TIMER`, `DISTRIBUTION_SUMMARY`, `OTHER`). Case-insensitive; validated against valid enum names.
    - `group` (string, optional, default empty): matches curated provenance group id from `MeterFamilyCatalogue` (e.g. `jvm`, `http-server`, `system`, `datasource`, `cache`, `executor`, `logback`, `unclassified`).
    - `provenance` (string, optional, default empty): matches `classified` or `unclassified`.
    - `explanation` (string, optional, default empty): matches source type `CURATED`, `NATIVE`, or `UNKNOWN`.
    - `offset` (string/int, optional, default `0`): integer `>= 0`.
    - `limit` (string/int, optional, default `200`, max `1000`): integer clamped to `1..1000`.
  - Request body: None.
  - Returns `MetricsReport`.
- `GET /bootui/api/metrics/detail`:
  - Query parameters:
    - `name` (string, required): meter name, non-blank.
    - `tag` (repeated string, optional, default empty): tag filter list using `key:value` syntax (e.g. `tag=uri:/api/orders&tag=status:200`).
    - `offset` (string/int, optional, default `0`): integer `>= 0`.
    - `limit` (string/int, optional, default `100`, max `1000`): integer clamped to `1..1000`.
  - Request body: None.
  - Returns `MetricDetailDto`.

### 2. Response DTOs
Source paths:
- `MetricsReport.java` (`bootui-engine/src/main/java/io/github/jdubois/bootui/core/dto/MetricsReport.java`):
  - `metricsAvailable`: boolean (false if `MeterRegistry` is unavailable/null)
  - `total`: int (total distinct meter names in the registry)
  - `meters`: `MetricMeterDto[]` (paged list of matching meters)
  - `availableTypes`: `string[]` (distinct sorted meter types present in registry, e.g. `["COUNTER", "GAUGE", "TIMER"]`)
  - `page`: `PageMetadata` (`total`: int, `matched`: int, `offset`: int, `limit`: int, `returned`: int, `hasMore`: boolean)
  - `groups`: `MetricGroupDto[]` (provenance groups aggregated over filters before group narrowing)
  - `catalogueVersion`: `string|null` (version of the curated meter catalogue, e.g. `"2026.10"`)
- `MetricMeterDto.java` (`bootui-engine/src/main/java/io/github/jdubois/bootui/core/dto/MetricMeterDto.java`):
  - `name`: string
  - `description`: string|null
  - `baseUnit`: string|null
  - `type`: string|null (`"GAUGE"`, `"COUNTER"`, `"TIMER"`, etc.)
  - `availableTags`: `MetricAvailableTagDto[]` (tag keys and observed distinct values)
  - `provenance`: `MetricProvenanceDto`
- `MetricDetailDto.java` (`bootui-engine/src/main/java/io/github/jdubois/bootui/core/dto/MetricDetailDto.java`):
  - `metricsAvailable`: boolean
  - `name`: string
  - `description`: string|null
  - `baseUnit`: string|null
  - `type`: string|null
  - `measurements`: `MetricMeasurementDto[]` (aggregated statistics across matching meters)
  - `availableTags`: `MetricAvailableTagDto[]`
  - `samples`: `MetricSampleDto[]` (concrete series samples)
  - `totalSamples`: int
  - `samplePage`: `PageMetadata`
  - `samplesTruncated`: boolean
  - `provenance`: `MetricProvenanceDto`
- Supporting DTOs:
  - `MetricGroupDto` (`id`: string, `label`: string, `contributor`: string, `summary`: string, `interpretation`: string, `meterCount`: int, `describedMeterCount`: int, `families`: string[], `commonTagKeys`: string[], `baseUnits`: string[])
  - `MetricProvenanceDto` (`groupId`: string, `groupLabel`: string, `contributor`: string, `familyId`: string, `familyLabel`: string, `classified`: boolean, `explanation`: string, `explanationSource`: string [`"CURATED"|"NATIVE"|"UNKNOWN"`], `interpretation`: string)
  - `MetricAvailableTagDto` (`key`: string, `values`: string[], `truncated`: boolean)
  - `MetricMeasurementDto` (`statistic`: string [`"COUNT"|"TOTAL"|"TOTAL_TIME"|"MAX"|"VALUE"|"UNKNOWN"`], `value`: double)
  - `MetricSampleDto` (`tags`: `MetricTagDto[]`, `measurements`: `MetricMeasurementDto[]`)
  - `MetricTagDto` (`key`: string, `value`: string)

JSON Example (`GET /bootui/api/metrics`):
```json
{
  "metricsAvailable": true,
  "total": 65,
  "meters": [
    {
      "name": "jvm.memory.used",
      "description": "The amount of used memory",
      "baseUnit": "bytes",
      "type": "GAUGE",
      "availableTags": [
        {"key": "area", "values": ["heap", "nonheap"], "truncated": false},
        {"key": "id", "values": ["G1 Old Gen", "G1 Eden Space"], "truncated": false}
      ],
      "provenance": {
        "groupId": "jvm",
        "groupLabel": "JVM & Runtime",
        "contributor": "Micrometer JVM instrumentation",
        "familyId": "jvm-memory",
        "familyLabel": "JVM Memory Pools",
        "classified": true,
        "explanation": "Current memory allocated to Java heap and native regions.",
        "explanationSource": "CURATED",
        "interpretation": "High heap utilization approaching max indicates GC pressure."
      }
    }
  ],
  "availableTypes": ["COUNTER", "GAUGE", "TIMER"],
  "page": {"total": 65, "matched": 1, "offset": 0, "limit": 200, "returned": 1, "hasMore": false},
  "groups": [
    {
      "id": "jvm",
      "label": "JVM & Runtime",
      "contributor": "Micrometer JVM instrumentation",
      "summary": "Core JVM memory, GC, and thread metrics",
      "interpretation": "Monitors runtime health and sizing.",
      "meterCount": 18,
      "describedMeterCount": 18,
      "families": ["JVM Memory Pools", "Garbage Collection"],
      "commonTagKeys": ["area", "id"],
      "baseUnits": ["bytes", "seconds"]
    }
  ],
  "catalogueVersion": "2026.10"
}
```

### 3. Error bodies and reason strings
Controller local `@ExceptionHandler(IllegalArgumentException.class)` in `MetricsController.java:48-51`:
- Status: `400 Bad Request`
- Body: `{"error": "<message>"}`
- Verbatim exception messages:
  - `"Metric name must not be blank"`
  - `"Metric offset must be 0 or greater"`
  - `"Metric limit must be between 1 and 1000"`
  - `"Metric type must be one of: COUNTER, DISTRIBUTION_SUMMARY, GAUGE, LONG_TASK_TIMER, OTHER, TIMER"`
  - `"Metric group must be one of: <comma-separated list of groups>"`
  - `"Metric provenance must be one of: classified, unclassified"`
  - `"Metric explanation source must be one of: CURATED, NATIVE, UNKNOWN"`
  - `"Metric tag filters must use key:value syntax"`
Panel gating:
- Panel disabled: `403 {"error":"sharpit panel access denied","panel":"metrics","reason":"Panel is disabled via bootui.panels.metrics.enabled=false"}`

### 4. Panel flags and settings
- Panel ID: `metrics`, Title: `"Metrics"`, `actionCapable: false`, API prefix: `"/metrics"`.
- Properties:
  - `bootui.panels.metrics.enabled=true` (show panel when Micrometer `MeterRegistry` is present)
  - View-only: `bootui.panels.metrics.read-only` not applicable (no actions).
  - No `bootui.metrics.*` property keys exist in `BootUiProperties.java`.

### 5. Side effects
- Reads are passive in-memory queries over `MeterRegistry.getMeters()`.
- Note: Standard meters read cached counters/gauges in memory. User-registered custom `Gauge` meters execute the supplier function provided when the gauge was created; well-behaved gauges do no I/O, but BootUI has no control over user lambda code. BootUI performs no socket, file, database, logger, or environment mutations.

### 6. Streams
None. Poll-based UI with optional auto-refresh.

### 7. MCP tools and CLI commands
- MCP Tool: `get_metrics`
  - Schema: `QUERY_LIMIT` (`query` string optional, `limit` int optional, compacted default `25`).
  - Action: `false` (read-only).
  - Output: Compacted view `{meters: MetricMeterDto[], page: PageMetadata}`.
- CLI:
  - `bootui metrics` (options: `--query <q>`, `--limit <n>`).

### 8. Advisor rules
None (runtime telemetry panel, not an advisor).

### 9. UI
- View: `bootui-ui/src/main/frontend/src/views/Metrics.vue`
- Components: `PanelHeader.vue`, `PanelSkeleton.vue`, `ServerListFooter.vue`.
- Composables: `useAutoRefresh.js`, `describeLoadError.js`.
- API calls: `getJson('api/metrics?...')`, `getJson('api/metrics/detail?...')`.

### 10. Tests that define behaviour
- Controller: `bootui-spring-boot-starter/src/test/java/io/github/jdubois/bootui/autoconfigure/web/MetricsControllerTests.java`
  - `# ported: MetricsControllerTests.metricsDelegatesToProvider`
  - `# ported: MetricsControllerTests.detailBindsNameAndTagParametersAndDelegates`
  - `# ported: MetricsControllerTests.malformedTagFilterIsMappedToBadRequest`
  - `# ported: MetricsControllerTests.invalidListLimitIsMappedToCanonicalBadRequest`
  - `# ported: MetricsControllerTests.unknownProvenanceFiltersAreMappedToCanonicalBadRequests`
  - `# ported: MetricsControllerTests.missingDetailNameIsMappedToCanonicalBadRequest`
  - `# ported: MetricsControllerTests.defaultSelfDataFilterHidesBootUiSamples`
- Engine: `bootui-engine/src/test/java/io/github/jdubois/bootui/engine/metrics/MetricsReportProviderTests.java`
  - `# ported: MetricsReportProviderTests.metricsGroupsMetersByNameAndAggregatesTagValues`
  - `# ported: MetricsReportProviderTests.metricsFiltersAndPagesInDeterministicNameOrder`
  - `# ported: MetricsReportProviderTests.metricsUsesBoundedDefaultsAndRejectsInvalidPaging`
  - `# ported: MetricsReportProviderTests.detailFiltersByTagsAndAggregatesFiniteMeasurements`
  - `# ported: MetricsReportProviderTests.detailPagesDeterministicallyAndAggregatesEveryMatchingSample`
  - `# ported: MetricsReportProviderTests.detailBoundsTagValuesWhileRetainingDeterministicValues`
  - `# ported: MetricsReportProviderTests.detailUsesMaximumWhenAggregatingMaxStatistic`
  - `# ported: MetricsReportProviderTests.detailAcceptsColonInTagValues`
  - `# ported: MetricsReportProviderTests.detailRejectsMalformedTagFilters`
  - `# ported: MetricsReportProviderTests.detailRejectsBlankNameAndInvalidPaging`
  - `# ported: MetricsReportProviderTests.metricsReportUnavailableWhenNoRegistry`
  - `# ported: MetricsReportProviderTests.metricsNeverLeaksTagValuesIntoProvenanceOrGroups`
- UI: `bootui-ui/src/main/frontend/src/views/Metrics.test.js`.

### 11. Python mapping
- Python data source: `prometheus_client.REGISTRY` collectors / metrics samples, or OpenTelemetry `MeterProvider` metric readers.
- Optional dependency: `prometheus-client`.
- Proposed gatekeeper: `src/sharpit/engine/prometheus.py`.

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: Micrometer `Meter.Type.LONG_TASK_TIMER` and JVM-specific GC meter names (`jvm.gc.pause`, `jvm.gc.memory.allocated`) drop or map to Prometheus counter/gauge equivalents.
- [AMBIG]: Prometheus metrics do not natively group by "family" or "provenance" unless sharpit ships a curated catalogue for Python metrics (e.g. `python_gc_*`, `process_*`, `starlette_*`).

### 13. Size estimate
- **M (≤ 1 day)**: Parsing and paging logic is straightforward, but Prometheus registry sample inspection and tag value aggregation requires robust data structures.

---

## 2. Memory (Advisor)

Backing panel id: `memory`. On-demand diagnostic advisor evaluating 32 health and configuration checks against JVM runtime memory observations.

### 1. Endpoints
- `GET /bootui/api/memory`:
  - Query parameters: None.
  - Request body: None.
  - Returns `MemoryReport` (returns cached previous scan, or initial unscanned state).
- `POST /bootui/api/memory/scan`:
  - Query parameters: None.
  - Request body: None.
  - Executes single-flight memory rule evaluation; returns fresh `MemoryReport`.
- `GET /bootui/api/memory/rules/{ruleId}/violations`:
  - Query parameters:
    - `scanId` (string, optional): matches scan id.
    - `offset` (string/int, optional, default `0`): integer `>= 0`.
    - `limit` (string/int, optional, default `100`, max `1000`): integer clamped to `1..1000`.
  - Request body: None.
  - Returns `AdvisorRuleViolationsDto`.

### 2. Response DTOs
Source paths:
- `MemoryReport.java` (`bootui-engine/.../core/dto/MemoryReport.java`):
  - `localOnly`: boolean (`true`)
  - `disclaimer`: string
  - `rulesEvaluated`: int
  - `violationsFound`: int
  - `summary`: `MemorySummaryDto`
  - `severityCounts`: `MemorySeverityCountDto[]`
  - `scan`: `MemoryScanStatusDto`
  - `results`: `MemoryRuleResultDto[]`
  - `analysisErrors`: `MemoryRuleResultDto[]`
  - `evidence`: `AdvisorEvidenceDto`
  - `violationDetails`: `AdvisorViolationDetailsDto|null`
- `MemorySummaryDto.java` (`bootui-engine/.../core/dto/MemorySummaryDto.java`):
  - `heapUsedBytes`: long (bytes)
  - `heapMaxBytes`: long (bytes)
  - `heapUsedPercent`: int (0..100)
  - `liveThreads`: int
  - `peakThreads`: int
  - `deadlockDetected`: boolean
  - `loadedClasses`: int
  - `histogramAvailable`: boolean
- `MemoryRuleResultDto.java` (`bootui-engine/.../core/dto/MemoryRuleResultDto.java`):
  - `id`: string (e.g. `"MEM-HEAP-001"`)
  - `name`: string
  - `category`: string (`"HEAP_PRESSURE"|"NATIVE_MEMORY"|"MEMORY_POOLS"|"GC_CONFIGURATION"|"THREADS"|"HEAP_CONTENT"|"CLASS_LOADING"`)
  - `severity`: string (`"CRITICAL"|"HIGH"|"MEDIUM"|"LOW"|"INFO"`)
  - `description`: string
  - `status`: string (`"PASS"|"FAIL"|"SKIPPED"|"ERROR"`)
  - `violationCount`: int
  - `sampleViolations`: `string[]` (up to 10 preview items)
  - `recommendation`: string
  - `learnMoreUrl`: string|null
  - `dismissed`: boolean
- Supporting DTOs:
  - `MemorySeverityCountDto` (`severity`: string, `count`: int)
  - `MemoryScanStatusDto` (`analyzer`: string, `status`: string, `message`: string, `scannedAt`: long|null [epoch ms], `rulesEvaluated`: int, `violationsFound`: int)

JSON Example (`GET /bootui/api/memory`):
```json
{
  "localOnly": true,
  "disclaimer": "Findings are local development diagnostics, not production sizing guarantees.",
  "rulesEvaluated": 32,
  "violationsFound": 1,
  "summary": {
    "heapUsedBytes": 134217728,
    "heapMaxBytes": 1073741824,
    "heapUsedPercent": 12,
    "liveThreads": 24,
    "peakThreads": 32,
    "deadlockDetected": false,
    "loadedClasses": 9412,
    "histogramAvailable": false
  },
  "severityCounts": [{"severity": "MEDIUM", "count": 1}],
  "scan": {
    "analyzer": "MemoryAdvisor",
    "status": "COMPLETED",
    "message": "Scan completed in 12ms",
    "scannedAt": 1730487960000,
    "rulesEvaluated": 32,
    "violationsFound": 1
  },
  "results": [
    {
      "id": "MEM-GC-001",
      "name": "Heap sizing is left to default container ergonomics",
      "category": "GC_CONFIGURATION",
      "severity": "INFO",
      "description": "No explicit -Xmx or -XX:MaxRAMPercentage was specified.",
      "status": "FAIL",
      "violationCount": 1,
      "sampleViolations": ["Heap max is 1024 MiB (25% of detected container limit)."],
      "recommendation": "Set -XX:MaxRAMPercentage=75.0 or explicit -Xmx.",
      "learnMoreUrl": "https://www.julien-dubois.com/boot-ui/docs/memory-checks#mem-gc-001",
      "dismissed": false
    }
  ],
  "analysisErrors": [],
  "evidence": {"status": "AVAILABLE", "retainedScans": 1},
  "violationDetails": null
}
```

### 3. Error bodies and reason strings
- Gated read-only on POST scan: `403 {"error":"sharpit panel access denied","panel":"memory","reason":"BootUI is read-only via bootui.read-only=true"}` or `"...bootui.panels.memory.read-only=true"`.
- Panel disabled: `403 {"error":"sharpit panel access denied","panel":"memory","reason":"Panel is disabled via bootui.panels.memory.enabled=false"}`.
- Paging errors on violations endpoint: `400 Bad Request {"error": "'offset' must be a valid integer"}` or `{"error": "'limit' must be between 1 and 1000"}` via `AdvisorViolationException.java`.

### 4. Panel flags and settings
- Panel ID: `memory`, Title: `"Memory"`, `actionCapable: true`, API prefix: `"/memory"`.
- Properties:
  - `bootui.panels.memory.enabled=true`
  - `bootui.panels.memory.read-only=false`
  - No dedicated `bootui.memory.*` properties (limits are governed by shared advisor policies).

### 5. Side effects
- `GET /bootui/api/memory`: Passive read of previous scan report in memory. No socket, file, DB, or logger changes.
- `POST /bootui/api/memory/scan`: Reads JVM management MXBeans (`MemoryMXBean`, `MemoryPoolMXBean`, `ThreadMXBean`, `GarbageCollectorMXBean`), inspects Linux cgroup file `/sys/fs/cgroup/memory.current` / `memory.max` if present. Does NOT trigger garbage collection, heap dumps, or subprocesses.
- `GET /bootui/api/memory/rules/{ruleId}/violations`: Reads retained violation details from memory.

### 6. Streams
None.

### 7. MCP tools and CLI commands
- MCP Tools:
  - `memory_scan` (schema: NONE, action: `true`) → returns scan summary.
  - `get_memory_report` (schema: NONE, action: `false`) → returns `MemoryReport`.
  - `get_memory_rule_violations` (schema: `RULE_VIOLATIONS` [`ruleId`, `scanId`, `offset`, `limit`]) → returns violations.
- CLI:
  - `bootui memory report`
  - `bootui memory scan`
  - `bootui memory violations <ruleId> --scan-id <id>`

### 8. Advisor rules (32 active checks)
Source: `bootui-engine/.../engine/memory/MemoryRules.java` and `docs/MEMORY-CHECKS.md`.
All 32 rules evaluate JVM/HotSpot/cgroup observations.
| Rule ID | Category | Severity | Verbatim Title | Trigger | JVM-Only? |
|---|---|---|---|---|---|
| `MEM-HEAP-001` | HEAP_PRESSURE | MEDIUM | Heap occupancy is near its reported maximum | Occupancy >= 95% of known heap maximum | Yes (JVM heap) |
| `MEM-HEAP-002` | HEAP_PRESSURE | MEDIUM | Old generation is near its maximum | Old generation pool >= 85% of known max | Yes (JVM old gen) |
| `MEM-HEAP-003` | HEAP_PRESSURE | LOW | Maximum heap is capped well below the container limit | Max heap < 15% of container limit (>= 1 GiB) and used >= 80% | Yes (JVM heap vs cgroup) |
| `MEM-HEAP-004` | HEAP_PRESSURE | INFO | Max heap is at or just above the compressed-oops limit | Heap between 32 GiB and 40 GiB (disables Compressed Oops) | Yes (HotSpot JVM) |
| `MEM-HEAP-005` | GC_CONFIGURATION | INFO | Initial and maximum heap differ for a low-latency collector | Initial heap != max heap with ZGC or Shenandoah | Yes (HotSpot JVM) |
| `MEM-HEAP-006` | HEAP_PRESSURE | LOW | Objects are backing up awaiting finalization | Persistent backlog >= 1,000 objects pending finalization | Yes (Java finalizers) |
| `MEM-HEAP-008` | HEAP_PRESSURE | LOW | Old-generation occupancy is increasing across comparable scans | 3 consecutive increases in old-generation post-GC occupancy | Yes (JVM old gen) |
| `MEM-FOOTPRINT-001` | NATIVE_MEMORY | MEDIUM/HIGH | Configured JVM memory leaves little container headroom | Heap + native memory envelope >= 90% (HIGH at 100%) of cgroup | Yes (JVM native sizing) |
| `MEM-FOOTPRINT-002` | NATIVE_MEMORY | LOW | Platform thread stacks reserve a large amount of native memory | Thread count * stack size >= 1 GiB or >= 20% container limit | Yes (Java thread stacks) |
| `MEM-FOOTPRINT-003` | NATIVE_MEMORY | HIGH | Container memory usage is near the cgroup limit | Container memory usage >= 90% of cgroup limit | No (Container cgroup) |
| `MEM-POOL-001` | MEMORY_POOLS | MEDIUM | Metaspace is close to its maximum | Metaspace pool usage >= 85% of reported max | Yes (JVM Metaspace) |
| `MEM-POOL-002` | MEMORY_POOLS | MEDIUM | Code cache is close to its maximum | Code cache (or CodeHeaps sum) >= 90% of max | Yes (JVM JIT code cache) |
| `MEM-POOL-003` | MEMORY_POOLS | LOW/MEDIUM | Direct buffer usage is high | NIO direct buffer capacity >= 80% cap (MEDIUM if DisableExplicitGC) | Yes (Java NIO direct memory) |
| `MEM-POOL-004` | MEMORY_POOLS | LOW | Metaspace has no reported maximum inside a memory-limited container | Metaspace >= 128 MiB without explicit max in container | Yes (JVM Metaspace) |
| `MEM-POOL-005` | MEMORY_POOLS | MEDIUM | Compressed Class Space is close to its maximum | Compressed Class Space pool >= 85% of max | Yes (JVM Metaspace pointers) |
| `MEM-POOL-007` | MEMORY_POOLS | LOW | Direct buffer usage has increased across comparable scans | 3 consecutive increases in direct buffer allocation | Yes (Java NIO buffers) |
| `MEM-GC-001` | GC_CONFIGURATION | INFO | Heap sizing is left to default container ergonomics | No explicit -Xmx or -XX:MaxRAMPercentage specified | Yes (JVM sizing) |
| `MEM-GC-002` | GC_CONFIGURATION | MEDIUM | Cumulative GC time is a large share of uptime | Total GC time > 5% of JVM process uptime | Yes (JVM GC pauses) |
| `MEM-GC-003` | GC_CONFIGURATION | MEDIUM | Recent GC overhead is high | GC duration between consecutive scans > 10% of elapsed time | Yes (JVM GC pauses) |
| `MEM-GC-004` | GC_CONFIGURATION | LOW | Serial GC selected on a multi-core system | Serial GC active with >= 2 CPUs and >= 2 GiB RAM | Yes (HotSpot GC) |
| `MEM-GC-005` | GC_CONFIGURATION | INFO | G1 Full GC occurred between scans | G1 Old Gen Full GC count incremented outside histogram | Yes (HotSpot G1 GC) |
| `MEM-GC-006` | GC_CONFIGURATION | MEDIUM | Most recently completed GC event was long | Last stop-the-world pause lasted >= 1,000 ms | Yes (JVM pause time) |
| `MEM-GC-007` | GC_CONFIGURATION | HIGH | JVM container awareness is explicitly disabled | -XX:-UseContainerSupport active inside container cgroup | Yes (HotSpot flag) |
| `MEM-GC-008` | GC_CONFIGURATION | INFO | Non-generational ZGC is active where generational ZGC is available | Non-generational ZGC active on JDK 21+ | Yes (HotSpot ZGC) |
| `MEM-THREAD-001` | THREADS | CRITICAL | Thread deadlock detected | ThreadMXBean detects cyclic monitor/synchronizer deadlock | Yes (Java thread monitors) |
| `MEM-THREAD-002` | THREADS | MEDIUM | High proportion of BLOCKED threads | >= 5 BLOCKED threads and >= 25% total, or >= 20 BLOCKED | Yes (JVM thread states) |
| `MEM-THREAD-004` | THREADS | INFO | Runnable threads with very high lifetime CPU usage | RUNNABLE thread with accumulated CPU >= 60s and >= 50% uptime | Yes (Java thread CPU timing) |
| `MEM-CONTENT-001` | HEAP_CONTENT | INFO | Classes with very large average instance size | Histogram average instance size >= 512 KiB and >= 10 MiB total | Yes (JVM class histogram) |
| `MEM-CONTENT-002` | HEAP_CONTENT | LOW/MEDIUM | Collections occupy a large share of the heap | JDK collection/map classes >= 50 MiB or >= 10% of heap | Yes (JVM class histogram) |
| `MEM-CONTENT-003` | HEAP_CONTENT | LOW | A single class dominates the sampled heap | Largest non-array class >= 25% of shallow histogram | Yes (JVM class histogram) |
| `MEM-CLASS-001` | CLASS_LOADING | INFO | Very large number of currently loaded classes | Loaded class count >= 50,000 | Yes (JVM classloader) |
| `MEM-CLASS-002` | CLASS_LOADING | INFO | High class-loading churn | Lifetime unloads >= 50,000 or rate >= 1,000/min | Yes (JVM classloader) |

Retired IDs: `MEM-HEAP-007` (committed heap ratio), `MEM-FOOTPRINT-004` (system swap), `MEM-POOL-006`, `MEM-THREAD-003`, `MEM-CONTENT-004`.

### 9. UI
- Views: `bootui-ui/src/main/frontend/src/views/Memory.vue`, `Memory.test.js`.
- Composables/Utils: `useAdvisorPanel.js`, `insightsPanel.js`, `AdvisorFindings.vue`.
- API calls: `getJson('api/memory')`, `postJson('api/memory/scan')`, `getJson('api/memory/rules/{id}/violations?...')`.

### 10. Tests that define behaviour
- Controller: `bootui-spring-boot-starter/.../autoconfigure/memory/MemoryControllerTests.java`
  - `# ported: MemoryControllerTests.memoryReturnsLatestScan`
  - `# ported: MemoryControllerTests.scanEvaluatesRulesAndAppliesDismissals`
  - `# ported: MemoryControllerTests.violationsPagesThroughRetainedDetails`
- Engine: `bootui-engine/.../engine/memory/MemoryScannerTests.java`, `MemoryRulesTests.java`
  - `# ported: MemoryRulesTests.highHeapUtilizationFlagsAboveNinetyFivePercent`
  - `# ported: MemoryRulesTests.threadDeadlockIsCritical`
  - `# ported: MemoryRulesTests.containerMemoryPressureFlagsAtNinetyPercent`
  - `# ported: MemoryRulesTests.compressedOopsCliffDetected`

### 11. Python mapping
- Python data source: Process resident memory from `psutil` or `resource.getrusage(RUSAGE_SELF)`, container cgroup limits from `/sys/fs/cgroup/memory.current` vs `memory.max`, `tracemalloc` snapshots for large allocations, and `gc.get_stats()` / `gc.garbage`.
- Optional dependency: `psutil`.
- Proposed gatekeeper: `src/sharpit/engine/psutil.py`.

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: 30 of the 32 checks evaluate Java/HotSpot concepts (Metaspace, CodeCache, CompressedOops, GC pauses, ZGC, ThreadMXBean, finalizers). Only `MEM-FOOTPRINT-003` (cgroup pressure) ports directly.
- [AMBIG]: Replace the 31 JVM rules with Python-idiomatic memory advisor rules: e.g. `PY-MEM-001` (RSS near cgroup limit), `PY-MEM-002` (uncollectable cyclical garbage in `gc.garbage`), `PY-MEM-003` (high tracemalloc allocation rate), `PY-MEM-004` (thread pool exhaustion).

### 13. Size estimate
- **L (> 1 day)**: Developing the advisor scan harness, rule definitions, and Python-specific diagnostic sensors requires significant careful design.

---

## 3. Live Memory

Backing panel id: `live-memory`. Interactive runtime panel showing JVM memory pools, Paketo-style container sizing calculations, Kubernetes YAML recommendations, and low-footprint mode.

### 1. Endpoints
- `GET /bootui/api/live-memory`:
  - Query parameters (sizing overrides):
    - `totalMemoryMb` (long, optional): container memory budget override in MiB.
    - `threadCount` (int, optional): thread count override for stack calculation.
    - `headRoomPercent` (int, optional, default `0`): safety headroom percentage.
    - `kubernetesBurstableEnabled` (boolean, optional): whether to calculate burstable QoS.
    - `kubernetesActuatorEnabled` (boolean, optional): include actuator health probes in YAML.
  - Request body: None.
  - Returns `LiveMemoryReport`.
- `POST /bootui/api/live-memory/offload`:
  - Action: **Free BootUI memory** (empties in-memory buffers across all panels, then calls `System.gc()`).
  - Query parameters / body: None.
  - Returns `MemoryOffloadReport`.
- `GET /bootui/api/live-memory/footprint`:
  - Query parameters / body: None.
  - Returns `LowFootprintStatus` (whether low-footprint mode is active and which components are paused).
- `POST /bootui/api/live-memory/footprint`:
  - Request body: `LowFootprintRequest` (`{"enabled": boolean}`).
  - Returns `LowFootprintStatus`.

### 2. Response DTOs
Source paths:
- `LiveMemoryReport.java` (`bootui-engine/.../core/dto/LiveMemoryReport.java`):
  - `heap`: `MemoryPoolDto`
  - `nonHeap`: `MemoryPoolDto`
  - `pools`: `MemoryPoolDto[]` (individual memory pools, e.g. G1 Eden, G1 Old, Metaspace)
  - `jvmInputArguments`: `string[]` (masked JVM flags)
  - `suggestedJvmOptions`: `string|null`
  - `calculation`: `MemoryCalculationDto` (Paketo container memory partition calculation)
  - `kubernetes`: `KubernetesMemoryRecommendationDto` (Kubernetes pod requests/limits recommendation)
- `MemoryPoolDto.java` (`bootui-engine/.../core/dto/MemoryPoolDto.java`):
  - `name`: string
  - `usedBytes`: long
  - `committedBytes`: long
  - `maxBytes`: long (-1 if undefined)
  - `usedPercent`: int (0..100)
- `MemoryCalculationDto.java` (`bootui-engine/.../core/dto/MemoryCalculationDto.java`):
  - `totalMemoryBytes`: long
  - `heapBytes`: long
  - `metaspaceBytes`: long
  - `codeCacheBytes`: long
  - `directMemoryBytes`: long
  - `stackBytesPerThread`: long
  - `stackBytesTotal`: long
  - `headRoomBytes`: long
  - `fixedRegionsBytes`: long
  - `threadCount`: int
  - `loadedClasses`: int
  - `liveThreadCount`: int
  - `liveLoadedClassCount`: int
  - `headRoomPercent`: int
  - `virtualThreadsEnabled`: boolean
  - `virtualThreadsProperty`: string|null
  - `jvmOptions`: string
  - `valid`: boolean
  - `error`: string|null
- `KubernetesMemoryRecommendationDto.java` (`bootui-engine/.../core/dto/KubernetesMemoryRecommendationDto.java`):
  - `requestMemoryBytes`: long
  - `limitMemoryBytes`: long
  - `burstableRequestMemoryBytes`: long
  - `currentSnapshotBytes`: long
  - `detectedContainerLimitBytes`: Long|null
  - `requestMemory`: string (display formatted, e.g. `"768Mi"`)
  - `limitMemory`: string
  - `burstableRequestMemory`: string
  - `currentSnapshotMemory`: string
  - `detectedContainerLimitMemory`: string|null
  - `qosClass`: string (`"Guaranteed"|"Burstable"`)
  - `confidence`: string
  - `warnings`: `string[]`
  - `yaml`: string (ready-to-paste Kubernetes manifest snippet)
  - `maxRamPercentage`: double
  - `initialRamPercentage`: double
  - `javaToolOptions`: string
  - `burstableEnabled`: boolean
  - `healthProbesEnabled`: boolean
- `MemoryOffloadReport.java` (`bootui-engine/.../core/dto/MemoryOffloadReport.java`):
  - `heapUsedBeforeBytes`: long
  - `heapUsedAfterBytes`: long
  - `reclaimedBytes`: long
  - `gcRequested`: boolean
  - `explicitGcDisabled`: boolean
  - `entriesCleared`: long
  - `stores`: `MemoryOffloadStoreDto[]` (`id`: string, `label`: string, `cleared`: boolean, `entriesCleared`: long, `failure`: string|null)
  - `durationMillis`: long
- `LowFootprintStatus.java` (`bootui-engine/.../core/dto/LowFootprintStatus.java`):
  - `active`: boolean
  - `sinceEpochMillis`: Long|null
  - `agentAttached`: boolean
  - `components`: `SuspendedComponentDto[]` (`id`: string, `label`: string, `suspended`: boolean, `failure`: string|null)
  - `warnings`: `string[]`
  - `offload`: `MemoryOffloadReport|null`

JSON Example (`GET /bootui/api/live-memory`):
```json
{
  "heap": {"name": "Heap", "usedBytes": 67108864, "committedBytes": 134217728, "maxBytes": 1073741824, "usedPercent": 6},
  "nonHeap": {"name": "Non-Heap", "usedBytes": 41943040, "committedBytes": 50331648, "maxBytes": -1, "usedPercent": 0},
  "pools": [
    {"name": "G1 Eden Space", "usedBytes": 33554432, "committedBytes": 67108864, "maxBytes": -1, "usedPercent": 0},
    {"name": "Metaspace", "usedBytes": 25165824, "committedBytes": 29360128, "maxBytes": -1, "usedPercent": 0}
  ],
  "jvmInputArguments": ["-Xmx1g", "-XX:+UseG1GC"],
  "suggestedJvmOptions": "-XX:MaxRAMPercentage=75.0",
  "calculation": {
    "totalMemoryBytes": 1073741824,
    "heapBytes": 536870912,
    "metaspaceBytes": 134217728,
    "codeCacheBytes": 67108864,
    "directMemoryBytes": 10485760,
    "stackBytesPerThread": 1048576,
    "stackBytesTotal": 33554432,
    "headRoomBytes": 0,
    "fixedRegionsBytes": 245366784,
    "threadCount": 32,
    "loadedClasses": 9500,
    "liveThreadCount": 24,
    "liveLoadedClassCount": 9412,
    "headRoomPercent": 0,
    "virtualThreadsEnabled": false,
    "virtualThreadsProperty": null,
    "jvmOptions": "-XX:MaxMetaspaceSize=128M -Xmx512M",
    "valid": true,
    "error": null
  },
  "kubernetes": {
    "requestMemoryBytes": 1073741824,
    "limitMemoryBytes": 1073741824,
    "burstableRequestMemoryBytes": 805306368,
    "currentSnapshotBytes": 109051904,
    "detectedContainerLimitBytes": 1073741824,
    "requestMemory": "1Gi",
    "limitMemory": "1Gi",
    "burstableRequestMemory": "768Mi",
    "currentSnapshotMemory": "104Mi",
    "detectedContainerLimitMemory": "1Gi",
    "qosClass": "Guaranteed",
    "confidence": "HIGH",
    "warnings": [],
    "yaml": "resources:\n  requests:\n    memory: 1Gi\n  limits:\n    memory: 1Gi",
    "maxRamPercentage": 75.0,
    "initialRamPercentage": 75.0,
    "javaToolOptions": "-XX:MaxRAMPercentage=75.0",
    "burstableEnabled": false,
    "healthProbesEnabled": true
  }
}
```

### 3. Error bodies and reason strings
- Gated read-only actions: `403 {"error":"sharpit panel access denied","panel":"live-memory","reason":"Panel is read-only via bootui.panels.live-memory.read-only=true"}`.

### 4. Panel flags and settings
- Panel ID: `live-memory`, Title: `"Live Memory"`, `actionCapable: true`, API prefix: `"/live-memory"`.
- Properties:
  - `bootui.panels.live-memory.enabled=true`
  - `bootui.panels.live-memory.read-only=false`
  - `bootui.free-on-idle.enabled=false` (automatic offload on idle)
  - `bootui.free-on-idle.idle-duration=5m`

### 5. Side effects
- `GET /bootui/api/live-memory`: Passive read of JMX MXBeans and cgroup. No socket, file, or logger mutations.
- `POST /bootui/api/live-memory/offload`: Mutates in-memory buffers across panels (drops retained entries) and requests full GC via `System.gc()`.
- `POST /bootui/api/live-memory/footprint`: Changes the boolean pause state of in-memory recorders and calls offload if enabled.

### 6. Streams
None.

### 7. MCP tools and CLI commands
- MCP Tools:
  - `get_live_memory` (schema: NONE, action: `false`)
  - `get_low_footprint` (schema: NONE, action: `false`)
  - `enable_low_footprint` (schema: NONE, action: `true`)
  - `disable_low_footprint` (schema: NONE, action: `true`)
- CLI:
  - `bootui memory live`

### 8. Advisor rules
None (runtime panel).

### 9. UI
- View: `bootui-ui/.../views/LiveMemory.vue`, `LiveMemory.test.js`.
- Components: `PanelHeader.vue`, `LowFootprintBanner.vue`, `SpinnerButton.vue`.
- API calls: `getJson('api/live-memory?...')`, `postJson('api/live-memory/offload')`, `getJson('api/live-memory/footprint')`, `postJson('api/live-memory/footprint', {enabled})`.

### 10. Tests that define behaviour
- Controller: `LiveMemoryControllerTests.java`
  - `# ported: LiveMemoryControllerTests.liveMemoryReturnsReport`
  - `# ported: LiveMemoryControllerTests.offloadTriggersBufferClearingAndGc`
  - `# ported: LiveMemoryControllerTests.footprintTogglesRecordingComponents`
- Engine: `MemoryReportProviderTests.java`, `MemoryCalculatorTests.java`, `MemoryOffloadServiceTests.java`
  - `# ported: MemoryCalculatorTests.partitionsContainerBudgetCorrectly`
  - `# ported: MemoryOffloadServiceTests.emptiesAllRegisteredStores`

### 11. Python mapping
- Python data source: `tracemalloc`, `gc.get_stats()`, `resource.getrusage()`, `/sys/fs/cgroup/memory.*`. Offload triggers `gc.collect()`.
- Optional dependency: `psutil`. Gatekeeper: `src/sharpit/engine/psutil.py`.

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: Metaspace, CodeCache, CompressedOops, and `-XX:MaxRAMPercentage` are JVM-only.
- [AMBIG]: In Python, the calculator can partition container memory among Uvicorn/Gunicorn worker processes and estimate worker thread/task allocations.

### 13. Size estimate
- **M (≤ 1 day)**: Memory sizing calculator and offload hooks are clean, but adapting the container sizing model to Python worker processes requires design.

---

## 4. Heap Dump

Backing panel id: `heap-dump`. Diagnostic panel supporting HotSpot class histogram inspection, local `.hprof` heap dump capture, and disk management.

> [!WARNING]
> **File Writing Action Flag**: Capturing a heap dump (`POST /heap-dump/capture`) writes a `.hprof` binary file to disk (`bootui.heap-dump.output-dir`). Passive reads (`GET /heap-dump`) NEVER write files.

### 1. Endpoints
- `GET /bootui/api/heap-dump`:
  - Query parameters:
    - `filter` (string, optional, default empty): substring filter on class name.
    - `smartFilter` (string, optional, default empty): `"big-objects"` (sort by bytes per instance descending) or `"collection-bloat"` (filter to standard collection classes).
  - Request body: None.
  - Returns `HeapDumpReport`.
- `POST /bootui/api/heap-dump/capture`:
  - Query parameters:
    - `live` (boolean, optional, default `true`): only dump live reachable objects.
  - Request body: None.
  - Action: Writes `.hprof` file to `outputDir`, executes `GC.class_histogram`, updates capture status.
  - Returns `HeapDumpReport`.
- `POST /bootui/api/heap-dump/analyze`:
  - Query parameters / body: None.
  - Action: Runs `GC.class_histogram` in memory without writing a `.hprof` file to disk.
  - Returns `HeapDumpReport`.
- `POST /bootui/api/heap-dump/delete`:
  - Query parameters:
    - `name` (string, required): file name of existing dump (must match regex `^[A-Za-z0-9._-]+\.hprof$`).
  - Request body: None.
  - Action: Deletes the specified heap dump file from disk.
  - Returns `HeapDumpReport`.
- `GET /bootui/api/heap-dump/download`:
  - Query parameters:
    - `name` (string, required): file name.
  - Returns: `ResponseEntity<Resource>` with `Content-Disposition: attachment; filename="<name>"`, `application/octet-stream`. Returns `404 Not Found` if `rawDownloadAllowed` is false or file does not exist.

### 2. Response DTOs
Source paths:
- `HeapDumpReport.java` (`bootui-engine/.../core/dto/HeapDumpReport.java`):
  - `hotspotAvailable`: boolean
  - `captureEnabled`: boolean
  - `rawDownloadEnabled`: boolean
  - `outputDirectory`: string (normalized path)
  - `maxDumps`: int
  - `dumpCount`: int
  - `liveHeapUsedBytes`: long (bytes)
  - `freeDiskBytes`: long (bytes)
  - `capture`: `HeapDumpCaptureStatusDto`
  - `dumps`: `HeapDumpFileDto[]` (sorted newest first)
  - `histogramTotalInstances`: long
  - `histogramTotalBytes`: long
  - `topClasses`: `HeapClassHistogramEntryDto[]`
- Supporting DTOs:
  - `HeapDumpFileDto` (`name`: string, `sizeBytes`: long, `createdAtEpochMs`: long, `live`: boolean)
  - `HeapDumpCaptureStatusDto` (`status`: string [`"NOT_CAPTURED"|"CAPTURED"|"ANALYZED"|"ERROR"`], `message`: string|null, `capturedAtEpochMs`: Long|null)
  - `HeapClassHistogramEntryDto` (`rank`: int, `className`: string, `instances`: long, `bytes`: long)

JSON Example (`GET /bootui/api/heap-dump`):
```json
{
  "hotspotAvailable": true,
  "captureEnabled": true,
  "rawDownloadEnabled": false,
  "outputDirectory": ".bootui/heap-dumps",
  "maxDumps": 5,
  "dumpCount": 1,
  "liveHeapUsedBytes": 134217728,
  "freeDiskBytes": 10737418240,
  "capture": {
    "status": "ANALYZED",
    "message": "Live heap analyzed without writing a dump",
    "capturedAtEpochMs": 1730487960000
  },
  "dumps": [
    {"name": "heap-20261030-120000.hprof", "sizeBytes": 146800640, "createdAtEpochMs": 1730487900000, "live": true}
  ],
  "histogramTotalInstances": 124500,
  "histogramTotalBytes": 104857600,
  "topClasses": [
    {"rank": 1, "className": "byte[]", "instances": 1200, "bytes": 41943040},
    {"rank": 2, "className": "java.lang.String", "instances": 15400, "bytes": 12582912}
  ]
}
```

### 3. Error bodies and reason strings
- Single-flight conflict (capture or analyze already in progress):
  - Status: `409 Conflict`
  - Body: `ActionBusyResult {"error":"sharpit action already in progress","operation":"heap-dump-capture","activeOperation":"heap-dump-capture","message":"Operation 'heap-dump-capture' cannot start while 'heap-dump-capture' is in progress."}`
- Read-only action blocked:
  - Status: `403 Forbidden`
  - Body: `{"error":"sharpit panel access denied","panel":"heap-dump","reason":"Panel is read-only via bootui.panels.heap-dump.read-only=true"}`
- Validation errors:
  - `IllegalArgumentException("Invalid dump file name")` (path traversal guard) -> 400.
  - `IllegalArgumentException("Dump file not found")` -> 400.
- Report status errors (`capture.status = "ERROR"`):
  - `"Heap dumps are not supported on this JVM"`
  - `"Heap dump capture is disabled via bootui.heap-dump.capture-enabled=false"`
  - `"Not enough free disk space to capture a heap dump safely"`
  - `"Heap dump capture failed: <cause>"`
  - `"Heap analysis failed: <cause>"`

### 4. Panel flags and settings
- Panel ID: `heap-dump`, Title: `"Heap Dump"`, `actionCapable: true`, API prefix: `"/heap-dump"`.
- Properties:
  - `bootui.panels.heap-dump.enabled=true`
  - `bootui.panels.heap-dump.read-only=false`
  - `bootui.heap-dump.capture-enabled=true`
  - `bootui.heap-dump.allow-raw-download=false` (downloads disabled by default because dumps contain unmasked secrets)
  - `bootui.heap-dump.output-dir=.bootui/heap-dumps`
  - `bootui.heap-dump.max-dumps=5` (oldest files evicted beyond this limit)
  - `bootui.heap-dump.max-classes=1000` (max histogram rows kept in memory)
  - `bootui.heap-dump.top-classes=25` (rows returned in topClasses DTO list)

### 5. Side effects
- `GET /heap-dump`: Passive file listing of `output-dir` and read of in-memory histogram state. Does NOT write files, run GC, or mutate state.
- `POST /heap-dump/capture`: **Writes a binary file to disk** in `output-dir`, invokes `HotSpotDiagnosticMXBean.dumpHeap()`, triggers full GC, and refreshes the histogram.
- `POST /heap-dump/analyze`: Triggers full GC via HotSpot `GC.class_histogram` diagnostic command; mutates in-memory histogram state, does NOT write a file.
- `POST /heap-dump/delete`: Deletes a `.hprof` file from disk.
- `GET /heap-dump/download`: Reads and streams the raw dump file.

### 6. Streams
None.

### 7. MCP tools and CLI commands
- MCP Tools:
  - `get_heap_dump_report` (schema: NONE, action: `false`)
  - `analyze_heap_dump` (schema: NONE, action: `true`)
  - (Note: `capture` is intentionally NOT exposed to MCP to prevent agents from filling disk or triggering full GC pauses).
- CLI:
  - `bootui memory heap report`
  - `bootui memory heap analyze`

### 8. Advisor rules
None.

### 9. UI
- View: `bootui-ui/.../views/HeapDump.vue`, `HeapDump.test.js`.
- Components: `PanelHeader.vue`, `PanelSkeleton.vue`, `SpinnerButton.vue`, `ReadOnlyNotice.vue`.
- API calls: `getJson('api/heap-dump?...')`, `postJson('api/heap-dump/analyze')`, `postJson('api/heap-dump/capture?live=...')`, `postJson('api/heap-dump/delete?name=...')`.

### 10. Tests that define behaviour
- Controller: `HeapDumpControllerTests.java`
  - `# ported: HeapDumpControllerTests.reportReturnsCurrentStatus`
  - `# ported: HeapDumpControllerTests.captureDelegatesAndReturnsReport`
  - `# ported: HeapDumpControllerTests.analyzeRunsWithoutWritingFile`
  - `# ported: HeapDumpControllerTests.deleteRemovesFileAndRefreshes`
  - `# ported: HeapDumpControllerTests.downloadRefusedWhenDisabled`
- Engine: `HeapDumpServiceTests.java`
  - `# ported: HeapDumpServiceTests.rejectsInvalidFileNames`
  - `# ported: HeapDumpServiceTests.evictsOldestDumpsBeyondMax`
  - `# ported: HeapDumpServiceTests.refusesCaptureWhenDiskSpaceInsufficient`
  - `# ported: HeapDumpServiceTests.parsesClassHistogramOutputCorrectly`
  - `# ported: HeapDumpServiceTests.smartFilterBigObjectsOrdersByBytesPerInstance`
  - `# ported: HeapDumpServiceTests.smartFilterCollectionBloatFiltersToStandardCollections`

### 11. Python mapping
- Python data source: `tracemalloc.take_snapshot()` and `gc.get_objects()`.
- Python does not produce `.hprof` files; a Python heap dump can serialize `tracemalloc` snapshots or use `objgraph`.
- In sharpit: `POST /heap-dump/analyze` maps to `tracemalloc.get_traced_memory()` and top stats by class/file in memory.
- Proposed gatekeeper: `src/sharpit/engine/tracemalloc.py`.

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: HotSpot MXBeans and `.hprof` format are HotSpot-specific.
- [AMBIG]: Decide whether sharpit should ever write a memory dump to disk on Python (`tracemalloc.Snapshot.dump()`), or remain strictly in-memory (`analyze`-only) to honor sharpit's zero-file-write default.

### 13. Size estimate
- **M (≤ 1 day)**: Histogram generation and smart filters port quickly using `tracemalloc.Statistic` groupings.

---

## 5. Startup (Startup Timeline)

Backing panel id: `startup`. Read-only panel displaying the hierarchical application startup steps and durations.

### 1. Endpoints
- `GET /bootui/api/startup`:
  - Query parameters / request body: None.
  - Returns `StartupReport`.

### 2. Response DTOs
Source paths:
- `StartupReport.java` (`bootui-engine/.../core/dto/StartupReport.java`):
  - `steps`: `StartupStepDto[]`
- `StartupStepDto.java` (`bootui-engine/.../core/dto/StartupStepDto.java`):
  - `id`: long
  - `parentId`: Long|null
  - `name`: string
  - `durationMs`: long
  - `tags`: `TagDto[]` (`key`: string, `value`: string)

JSON Example (`GET /bootui/api/startup`):
```json
{
  "steps": [
    {
      "id": 1,
      "parentId": null,
      "name": "spring.boot.application.starting",
      "durationMs": 45,
      "tags": [{"key": "mainApplicationClass", "value": "com.acme.OrderApplication"}]
    },
    {
      "id": 2,
      "parentId": 1,
      "name": "spring.boot.application.environment-prepared",
      "durationMs": 120,
      "tags": []
    }
  ]
}
```

### 3. Error bodies and reason strings
- Panel disabled: `403 {"error":"sharpit panel access denied","panel":"startup","reason":"Panel is disabled via bootui.panels.startup.enabled=false"}`.
- If Actuator startup endpoint is absent, returns empty report `{"steps": []}` with status `200 OK`.

### 4. Panel flags and settings
- Panel ID: `startup`, Title: `"Startup Timeline"`, `actionCapable: false`, API prefix: `"/startup"`.
- Properties:
  - `bootui.panels.startup.enabled=true`
  - `bootui.startup.enabled=true` (auto-installs `BufferingApplicationStartup` in Spring Boot)
  - `bootui.startup.capacity=4096` (buffer size for startup events; `<= 0` disables buffer)

### 5. Side effects
- Reads in-memory startup event buffer. No socket, file, DB, or logger changes.

### 6. Streams
None.

### 7. MCP tools and CLI commands
- MCP Tool: `get_startup_timeline`
  - Schema: `QUERY_LIMIT` (`query` string, `limit` int, compacted default `25`).
  - Action: `false` (read-only).
  - Output: `{"steps": StartupStepDto[], "page": PageMetadata}` (sorted by duration descending, then id).
- CLI:
  - `bootui startup` (`--query <q>`, `--limit <n>`)

### 8. Advisor rules
None.

### 9. UI
- View: `bootui-ui/.../views/Startup.vue`, `Startup.test.js`.
- Components: `PanelHeader.vue`, `PanelSkeleton.vue`.
- API calls: `apiFetch('api/startup')`.

### 10. Tests that define behaviour
- Controller: `StartupControllerTests.java`
  - `# ported: StartupControllerTests.startupReturnsEmptyWhenActuatorUnavailable`
  - `# ported: StartupControllerTests.startupReturnsEmptyWhenTimelineIsNull`
  - `# ported: StartupControllerTests.startupReturnsStepsFromTimeline`
  - `# ported: StartupControllerTests.startupFiltersBootUiStepsByDefault`
  - `# ported: StartupControllerTests.startupHandlesZeroDurationWhenDurationIsNull`
- Post-processor: `BootUiStartupEnvironmentPostProcessorTests.java`
  - `# ported: BootUiStartupEnvironmentPostProcessorTests.installsBufferingStartupWhenBootUiIsEnabled`
  - `# ported: BootUiStartupEnvironmentPostProcessorTests.doesNotInstallWhenCapacityIsNotPositive`

### 11. Python mapping
- Python data source: Application factory execution time, lifespan startup handlers (`@asynccontextmanager lifespan(app)`), and module import times (`python -X importtime`).
- Optional dependency: None (stdlib `time.perf_counter()`).
- Proposed gatekeeper: None required.

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: Spring `BufferingApplicationStartup` and `StartupTimeline` event interfaces drop.
- [AMBIG]: In FastAPI/Starlette, define standard phases: `router_include`, `middleware_init`, `lifespan_startup`, `db_connect`.

### 13. Size estimate
- **S (≤ half a day)**: Step recording during lifespan context manager is lightweight and needs only a tiny recorder.

---

## 6. REST Client Trace

Backing panel id: `rest-client-trace`. Captures outbound HTTP client calls from Spring's `RestClient`, `RestTemplate`, and `WebClient`, detecting chatty (N+1) outbound requests and slow dependencies.

### 1. Endpoints
- `GET /bootui/api/rest-client-trace`:
  - Query parameters / request body: None.
  - Returns `RestClientTraceReport`.
- `POST /bootui/api/rest-client-trace/clear`:
  - Action: Empties the in-memory trace buffer.
  - Query parameters / request body: None.
  - Returns `RestClientTraceReport`.
- `POST /bootui/api/rest-client-trace/recording`:
  - Action: Pauses or resumes outbound call capture.
  - Request body: `RestClientTraceRecordingRequest` (`{"enabled": boolean|null}`). If null/omitted, toggles current state.
  - Returns `RestClientTraceReport`.
- `GET /bootui/api/rest-client-trace/stream`:
  - SSE endpoint (`text/event-stream`).
  - Emits coalesced `event: update` on new call capture, clear, or pause/resume.

### 2. Response DTOs
Source paths:
- `RestClientTraceReport.java` (`bootui-engine/.../core/dto/RestClientTraceReport.java`):
  - `available`: boolean
  - `unavailableReason`: string|null
  - `capturing`: boolean
  - `captureHeaders`: boolean
  - `bufferSize`: int
  - `totalCaptured`: long
  - `slowCallThresholdMillis`: long
  - `clientTypes`: `string[]` (e.g. `["RestClient", "WebClient"]`)
  - `stats`: `RestClientTraceStatsDto`
  - `entries`: `RestClientTraceEntryDto[]` (newest first)
  - `topCalls`: `RestClientTraceGroupDto[]` (grouped by method + host + normalized path)
  - `warnings`: `string[]`
  - `retention`: `CaptureRetentionDto|null`
- `RestClientTraceEntryDto.java` (`bootui-engine/.../core/dto/RestClientTraceEntryDto.java`):
  - `id`: long
  - `timestamp`: long (epoch ms)
  - `method`: string (`"GET"`, `"POST"`, etc.)
  - `uri`: string (query values masked per exposure policy)
  - `host`: string
  - `path`: string (path without query)
  - `status`: Integer|null (HTTP status code, null on client failure)
  - `durationMillis`: long
  - `success`: boolean (false on connection timeout/failure)
  - `errorMessage`: string|null
  - `slow`: boolean
  - `clientType`: string (`"RestClient"|"RestTemplate"|"WebClient"`)
  - `requestHeaders`: `Map<string, string>` (masked per policy; empty if header capture disabled)
  - `traceId`: string|null
  - `thread`: string
  - `callSite`: string|null (e.g. `"OrderClient.java:42"`)
  - `requestId`: string|null
  - `executionId`: string|null
  - `threadKind`: string|null
- Supporting DTOs:
  - `RestClientTraceGroupDto` (`method`: string, `host`: string, `path`: string, `executions`: long, `totalDurationMillis`: long, `maxDurationMillis`: long, `chatty`: boolean, `callSites`: string[])
  - `RestClientTraceStatsDto` (`totalCalls`: long, `totalDurationMillis`: long, `maxDurationMillis`: long, `avgDurationMillis`: double, `slowCalls`: long, `failedCalls`: long, `errorStatusCalls`: long, `getCount`: long, `postCount`: long, `putCount`: long, `deleteCount`: long, `otherCount`: long, `evicted`: long)

JSON Example (`GET /bootui/api/rest-client-trace`):
```json
{
  "available": true,
  "unavailableReason": null,
  "capturing": true,
  "captureHeaders": false,
  "bufferSize": 200,
  "totalCaptured": 1,
  "slowCallThresholdMillis": 1000,
  "clientTypes": ["httpx"],
  "stats": {
    "totalCalls": 1,
    "totalDurationMillis": 45,
    "maxDurationMillis": 45,
    "avgDurationMillis": 45.0,
    "slowCalls": 0,
    "failedCalls": 0,
    "errorStatusCalls": 0,
    "getCount": 1,
    "postCount": 0,
    "putCount": 0,
    "deleteCount": 0,
    "otherCount": 0,
    "evicted": 0
  },
  "entries": [
    {
      "id": 1,
      "timestamp": 1730487960000,
      "method": "GET",
      "uri": "https://api.stripe.com/v1/charges?customer=******",
      "host": "api.stripe.com",
      "path": "/v1/charges",
      "status": 200,
      "durationMillis": 45,
      "success": true,
      "errorMessage": null,
      "slow": false,
      "clientType": "httpx",
      "requestHeaders": {},
      "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
      "thread": "asyncio_0",
      "callSite": "billing.py:54",
      "requestId": "req_01",
      "executionId": null,
      "threadKind": "async"
    }
  ],
  "topCalls": [
    {
      "method": "GET",
      "host": "api.stripe.com",
      "path": "/v1/charges",
      "executions": 1,
      "totalDurationMillis": 45,
      "maxDurationMillis": 45,
      "chatty": false,
      "callSites": ["billing.py:54"]
    }
  ],
  "warnings": [],
  "retention": null
}
```

### 3. Error bodies and reason strings
- Gated read-only on clear/recording: `403 {"error":"sharpit panel access denied","panel":"rest-client-trace","reason":"Panel is read-only via bootui.panels.rest-client-trace.read-only=true"}`.
- Unavailable reasons emitted in DTO when client is not instrumented:
  - `"REST client tracing is not configured"`
  - `"REST client tracing is disabled (set bootui.rest-client-trace.enabled=true in a trusted local profile)."`
  - `"No RestClient, RestTemplate, or WebClient has been instrumented yet."`

### 4. Panel flags and settings
- Panel ID: `rest-client-trace`, Title: `"REST Client"`, `actionCapable: true`, API prefix: `"/rest-client-trace"`.
- Properties:
  - `bootui.panels.rest-client-trace.enabled=true`
  - `bootui.panels.rest-client-trace.read-only=false`
  - `bootui.rest-client-trace.enabled=true`
  - `bootui.rest-client-trace.recording=true`
  - `bootui.rest-client-trace.capture-headers=false`
  - `bootui.rest-client-trace.capture-call-site=true`
  - `bootui.rest-client-trace.max-entries=200`
  - `bootui.rest-client-trace.slow-call-threshold-millis=1000`
  - `bootui.rest-client-trace.reserved-share-percent=25` (25% reserved for failed/slow calls)
  - `bootui.rest-client-trace.max-uri-length=2000`
  - `bootui.rest-client-trace.max-header-value-length=200`
  - `bootui.rest-client-trace.chatty-call-threshold=5`

### 5. Side effects
- Passive in-memory read of the ring buffer on GET. Client instrumentation is attached at startup or client creation; no network or socket side effect occurs during report assembly.
- Sensitive query parameters and headers are masked before return.

### 6. Streams
- Endpoint: `GET /bootui/api/rest-client-trace/stream` (`text/event-stream`).
- Event name: `update`. Empty payload (notification only). Closes when application context closes.

### 7. MCP tools and CLI commands
- MCP Tools:
  - `get_rest_client_traces` (schema: QUERY_LIMIT, action: `false`)
  - `clear_rest_client_traces` (schema: NONE, action: `true`)
  - `pause_rest_client_recording` (schema: NONE, action: `true`)
  - `resume_rest_client_recording` (schema: NONE, action: `true`)
- CLI:
  - `bootui rest-client traces` (`--query`, `--limit`)
  - `bootui rest-client clear`
  - `bootui rest-client pause`
  - `bootui rest-client resume`

### 8. Advisor rules
None.

### 9. UI
- View: `bootui-ui/.../views/RestClientTrace.vue`, `RestClientTrace.test.js`.
- Components: `PanelHeader.vue`, `CaptureRetention.vue`, `LowFootprintBanner.vue`, `SpinnerButton.vue`.
- Composables: `useEventStreamRefresh.js`, `useConfirm.js`.
- API calls: `getJson('api/rest-client-trace')`, `postJson('api/rest-client-trace/clear')`, `postJson('api/rest-client-trace/recording', {enabled})`, SSE `/stream`.

### 10. Tests that define behaviour
- Controller: `RestClientTraceControllerTests.java`
  - `# ported: RestClientTraceControllerTests.reportsUnavailableWhenNoRecorderConfigured`
  - `# ported: RestClientTraceControllerTests.reportsDisabledReasonWhenTracingOff`
  - `# ported: RestClientTraceControllerTests.reportsCapturedCalls`
  - `# ported: RestClientTraceControllerTests.reportsSlowCallsAndFailuresInStats`
  - `# ported: RestClientTraceControllerTests.capturesRequestHeadersWhenEnabled`
  - `# ported: RestClientTraceControllerTests.clearEmptiesTheBuffer`
  - `# ported: RestClientTraceControllerTests.recordingTogglePausesAndResumes`
- Engine: `RestClientTraceRecorderTests.java`
  - `# ported: RestClientTraceRecorderTests.floodOfSuccessfulCallsKeepsRecentFailedErrorAndSlowCallsUpToTheReservedShare`
  - `# ported: RestClientTraceRecorderTests.groupsRepeatedCallsViaTopCalls`
  - `# ported: RestClientTraceRecorderTests.selectCallSiteFindsFirstApplicationFrame`
  - `# ported: RestClientTraceRecorderTests.maskedReportHidesSecretHeaderAndQueryParameterValuesByName`
  - `# ported: RestClientTraceRecorderTests.removesUriUserInfoCredentialsBeforeTheyAreBuffered`

### 11. Python mapping
- Python source: `httpx` event hooks (`event_hooks={"request": [...], "response": [...]}`) or custom `httpx.BaseTransport`, and `requests.adapters.HTTPAdapter` or `urllib3.connectionpool`.
- Optional dependencies: `httpx`, `requests`.
- Proposed gatekeeper modules:
  - `src/sharpit/engine/httpx.py`
  - `src/sharpit/engine/requests.py`

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: Spring `ClientHttpRequestInterceptor` and WebClient `ExchangeFilterFunction` drop.
- [AMBIG]: Python apps often construct one-off `httpx.AsyncClient()` or `requests.get()` instances without dependency injection. A global transport hook or patching `httpx.Client.__init__` vs an explicit client wrapper must be decided.

### 13. Size estimate
- **M (≤ 1 day)**: The in-memory buffer, group aggregation, and secret masking mirror SQL trace; writing the `httpx` transport/event hook is moderate work.

---

## 7. AI (AI Framework)

Backing panel id: `ai`. Read-only panel aggregating GenAI chat completions, token usage time-series, tool calls, and vector store operations from OpenTelemetry GenAI spans.

### 1. Endpoints
- `GET /bootui/api/ai/overview`:
  - Query parameters / request body: None.
  - Returns `AiOverviewDto`.
- `GET /bootui/api/ai/chats`:
  - Query parameters:
    - `limit` (int, optional, default `100`, clamped to `maxRecentChats`).
  - Request body: None.
  - Returns `AiChatSummaryDto[]` (most recent first).
- `GET /bootui/api/ai/chats/{spanId}`:
  - Path variable: `spanId` (string, required).
  - Query parameters / request body: None.
  - Returns `AiChatDetailDto`.
  - Status `404 Not Found` if spanId not found.
- `GET /bootui/api/ai/tokens`:
  - Query parameters:
    - `minutes` (int, optional, default `tokenSeriesMinutes` = `60`, clamped `1..1440`).
  - Request body: None.
  - Returns `AiTokenSeriesDto`.

### 2. Response DTOs
Source paths:
- `AiOverviewDto.java` (`bootui-engine/.../core/dto/AiOverviewDto.java`):
  - `enabled`: boolean
  - `springAiDetected`: boolean
  - `langChain4jDetected`: boolean
  - `aiFrameworkDetected`: boolean
  - `totalChats`: int
  - `totalInputTokens`: long
  - `totalOutputTokens`: long
  - `tokensByModel`: `Map<string, Long>`
  - `callsByModel`: `Map<string, Integer>`
  - `errorCount`: int
  - `averageDurationNanos`: long (nanoseconds)
  - `toolCallCount`: int
  - `vectorOperationCount`: int
  - `embeddingCount`: int
  - `recent`: `AiChatSummaryDto[]`
  - `contentBanner`: string|null
- `AiChatSummaryDto.java` (`bootui-engine/.../core/dto/AiChatSummaryDto.java`):
  - `traceId`: string
  - `spanId`: string
  - `startEpochNanos`: long (epoch nanoseconds)
  - `durationNanos`: long (nanoseconds)
  - `provider`: string (e.g. `"openai"`, `"anthropic"`)
  - `requestModel`: string
  - `responseModel`: string|null
  - `inputTokens`: Long|null
  - `outputTokens`: Long|null
  - `totalTokens`: Long|null
  - `finishReason`: string|null
  - `statusCode`: string (`"OK"|"ERROR"|"UNSET"`)
  - `operation`: string (`"chat"|"generate"`)
  - `toolCallCount`: int
  - `vectorOperationCount`: int
- `AiChatDetailDto.java` (`bootui-engine/.../core/dto/AiChatDetailDto.java`):
  - `summary`: `AiChatSummaryDto`
  - `toolCalls`: `AiToolCallDto[]` (tool calls linked to the same trace)
  - `vectorOperations`: `AiVectorOpDto[]` (vector ops linked to the same trace)
  - `attributes`: `SpanAttributeDto[]` (masked span attributes)
  - `events`: `SpanEventDto[]` (span events)
  - `contentCaptured`: boolean
  - `contentBanner`: string|null
- Supporting DTOs:
  - `AiTokenSeriesDto` (`minutes`: int, `buckets`: `AiTokenBucketDto[]`)
  - `AiTokenBucketDto` (`epochMinute`: long, `inputTokens`: long, `outputTokens`: long, `callCount`: int)
  - `AiToolCallDto` (`spanId`: string, `name`: string, `startEpochNanos`: long, `durationNanos`: long, `statusCode`: string)
  - `AiVectorOpDto` (`spanId`: string, `operation`: string, `collectionName`: string, `startEpochNanos`: long, `durationNanos`: long, `statusCode`: string)

JSON Example (`GET /bootui/api/ai/overview`):
```json
{
  "enabled": true,
  "springAiDetected": false,
  "langChain4jDetected": false,
  "aiFrameworkDetected": true,
  "totalChats": 12,
  "totalInputTokens": 4520,
  "totalOutputTokens": 1890,
  "tokensByModel": {"gpt-4o": 4100, "claude-3-5-sonnet": 2310},
  "callsByModel": {"gpt-4o": 8, "claude-3-5-sonnet": 4},
  "errorCount": 0,
  "averageDurationNanos": 850000000,
  "toolCallCount": 3,
  "vectorOperationCount": 2,
  "embeddingCount": 2,
  "recent": [
    {
      "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
      "spanId": "00f067aa0ba902b7",
      "startEpochNanos": 1730487960000000000,
      "durationNanos": 750000000,
      "provider": "anthropic",
      "requestModel": "claude-3-5-sonnet",
      "responseModel": "claude-3-5-sonnet-20241022",
      "inputTokens": 1024,
      "outputTokens": 256,
      "totalTokens": 1280,
      "finishReason": "end_turn",
      "statusCode": "OK",
      "operation": "chat",
      "toolCallCount": 1,
      "vectorOperationCount": 0
    }
  ],
  "contentBanner": "Prompt and completion content capture is disabled by default for privacy."
}
```

### 3. Error bodies and reason strings
- Chat detail missing:
  - Status: `404 Not Found`
  - Body: `ResponseStatusException(404, "chat span <spanId> not found")`
- Panel disabled: `403 {"error":"sharpit panel access denied","panel":"ai","reason":"Panel is disabled via bootui.panels.ai.enabled=false"}`.

### 4. Panel flags and settings
- Panel ID: `ai`, Title: `"AI Framework"`, `actionCapable: false`, API prefix: `"/ai"`.
- Properties:
  - `bootui.panels.ai.enabled=true`
  - `bootui.ai.token-series-minutes=60`
  - `bootui.ai.max-recent-chats=100`
  - `bootui.ai.show-content-capture-banner=true`
  - `bootui.telemetry.enabled=true` (controls underlying span ingestion)

### 5. Side effects
- Reads in-memory OpenTelemetry GenAI spans from `TelemetryStore`. No socket, file, DB, or logger changes.

### 6. Streams
None.

### 7. MCP tools and CLI commands
- MCP Tool: `get_ai_overview`
  - Schema: NONE.
  - Action: `false` (read-only).
  - Output: `AiOverviewDto`.
- CLI:
  - `bootui ai overview`

### 8. Advisor rules
None.

### 9. UI
- View: `bootui-ui/.../views/Ai.vue`, `Ai.test.js`.
- Components: `AiSetupChecklist.vue`, `LowFootprintBanner.vue`, `PanelHeader.vue`, `ProgressBar.vue`.
- Composables: `useAutoRefresh.js`, `useDataState.js`, `useLowFootprint.js`.
- API calls: `apiFetch('api/ai/overview')`, `apiFetch('api/ai/tokens?minutes=...')`, `getJson('api/ai/chats/<spanId>')`.

### 10. Tests that define behaviour
- Controller: `AiControllerTests.java`
  - `# ported: AiControllerTests.overviewAggregatesChatToolAndVectorSpans`
  - `# ported: AiControllerTests.overviewReportsDisabledTelemetry`
  - `# ported: AiControllerTests.chatsRespectLimitAndAreOrderedMostRecentFirst`
  - `# ported: AiControllerTests.chatDetailReturnsLinkedToolsAndVectorOperations`
  - `# ported: AiControllerTests.chatDetailFollowsTheLiveValueExposurePolicy`
  - `# ported: AiControllerTests.chatDetailReturnsNotFoundForUnknownSpan`
  - `# ported: AiControllerTests.tokensReturnsRequestedWindowAndBucketsTheChat`
  - `# ported: AiControllerTests.chatsClampLimitToConfiguredMaximum`

### 11. Python mapping
- Python data source: OpenTelemetry GenAI spans (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`), or hooks in OpenAI / Anthropic Python SDKs or LiteLLM.
- Optional dependency: `opentelemetry-sdk` or `httpx`.
- Proposed gatekeeper: `src/sharpit/engine/otel.py`.

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: Detection of Spring AI and LangChain4j class presence drops.
- [AMBIG]: In Python, detect `openai`, `anthropic`, `litellm`, or `langchain` packages in `importlib.metadata.distributions()`.

### 13. Size estimate
- **M (≤ 1 day)**: Once OpenTelemetry span ingestion exists (`engine/otel.py`), grouping chat spans, bucketizing tokens, and linking trace tool calls is straightforward.

---

## 8. Bean-Graph Mode (Beans)

Backing panel id: `beans`. Interactive graph visualization of application component dependency neighbourhoods, cycles, and condition metadata.

### 1. Endpoints
Bean-graph mode does **not** introduce a separate backend endpoint; it is a rich client-side visualization mode built on the standard Beans and Conditions endpoints:
- `GET /bootui/api/beans?q=&classification=&offset=&limit=`:
  - Query parameters:
    - `q` (string, optional): filter by name or type.
    - `classification` (string, optional): `"APPLICATION"` or `"FRAMEWORK"`.
    - `offset` (int, default `0`).
    - `limit` (int, default `200`, max `1000`).
  - Request body: None.
  - Returns `BeanList` (`{total: int, beans: BeanSummary[], page: PageMetadata}`).
  - Graph mode loads beans with `offset=0` and `limit=1000` (paginating up to `MAX_GRAPH_LOAD = 2000`).
- `GET /bootui/api/conditions`:
  - Returns `ConditionsReport`. Graph mode calls this to display matching auto-configuration conditions for the focused bean.

### 2. Response DTOs
Source paths:
- `BeanList.java` (`bootui-engine/.../core/dto/BeanList.java`):
  - `total`: int
  - `beans`: `BeanSummary[]`
  - `page`: `PageMetadata`
- `BeanSummary.java` (`bootui-engine/.../core/dto/BeanSummary.java`):
  - `name`: string
  - `type`: string
  - `scope`: string (e.g. `"singleton"`)
  - `resource`: string|null (e.g. `"class path resource [com/acme/OrderConfig.class]"`)
  - `dependencies`: `string[]` (list of bean names this bean depends on; **the graph edges**)
  - `aliases`: `string[]`
  - `classification`: string (`"APPLICATION"` or `"FRAMEWORK"`)

JSON Example:
```json
{
  "total": 2,
  "beans": [
    {
      "name": "orderService",
      "type": "com.acme.OrderService",
      "scope": "singleton",
      "resource": "class path resource [com/acme/OrderConfig.class]",
      "dependencies": ["orderRepository", "paymentClient"],
      "aliases": [],
      "classification": "APPLICATION"
    },
    {
      "name": "orderRepository",
      "type": "com.acme.OrderRepository",
      "scope": "singleton",
      "resource": null,
      "dependencies": ["dataSource"],
      "aliases": [],
      "classification": "APPLICATION"
    }
  ],
  "page": {"total": 2, "matched": 2, "offset": 0, "limit": 1000, "returned": 2, "hasMore": false}
}
```

Client Graph Model (`useBeanGraph.js`):
- `nodes`: `{id: string, name: string, type: string, classification: string, role: string, depth: int}[]`
  - `role` enum: `"focus"` (selected node), `"dep"` (direct dependency), `"rdep"` (direct dependent), `"deep"` (2nd/3rd hop), `"both"` (mutual dependency).
- `edges`: `{id: string, source: string, target: string, direction: string}[]`
- Client constants and clamps:
  - `MAX_GRAPH_LOAD = 2000` (max beans fetched before marking inventory truncated)
  - `GRAPH_LOAD_PAGE_SIZE = 1000` (page fetch batch)
  - `MAX_GRAPH_NODES = 60` (neighborhood render limit)
  - `MAX_GRAPH_DEPTH = 3` (BFS hop limit from focus node)
  - `MAX_BEAN_CONDITIONS = 20` (condition rows linked)

### 3. Error bodies and reason strings
- Shared panel gating: `403 {"error":"sharpit panel access denied","panel":"beans","reason":"Panel is disabled via bootui.panels.beans.enabled=false"}`.

### 4. Panel flags and settings
- Panel ID: `beans`, Title: `"Beans"`, `actionCapable: false`, API prefix: `"/beans"`.
- Properties:
  - `bootui.panels.beans.enabled=true`
  - No `bootui.beans.*` settings in `BootUiProperties.java`.

### 5. Side effects
- Passive reflection on Spring `ApplicationContext` or framework DI container. No socket, file, DB, or logger changes.

### 6. Streams
None.

### 7. MCP tools and CLI commands
- MCP Tool: `get_beans` (schema: QUERY_LIMIT, action: `false`).
- CLI: `bootui beans` (`--query`, `--limit`).

### 8. Advisor rules
None.

### 9. UI
- Views: `bootui-ui/.../views/Beans.vue`, `BeansGraphMode.vue`, `BeanGraph.vue`.
- Composables: `useBeanGraph.js` (BFS neighborhood calculation, cycle detection, automatic focus selection via `mostConnectedApplicationBeanName`).
- API calls: `apiFetch('api/beans?offset=...&limit=1000')`, `apiFetch('api/conditions')`.

### 10. Tests that define behaviour
- Frontend graph logic: `bootui-ui/src/main/frontend/src/utils/useBeanGraph.test.js`
  - `selects the Application bean with the most direct relationships`
  - `counts incoming relationships`
  - `breaks equal relationship counts alphabetically`
  - `builds a byName map from all beans`
  - `builds a reverse index from dependencies`
  - `merges duplicate bean names deterministically without losing dependencies`
  - `assigns role 'focus' to the focus node`
  - `includes direct dependencies with role 'dep'`
  - `includes direct dependents with role 'rdep'`
  - `assigns role 'both' when focus is a direct mutual dependency`
  - `does not infinite-loop on a direct cycle`
  - `does not duplicate nodes on a diamond dependency`
  - `does not traverse beyond maxDepth`
  - `never exceeds maxNodes in the returned list`
  - `paginates through the backend 1 000-row cap up to the graph inventory bound`
- Backend: `bootui-spring-boot-starter/.../autoconfigure/web/BeansControllerTests.java`.

### 11. Python mapping
- Python source: FastAPI `route.dependant` tree (extract dependencies declared in `Depends(...)`), FastAPI `app.dependency_overrides`, or DI framework containers (e.g. `dependency-injector`, `dishka`).
- Optional dependency: None.
- Proposed gatekeeper: `src/sharpit/fastapi/dependencies.py`.

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: Spring `ApplicationContext` bean definitions and Actuator JSON model drop.
- [AMBIG]: In FastAPI, dependency nodes are callable functions (`def get_db()`, `def get_current_user()`) rather than named singleton classes. Name them by `<module>.<function>` and classify application vs framework code based on `sys.modules`.

### 13. Size estimate
- **S (≤ half a day)**: The Vue graph visualization runs entirely client-side using `BeanSummary.dependencies`. If the backend returns `dependencies: string[]` in each bean summary, the UI graph mode works immediately.

---

## 9. Live Flow Mode (Live Activity)

Backing panel id: `activity`. Renders an animated, topology-mapped service map (`ServiceMapReport`) showing inbound lanes and outbound dependency interactions (HTTP, JDBC, Kafka, RabbitMQ, Cache) without new probes.

### 1. Endpoints
- `GET /bootui/api/activity/service-map`:
  - Served under `/activity` because Live Flow is a view mode of Live Activity.
  - Query parameters / request body: None.
  - Returns `ServiceMapReport`.

### 2. Response DTOs
Source paths:
- `ServiceMapReport.java` (`bootui-engine/.../core/dto/ServiceMapReport.java`):
  - `available`: boolean
  - `unavailableReason`: string|null
  - `generatedAt`: long (epoch ms)
  - `application`: `ServiceMapNodeDto|null` (the center application node)
  - `nodes`: `ServiceMapNodeDto[]` (inbound lane and outbound dependency nodes)
  - `edges`: `ServiceMapEdgeDto[]` (relationships anchored on application)
  - `truncation`: `ServiceMapTruncationDto`
  - `sources`: `string[]` (labels of contributing panels, e.g. `["HTTP Exchanges", "SQL Trace"]`)
  - `warnings`: `string[]`
- `ServiceMapNodeDto.java` (`bootui-engine/.../core/dto/ServiceMapNodeDto.java`):
  - `id`: string (e.g. `"application"`, `"inbound:http"`, `"http:https://api.stripe.com"`, `"jdbc:order-ds"`)
  - `kind`: string (`"APPLICATION"|"INBOUND"|"DEPENDENCY"`)
  - `protocol`: string (`"APPLICATION"|"HTTP_INBOUND"|"HTTP"|"JDBC"|"KAFKA"|"RABBITMQ"|"CACHE"`)
  - `label`: string
  - `detail`: string|null
  - `configured`: boolean (declared in config)
  - `observed`: boolean (observed in retained traffic)
  - `interactions`: int
  - `failures`: int
  - `distinctOperations`: Integer|null
  - `lastSeen`: Long|null (epoch ms)
  - `outcome`: string (`"NO_EVIDENCE"|"OBSERVED_OK"|"RETAINED_FAILURES"`)
  - `sourcePanelId`: string|null (e.g. `"rest-client-trace"`)
  - `sourceRoute`: string|null (e.g. `"/rest-client-trace"`)
  - `sourceLabel`: string|null (e.g. `"REST Client"`)
  - `note`: string|null
- `ServiceMapEdgeDto.java` (`bootui-engine/.../core/dto/ServiceMapEdgeDto.java`):
  - `id`: string (`"<fromId>-><toId>"`)
  - `fromId`: string
  - `toId`: string
  - `protocol`: string
  - `direction`: string (`"INBOUND"|"OUTBOUND"`)
  - `interactions`: int
  - `failures`: int
  - `lastSeen`: Long|null (epoch ms)
  - `outcome`: string (`"NO_EVIDENCE"|"OBSERVED_OK"|"RETAINED_FAILURES"`)
  - `recentInteractions`: `ServiceMapInteractionDto[]` (tail of up to 6 completed events)
- Supporting DTOs:
  - `ServiceMapInteractionDto` (`id`: string [`"<protocol>:<seq>"`], `timestamp`: long [epoch ms], `operation`: string [`"GET"|"POST"|"SELECT"|"UPDATE"|"GET"|"PUT"|"PUBLISH"`], `outcome`: string [`"OK"|"FAILED"`], `durationMs`: Long|null, `flowId`: string|null)
  - `ServiceMapTruncationDto` (`truncated`: boolean, `dependencyLimit`: int [28], `dependenciesShown`: int, `dependenciesOmitted`: int, `interactionLimit`: int [6])

JSON Example (`GET /bootui/api/activity/service-map`):
```json
{
  "available": true,
  "unavailableReason": null,
  "generatedAt": 1730487960000,
  "application": {
    "id": "application",
    "kind": "APPLICATION",
    "protocol": "APPLICATION",
    "label": "order-service",
    "detail": "FastAPI 0.115.0",
    "configured": true,
    "observed": true,
    "interactions": 10,
    "failures": 0,
    "distinctOperations": null,
    "lastSeen": 1730487959000,
    "outcome": "OBSERVED_OK",
    "sourcePanelId": null,
    "sourceRoute": null,
    "sourceLabel": null,
    "note": null
  },
  "nodes": [
    {
      "id": "inbound:http",
      "kind": "INBOUND",
      "protocol": "HTTP_INBOUND",
      "label": "HTTP Clients",
      "detail": null,
      "configured": false,
      "observed": true,
      "interactions": 6,
      "failures": 0,
      "distinctOperations": 2,
      "lastSeen": 1730487959000,
      "outcome": "OBSERVED_OK",
      "sourcePanelId": "http-exchanges",
      "sourceRoute": "/http-exchanges",
      "sourceLabel": "HTTP Exchanges",
      "note": null
    },
    {
      "id": "http:https://api.stripe.com",
      "kind": "DEPENDENCY",
      "protocol": "HTTP",
      "label": "api.stripe.com",
      "detail": "https://api.stripe.com",
      "configured": false,
      "observed": true,
      "interactions": 4,
      "failures": 0,
      "distinctOperations": 1,
      "lastSeen": 1730487958000,
      "outcome": "OBSERVED_OK",
      "sourcePanelId": "rest-client-trace",
      "sourceRoute": "/rest-client-trace",
      "sourceLabel": "REST Client",
      "note": null
    }
  ],
  "edges": [
    {
      "id": "inbound:http->application",
      "fromId": "inbound:http",
      "toId": "application",
      "protocol": "HTTP_INBOUND",
      "direction": "INBOUND",
      "interactions": 6,
      "failures": 0,
      "lastSeen": 1730487959000,
      "outcome": "OBSERVED_OK",
      "recentInteractions": [
        {"id": "HTTP_INBOUND:6", "timestamp": 1730487959000, "operation": "POST", "outcome": "OK", "durationMs": 15, "flowId": "flow-8a9f"}
      ]
    },
    {
      "id": "application->http:https://api.stripe.com",
      "fromId": "application",
      "toId": "http:https://api.stripe.com",
      "protocol": "HTTP",
      "direction": "OUTBOUND",
      "interactions": 4,
      "failures": 0,
      "lastSeen": 1730487958000,
      "outcome": "OBSERVED_OK",
      "recentInteractions": [
        {"id": "HTTP:4", "timestamp": 1730487958000, "operation": "POST", "outcome": "OK", "durationMs": 42, "flowId": "flow-8a9f"}
      ]
    }
  ],
  "truncation": {
    "truncated": false,
    "dependencyLimit": 28,
    "dependenciesShown": 1,
    "dependenciesOmitted": 0,
    "interactionLimit": 6
  },
  "sources": ["HTTP Exchanges", "REST Client"],
  "warnings": []
}
```

### 3. Error bodies and reason strings
- Gated panel error: `403 {"error":"sharpit panel access denied","panel":"activity","reason":"Panel is disabled via bootui.panels.activity.enabled=false"}`.
- If no sources contribute: returns `200 OK` with `available: false` and `unavailableReason: "No inbound traffic or outbound dependencies have been observed yet."`

### 4. Panel flags and settings
- Governed by the `activity` panel:
  - `bootui.panels.activity.enabled=true`
  - `bootui.panels.activity.read-only=false`
- Hard engine bounds (`ServiceMapLimits.java`):
  - `MAX_DEPENDENCIES = 28`
  - `MAX_RECENT_INTERACTIONS = 6`

### 5. Side effects
- Reads existing in-memory ring buffers from other panels (`HttpExchanges`, `RestClientTrace`, `ConnectionPools`, `SqlTrace`, `Cache`).
- Absolutely no socket, network probe, DNS lookup, database query, file write, or logger mutation occurs during assembly.

### 6. Streams
- Reuses parent Live Activity SSE stream `GET /bootui/api/activity/stream`. On receipt of the `update` event, the UI increments `flowRefreshTick` and re-fetches `/activity/service-map`. There is no separate stream endpoint.

### 7. MCP tools and CLI commands
- Aggregated within `get_live_activity` and `bootui activity`.

### 8. Advisor rules
None.

### 9. UI
- View: `bootui-ui/.../views/LiveActivity.vue`, `views/LiveFlowMode.vue`.
- Utils: `utils/serviceMap.js` (SVG layout, pulse animations, causal sequencing with `diffFlowPulses` and `createFlowQueue`).
- API call: `apiFetch('api/activity/service-map')`.

### 10. Tests that define behaviour
- Controller: `bootui-spring-boot-starter/.../autoconfigure/activity/LiveServiceMapServiceTests.java`
  - `# ported: LiveServiceMapServiceTests.mapsOutboundHttpJdbcAndMessagingEvidenceFromLiveRecorders`
  - `# ported: LiveServiceMapServiceTests.anchorsTheInboundLaneOnCompletedIncomingRequests`
  - `# ported: LiveServiceMapServiceTests.omitsAnEvidenceSourceWhoseOwnPanelIsDisabled`
  - `# ported: LiveServiceMapServiceTests.masksJdbcCredentialsAndParametersBeforeTheyReachTheMap`
  - `# ported: LiveServiceMapServiceTests.reportsUnavailableRatherThanAnEmptyMapWhenNoSourceIsPresent`
- Engine: `bootui-engine/.../engine/servicemap/ServiceMapAssemblerTests.java`
  - `# ported: ServiceMapAssemblerTests.centersTheApplicationAndAnchorsEveryEdgeOnIt`
  - `# ported: ServiceMapAssemblerTests.groupsOutboundHttpByOriginAndNeverCarriesPathOrQuery`
  - `# ported: ServiceMapAssemblerTests.capsDependenciesAndReportsTheOmissionVisibly`
  - `# ported: ServiceMapAssemblerTests.capsRetainedInteractionsPerEdgeNewestFirstWithStableIds`
  - `# ported: ServiceMapAssemblerTests.sharesTheSameOpaqueFlowIdAcrossInboundSqlRestAndCacheOnTheSameTrace`
  - `# ported: ServiceMapAssemblerTests.neverExposesTheRawTraceIdAndDifferentTracesProduceDifferentFlowIds`
- Frontend: `bootui-ui/src/main/frontend/src/utils/serviceMap.test.js`.

### 11. Python mapping
- Python source: Aggregation over sharpit's existing in-memory collectors (HTTP activity buffer, SQL trace buffer, REST client trace buffer, cache buffer).
- Optional dependency: None.
- Proposed gatekeeper: `src/sharpit/engine/activity/service_map.py`.

### 12. [JVM] drops and [AMBIG] calls
- [JVM]: Spring/JMS/Kafka template bean discovery drops.
- [AMBIG]: In Python, determine how flow correlation is assigned if OpenTelemetry tracing is absent (e.g. derive `flowId` from Starlette `request.state.request_id` or contextvar).

### 13. Size estimate
- **M (≤ 1 day)**: The assembler logic is pure Python aggregation over existing buffers, and the Vue map animation (`LiveFlowMode.vue`) is already fully built.

---

## 10. Wave C Summary Table

| Panel / Feature | Endpoints | DTO Count | GET Side Effects? | Optional Lib | Gatekeeper Module | Size Estimate |
|---|---:|---:|---|---|---|---|
| **Metrics** | 2 | 9 | No (in-memory `MeterRegistry`) | `prometheus-client` | `src/sharpit/engine/prometheus.py` | M (≤ 1 day) |
| **Memory** (Advisor) | 3 | 8 | No (POST scan reads JMX/cgroup) | `psutil` | `src/sharpit/engine/psutil.py` | L (> 1 day) |
| **Live Memory** | 4 | 9 | No (POST offload frees buffers & GCs) | `psutil` | `src/sharpit/engine/psutil.py` | M (≤ 1 day) |
| **Heap Dump** | 5 | 4 | No (POST capture writes `.hprof`) | stdlib / `tracemalloc` | `src/sharpit/engine/tracemalloc.py` | M (≤ 1 day) |
| **Startup** | 1 | 3 | No (passive in-memory read) | None (stdlib) | None | S (≤ half day) |
| **REST Client Trace** | 4 | 5 | No (reads in-memory ring buffer) | `httpx`, `requests` | `src/sharpit/engine/httpx.py`, `requests.py` | M (≤ 1 day) |
| **AI Framework** | 4 | 7 | No (reads in-memory OTel spans) | `opentelemetry-sdk` | `src/sharpit/engine/otel.py` | M (≤ 1 day) |
| **Bean-Graph Mode** | 1 | 2 | No (uses existing `/beans` & `/conditions`) | None | `src/sharpit/fastapi/dependencies.py` | S (≤ half day) |
| **Live Flow Mode** | 1 | 5 | No (aggregates existing in-memory buffers) | None | `src/sharpit/engine/activity/service_map.py` | M (≤ 1 day) |
