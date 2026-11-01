# BootUI JSON contract — 0.4.0 drift extract for sharpit

Source: `C:\development\github\boot-ui-ref` (commit `ddfcb2436`, 2026-10-23, tag `v2.2.0`) compared against
reference base branch `ffroliva/1067-claude-code-plugin` in `C:\development\github\boot-ui` (commit `81d1476af`, 1141 commits behind).

Abbreviations for paths in BootUI 2.2.0:
- `DTO/` = `bootui-engine/src/main/java/io/github/jdubois/bootui/core/dto/` (in 2.2.0, `bootui-core` was folded into `bootui-engine`)
- `ENG/` = `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/`
- `AC/` = `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/` (in 2.2.0, `bootui-spring-autoconfigure` was folded into `bootui-spring-boot-starter`)
- `UI/` = `bootui-ui/src/main/frontend/src/`
- `CONF/` = `bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/`

This document records the exact contract drift for the 20 panels sharpit already has (including the panels list/activation/safe-mode envelope). For each panel, it details what changed in 2.2.0 across endpoints, response DTOs, errors, flags/settings, side effects, streams, MCP/CLI, and advisor rules, ending with "What sharpit must change" sized S/M/L.

---

## 1. Envelope (Panels list, activation, safe mode)

### 1. Endpoints
- **New endpoints added in 2.2.0:**
  - `GET /bootui/api/dismissed-findings`: lists advisor findings dismissed individually (`AC/web/DismissedFindingsController.java:43`). No query params.
  - `POST /bootui/api/dismissed-findings`: dismisses an advisor finding individually (`AC/web/DismissedFindingsController.java:48`).
    - Request body: JSON object `{"ruleId": str, "identity": str, "note": str|null}`.
  - `DELETE /bootui/api/dismissed-findings`: restores a dismissed finding (`AC/web/DismissedFindingsController.java:55`).
    - Request body: JSON object `{"ruleId": str, "identity": str}`.
- **Existing endpoints unchanged:**
  - `GET /bootui/api/panels` (`AC/web/PanelsController.java:68`).
  - `POST /bootui/api/dismissed-rules/{ruleId}` (`AC/web/DismissedRulesController.java`).
  - `DELETE /bootui/api/dismissed-rules/{ruleId}` (`AC/web/DismissedRulesController.java`).

### 2. Response DTOs
- `DismissedFindingDto` (`DTO/DismissedFindingDto.java:10`):
  - `ruleId` (str, non-null): ID of the violating advisor rule.
  - `identity` (str, non-null): canonical finding identity (e.g. file, symbol, coordinate).
  - `note` (str|null): developer free-text reason; served only by `GET /dismissed-findings`, omitted from MCP/CLI.
- `DismissedFindingsDto` (`DTO/DismissedFindingsDto.java:11`):
  - `dismissed` (List<DismissedFindingDto>, non-null).
  - `ignored` (int, non-null): count of stored entries that could not be parsed (malformed/newer format).
- `PanelDto` (`DTO/PanelDto.java`):
  - Shape unchanged (`id`, `title`, `available`, `unavailableReason`, `enabled`, `readOnly`, `readOnlyReason`).
  - In `BootUiPanels.java:94`:
    - Panel `overview` title changed from `"Overview"` to `"Scorecard"`.
    - Panel `live-memory` `actionCapable` changed from `false` to `true`.
    - New panel IDs added to upstream catalog: `java-agent`, `runtime-insights`, `code-inventory`, `code-paths`, `side-effects`.

```json
{
  "dismissed": [
    {
      "ruleId": "RAPI-RESP-010",
      "identity": "com.example.OrderController#getOrder",
      "note": "Legacy client dependency"
    }
  ],
  "ignored": 0
}
```

### 3. Error bodies and reason strings verbatim
- `DismissedFindingsController` validation error (status 400):
  `{"error":"Request body must be a JSON object with string fields ruleId, identity and an optional note."}` (`AC/web/DismissedFindingsController.java:94`, `ENG/advisor/AdvisorViolationException.java`).
- `PanelsController` transaction manager unavailable reason update:
  `"No configurable transaction manager bean is available"` (`AC/web/PanelsController.java:250`, previously `"No configurable PlatformTransactionManager bean is available"`).

### 4. Panel flags & settings
- `bootui.read-only`: covers `POST /dismissed-findings` and `DELETE /dismissed-findings` (HTTP 403 when true).
- `SecurityHeadersFilter` (`AC/safety/SecurityHeadersFilter.java:71-125`):
  - Synchronized header mutation on `SecurityHeadersResponse` prevents race conditions during concurrent SSE streaming writes.
  - Baseline security headers (`X-Content-Type-Options`, `Content-Security-Policy`) are deduplicated on repeated host writes.

### 5. Side effects
- None on `GET /bootui/api/panels` or `GET /bootui/api/dismissed-findings` (reads in-memory storage and configuration).

### 6. Streams
- None on envelope endpoints.

### 7. MCP tools and CLI
- Deliberately no MCP or CLI binding for `dismissed-findings` (`AC/web/DismissedFindingsController.java:23`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. Add `GET /sharpit/api/dismissed-findings`, `POST /sharpit/api/dismissed-findings`, and `DELETE /sharpit/api/dismissed-findings` with file-based persistence or in-memory backing in `src/sharpit/engine/advisors/`. Update `PANELS` in `src/sharpit/engine/panels.py` to optionally track `Scorecard` title and ensure security headers middleware deduplicates concurrent host writes.

---

## 2. Overview (Scorecard)

### 1. Endpoints
- `GET /bootui/api/overview` (`AC/web/OverviewController.java:39`). No query parameters. Request body: none.

### 2. Response DTOs
- `OverviewDto` (`DTO/OverviewDto.java:8-24`):
  - Added key: `run` (`ApplicationRunDto|null`): identity of the observed application start (`DTO/ApplicationRunDto.java:18`).
  - Retained keys: `bootUiVersion` (str), `applicationName` (str), `frameworkName` (str), `frameworkVersion` (str|null), `javaVersion` (str), `javaVendor` (str), `activeProfiles` (str[]), `defaultProfiles` (str[]), `webApplicationType` (str: `"SERVLET"|"REACTIVE"`), `serverPort` (int|null), `managementPort` (int|null), `contextPath` (str|null), `startupTimeMillis` (long|null), `activation` (`ActivationStatus`), `openApiUrl` (str|null).
- `ApplicationRunDto` (`DTO/ApplicationRunDto.java:18`):
  - `instanceId` (str, non-null): 8 lowercase hex characters identifying the JVM instance.
  - `runId` (str, non-null): 8 lowercase hex characters identifying the application run.
  - `ordinal` (int, non-null): 1-based index of this run within the instance.
  - `startedAt` (long, non-null): epoch timestamp in milliseconds when the run started.

```json
{
  "bootUiVersion": "2.2.0",
  "applicationName": "petclinic",
  "frameworkName": "Spring Boot",
  "frameworkVersion": "3.5.0",
  "javaVersion": "21.0.4",
  "javaVendor": "Eclipse Adoptium",
  "activeProfiles": ["dev"],
  "defaultProfiles": ["default"],
  "webApplicationType": "SERVLET",
  "serverPort": 8080,
  "managementPort": null,
  "contextPath": null,
  "startupTimeMillis": 2310,
  "activation": {"enabled": true, "localhostOnly": true, "reason": "Enabled by active profile 'dev'", "warnings": []},
  "openApiUrl": null,
  "run": {
    "instanceId": "a1b2c3d4",
    "runId": "e5f60718",
    "ordinal": 1,
    "startedAt": 1729700000000
  }
}
```

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- Panel title in `BootUiPanels.java:94` renamed to `"Scorecard"`.
- `actionCapable: false`, API prefix: none (bypasses panel gating).

### 5. Side effects
- None. Reads in-memory `RunIdentity`, environment, and platform runtime.

### 6. Streams
- None.

### 7. MCP tools and CLI
- MCP tool: `get_overview` (args: none, returns `OverviewDto`).
- CLI command: `bootui overview` / `get_overview`.

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. Add `run` object generation (`instance_id`, `run_id`, `ordinal`, `started_at`) to `src/sharpit/engine/collectors/overview.py`. Stamping a run ID allows correlating reloads and sessions across panels.

---

## 3. Config

### 1. Endpoints
- `GET /bootui/api/config?q=&source=&overridesOnly=false&offset=&limit=` (`AC/web/ConfigController.java:44`).
- `POST /bootui/api/config/overrides` (`AC/web/ConfigController.java:50`).
- `DELETE /bootui/api/config/overrides/{name}` (`AC/web/ConfigController.java:55`).
- `GET /bootui/api/profile-diff` (`AC/web/ProfileDiffController.java:31`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `ConfigReport`, `ConfigPropertyDto`, `ConfigPropertySuggestionDto`, `ConfigOverrideResult`, `ProfilesReport`, `ProfileSourceDto`.
- No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: true`, prefix: `/config`.
- Settings unchanged (`bootui.config.*`, `bootui.overrides-file`).

### 5. Side effects
- No GET side effects.

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_config` (schema: `QUERY_LIMIT`, compacted default limit: 25 rows via `McpAgentViews.INVENTORY_DEFAULT_LIMIT`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes. Ensure `get_config` MCP tool in `src/sharpit/engine/mcp.py` applies the default 25-row limit when limit is unspecified.

---

## 4. Mappings

### 1. Endpoints
- `GET /bootui/api/mappings/flat?q=&offset=&limit=` (`AC/web/MappingsController.java:40`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `MappingsReport`, `MappingDto`, `PageMetadata`.
- No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: false`, prefix: `/mappings`.

### 5. Side effects
- No GET side effects.

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_mappings` (schema: `QUERY_LIMIT`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes.

---

## 5. Loggers

### 1. Endpoints
- `GET /bootui/api/loggers?q=&offset=&limit=` (`AC/web/LoggersController.java:42`).
- `POST /bootui/api/loggers/{name}` (`AC/web/LoggersController.java:51`).
  - Request body: `{"level": str|null}` (null resets level).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `LoggersReport`, `LoggerDto`.
- No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- 400: `{"error":"Invalid log level: <level>"}`. Unchanged.

### 4. Panel flags & settings
- `actionCapable: true`, prefix: `/loggers`.

### 5. Side effects
- No GET side effects. Level change occurs only on POST.

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_loggers`, `set_logger_level`.

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes.

---

## 6. Beans

### 1. Endpoints
- `GET /bootui/api/beans?q=&offset=&limit=` (`AC/web/BeansController.java:37`).
- No endpoint drift in 2.2.0. (Runtime bean call graph is part of the separate `code-paths` panel).

### 2. Response DTOs
- `BeansReport`, `BeanDto`.
- No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: false`, prefix: `/beans`.

### 5. Side effects
- No GET side effects.

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_beans` (schema: `QUERY_LIMIT`, compacted default limit: 25 rows via `McpAgentViews.INVENTORY_DEFAULT_LIMIT`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes in `beans` collector.

---

## 7. Vulnerabilities

### 1. Endpoints
- `GET /bootui/api/vulnerabilities` (`AC/web/VulnerabilitiesController.java:100`).
- `POST /bootui/api/vulnerabilities/scan` (`AC/web/VulnerabilitiesController.java:120`).
- No new endpoints, but response payload extended with runtime reach and symbol fields.

### 2. Response DTOs
- `DependenciesReport` (`DTO/DependenciesReport.java:14`):
  - Added key: `runtimeReach` (`RuntimeReachSummaryDto|null`): summary of runtime reach from Code Inventory (`DTO/RuntimeReachSummaryDto.java:14`).
- `DependencyDto` (`DTO/DependencyDto.java:11`):
  - Added key: `runtimeReach` (`RuntimeReachDto|null`): whether this dependency's code was loaded during this run (`DTO/RuntimeReachDto.java:23`).
- `DependencyVulnerabilityDto` (`DTO/DependencyVulnerabilityDto.java:46-50`):
  - Added key: `advisorySymbols` (`List<String>`): class or `Class#method` symbols named in the advisory.
  - Added key: `advisorySymbolSource` (`String|null`): source of symbols (`"OSV"|"ADVISORY_TEXT"|"NONE"`).
  - Added key: `runtimeReach` (`RuntimeReachDto|null`): reach evidence for this advisory.
  - Updated field: `score` (`Double|null`): selects CVSS v4.0 score if valid v4 vector applies, otherwise CVSS v3.x Base score.
- `RuntimeReachSummaryDto` (`DTO/RuntimeReachSummaryDto.java:14`):
  - `available` (bool), `unavailableReason` (str|null), `generation` (long|null), `note` (str|null), `incompleteReason` (str|null).
- `RuntimeReachDto` (`DTO/RuntimeReachDto.java:23`):
  - `status` (str: `"NOT_LOADED"|"LOADED"|"AFFECTED_CLASS_LOADED"|"UNKNOWN"`).
  - `reason` (str|null): explanation for `UNKNOWN` or status qualifier.
  - `classesLoaded` (long): classes loaded in this run.
  - `classesLoadedTotal` (long): classes loaded across entire JVM lifetime.
  - `loadedThisRun` (bool): whether classes were loaded in this run.
  - `firstRoute` (str|null): first HTTP route that triggered class load.
  - `loadedClasses` (List<String>): classes named in advisory that actually loaded.

```json
{
  "scanningEnabled": true,
  "total": 45,
  "vulnerable": 1,
  "severityCounts": [{"severity": "HIGH", "count": 1}],
  "scan": {"status": "SUCCESS", "scannedAt": 1729700000000, "message": "Scan complete."},
  "coverage": {"complete": true, "unresolvedCoordinates": 0},
  "runtimeReach": {
    "available": false,
    "unavailableReason": "Code Inventory panel is disabled.",
    "generation": null,
    "note": null,
    "incompleteReason": null
  },
  "dependencies": [
    {
      "groupId": "org.yaml",
      "artifactId": "snakeyaml",
      "version": "1.33",
      "packageName": "org.yaml.snakeyaml",
      "source": "classpath",
      "vulnerabilityCount": 1,
      "highestSeverity": "HIGH",
      "runtimeReach": null,
      "vulnerabilities": [
        {
          "id": "GHSA-mjrt-cq6q-gw5b",
          "summary": "SnakeYAML denial of service vulnerability",
          "details": "Uncaught exception leads to crash...",
          "severity": "HIGH",
          "score": 7.5,
          "aliases": ["CVE-2022-1471"],
          "references": ["https://nvd.nist.gov/vuln/detail/CVE-2022-1471"],
          "fixedVersions": ["2.0"],
          "fixAvailable": true,
          "epssScore": 0.0034,
          "epssPercentile": 0.72,
          "dismissed": false,
          "advisorySymbols": ["org.yaml.snakeyaml.constructor.Constructor"],
          "advisorySymbolSource": "OSV",
          "runtimeReach": null
        }
      ],
      "assessment": {"status": "VULNERABLE"}
    }
  ]
}
```

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: true`, prefix: `/vulnerabilities`.
- Settings unchanged (`bootui.vulnerabilities.*`).

### 5. Side effects
- `GET /vulnerabilities`: reads cached inventory and report; **never opens a socket or queries OSV on GET**.
- `POST /vulnerabilities/scan`: queries OSV batch API over HTTP.

### 6. Streams
- None.

### 7. MCP tools and CLI
- Tool `get_vulnerabilities_report`: schema upgraded from `NONE` to `QUERY_LIMIT` (`ENG/mcp/McpToolCatalog.java:162`).
  - Supports agent compaction (`McpAgentViews.VULNERABILITIES_DEFAULT_LIMIT = 10`, `ADVISORIES_PER_DEPENDENCY = 5`, `ADVISORY_LIST_ITEMS = 3`).
- Tool `vulnerabilities_scan`: marked as progress-capable (`McpToolCatalog.reportsProgress("vulnerabilities_scan") == true`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: M**.
  1. Add `runtimeReach: null` to `DependenciesReport` and `DependencyDto` in `src/sharpit/engine/collectors/vulns/report.py`.
  2. Add `advisorySymbols: []`, `advisorySymbolSource: null`, and `runtimeReach: null` to `DependencyVulnerabilityDto`.
  3. Support CVSS v4.0 score selection fallback when v4 vector is present in OSV response.
  4. Update `get_vulnerabilities_report` MCP tool in `src/sharpit/engine/mcp.py` to accept `query` and `limit` with default limit 10.

---

## 8. MCP Server

### 1. Endpoints
- `GET /bootui/api/mcp-server` (`AC/mcp/BootUiMcpController.java:39`).
- `POST /bootui/api/mcp-server/toggle` (`AC/mcp/BootUiMcpController.java:46`).
- `POST /bootui/api/mcp` (`AC/mcp/SpringMcpBridgeController.java:45`).
- No path changes.

### 2. Response DTOs
- `McpServerStatus` (`DTO/McpServerStatus.java:28-49`):
  - Added key: `supportedProtocolVersions` (`List<String>`, non-null): revisions served, newest first (`["2026-07-28", "2025-06-18"]`).
  - Added key: `cancellations` (`long`, non-null): count of calls cancelled before completion.
  - Added key: `progressDropped` (`long`, non-null): count of progress notifications suppressed due to `bootui.mcp.max-response-bytes`.
  - Retained keys: `enabled`, `configuredMode`, `overridden`, `serverName`, `serverVersion`, `transport`, `endpoint`, `protocolVersion`, `maxResults`, `callCount`, `totalLatencyMillis`, `capacityRefusals`, `timeouts`, `responseLimitRefusals`, `toolCount`, `tools`.

```json
{
  "enabled": true,
  "configuredMode": "LOCAL_ONLY",
  "overridden": false,
  "serverName": "BootUI",
  "serverVersion": "2.2.0",
  "transport": "http",
  "endpoint": "/bootui/api/mcp",
  "protocolVersion": "2025-06-18",
  "supportedProtocolVersions": ["2026-07-28", "2025-06-18"],
  "maxResults": 100,
  "callCount": 12,
  "totalLatencyMillis": 1450,
  "capacityRefusals": 0,
  "timeouts": 0,
  "responseLimitRefusals": 0,
  "cancellations": 0,
  "progressDropped": 0,
  "toolCount": 26,
  "tools": []
}
```

### 3. Error bodies and reason strings verbatim
- Verbatim JSON-RPC and protocol messages (`ENG/mcp/McpProtocol.java`):
  - Unknown tool: `"Unknown tool: <name>"`
  - Tool unavailable: `"Tool not available in this application: <name>. Its <panel> panel is unavailable: <reason>"`
  - Invalid type: `"Argument '<name>' must be <type>"`
  - Lower bound: `"Argument '<name>' must be at least <minimum>"`

### 4. Panel flags & settings
- `actionCapable: true`, prefix: `/mcp-server`.
- `/bootui/api/mcp` is intentionally NOT under `/mcp-server` and is not panel-gated; it has its own switch (`bootui.mcp.enabled`).

### 5. Side effects
- No GET side effects.

### 6. Streams
- Modern MCP supports streaming over SSE on `/bootui/api/mcp` when `Accept: text/event-stream` is requested (`ENG/mcp/McpProtocol.java:60`).
  - Stream events terminate with `\n\n`. Heartbeat comment: `:\n\n`.
  - Progress notification: JSON-RPC method `notifications/progress` with params `{"progressToken": token, "progress": n, "total": m}`.
  - Cancellation notification: `notifications/cancelled`.

### 7. MCP tools and CLI
- New tools added in 2.2.0 catalog (`ENG/mcp/McpToolCatalog.java`):
  - `get_http_routes`: schema `LIMIT`, panel `http-exchanges`, read-only.
  - `get_request_profile`: schema `ID`, panel `activity`, read-only.
- Tools converted to `QUERY_LIMIT`: `get_vulnerabilities_report`, `get_live_activity`, `get_sql_traces`, `get_log_tail`.
- Modern MCP headers supported: `Mcp-Method`, `Mcp-Name`, `MCP-Protocol-Version`.
- Modern `_meta` keys: `io.modelcontextprotocol/protocolVersion`, `io.modelcontextprotocol/clientCapabilities`, `io.modelcontextprotocol/serverInfo`, `progressToken`.

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: M**. Update `src/sharpit/engine/mcp.py` to:
  1. Add `supportedProtocolVersions: ["2026-07-28", "2025-06-18"]`, `cancellations: 0`, and `progressDropped: 0` to `GET /sharpit/api/mcp-server`.
  2. Register tools `get_http_routes` and `get_request_profile`.
  3. Support `query` parameter and compaction on `get_vulnerabilities_report`, `get_live_activity`, `get_sql_traces`, `get_log_tail`.
  4. Parse MCP 2026-07-28 request metadata (`_meta.progressToken`).

---

## 9. CLI

### 1. Endpoints
- `GET /bootui/api/cli` (`AC/cli/BootUiCliController.java:37`).
- `POST /bootui/api/cli/tools/{name}` (`AC/cli/BootUiCliController.java:54`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `CliServerStatus` (`DTO/CliServerStatus.java`):
  - `enabled` (bool), `serverName` (str), `serverVersion` (str), `endpoint` (str), `maxResults` (int), `callCount` (long), `toolCount` (int), `tools` (List<McpToolInfo>).
  - No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- Unchanged: `{"error": "<message>"}` on invocation failure.

### 4. Panel flags & settings
- `actionCapable: false`, prefix: none (`bootui.cli.enabled` switch).

### 5. Side effects
- No GET side effects.

### 6. Streams
- None.

### 7. MCP tools and CLI
- CLI endpoint routes commands through `McpToolCatalog` and renders payload via `SpringMcpPayloads.render(...)`.

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes. Keep tools exposed via `src/sharpit/engine/tools.py` in sync with MCP tool catalog.

---

## 10. Activity (Live Activity)

### 1. Endpoints
- `GET /bootui/api/activity` (`AC/activity/LiveActivityController.java:345`).
  - Query parameters:
    - `type` (str|null), `severity` (str|null), `since` (long, default 0), `limit` (int, default 200, max 5000), `q` (str|null), `until` (long|null), `cursor` (str|null), `pageSize` (int, default 0).
    - **New query parameters added in 2.2.0:**
      - `source` (str|null): `"journal"` (default) or `"buffers"`.
      - `route` (str|null): filter entries by low-cardinality route template.
      - `run` (str|null): filter entries by run ID.
      - `requestId` (str|null): filter entries by request correlation ID.
      - `noRequest` (bool, default false): filter entries not tied to any HTTP request.
- `GET /bootui/api/activity/request/{id}`: detail read returning `RequestProfileDto` (`AC/activity/LiveActivityController.java:575`).
- **New detail endpoints added in 2.2.0:**
  - `GET /bootui/api/activity/journal`: status of runtime journal (`AC/activity/LiveActivityController.java:507`).
  - `GET /bootui/api/activity/resources`: resource track and CPU ledger (`AC/activity/LiveActivityController.java:513`).
  - `GET /bootui/api/activity/request/{id}/journal`: journal request profile (`AC/activity/LiveActivityController.java:560`).
  - `POST /bootui/api/activity/journal/clear`: drops recorded events; body `{"confirm": true}` (`AC/activity/LiveActivityController.java:519`).
- `POST /bootui/api/activity/use-existing-datasource` (`AC/activity/LiveActivityController.java:535`).
- `GET /bootui/api/activity/stream`: SSE change stream (`AC/activity/LiveActivityController.java:589`).

### 2. Response DTOs
- `LiveActivityReport` (`DTO/LiveActivityReport.java`): top-level fields unchanged (`available`, `entries`, `typeCounts`, `kpis`, `sources`, `warnings`, `pageInfo`, `persistenceOption`).
- `RequestProfileDto` (`DTO/RequestProfileDto.java:42-59`):
  - Added key: `restCalls` (`List<RestClientTraceEntryDto>`): correlated outbound HTTP calls.
  - Added key: `cacheAccesses` (`List<RequestProfileCacheAccessDto>`): correlated cache operations.
  - Added key: `sections` (`List<RequestProfileSectionDto>`): correlation tier and truncation metadata per section.
  - Added key: `correlationTiers` (`List<RequestProfileTierDto>`): tiers available on this stack.
  - Added key: `approximate` (`boolean`): whether time-window heuristic was used for any section.
- `RuntimeJournalStatusDto` (`DTO/RuntimeJournalStatusDto.java:26-44`):
  - `enabled` (bool), `runId` (str), `retainedEvents` (int), `retainedBytes` (long), `maxEvents` (int), `maxBytes` (long), `reservedEvents` (int), `reservedCapacity` (int), `evictedEvents` (long), `bindingBound` (str: `"COUNT"|"BYTES"|null`), `oldestRetainedAt` (long|null), `queueDepth` (int), `queueCapacity` (int), `recorded` (Map<str, long>), `dropped` (Map<str, long>), `droppedEvents` (long), `previousRuns` (List), `previousRunsUnavailable` (str|null), `agentEvidence` (object|null).
- `RuntimeResourcesDto` (`DTO/RuntimeResourcesDto.java:16-21`):
  - `available` (bool), `unavailableReason` (str|null), `families` (str[]), `points` (List), `totals` (object).
- `RuntimeJournalClearRequest` (`DTO/RuntimeJournalClearRequest.java:4`): `confirm` (bool).
- `RuntimeJournalClearResult` (`DTO/RuntimeJournalClearResult.java:10`):
  - `status` (str: `"cleared"|"blocked"|"unavailable"`), `message` (str), `clearedEvents` (int).

```json
{
  "status": "cleared",
  "message": "Recorded events dropped.",
  "clearedEvents": 142
}
```

### 3. Error bodies and reason strings verbatim
- Buffer source filter warning (`ENG/journal/JournalActivityReports.java:34`):
  `"The route, run, request id, and no-request filters apply to the feed rendered from the runtime journal (source=journal); this feed comes from the panel buffers."`
- Journal disabled reason:
  `"Live Activity reads the runtime journal, which is disabled (bootui.runtime-journal.enabled=false)."`

### 4. Panel flags & settings
- `actionCapable: true` (in sharpit: `false`).
- Setting `bootui.activity.feed-source`: default `"journal"`. Value `"buffers"` was removed in 2.0.0 and fails startup.
- Setting `bootui.activity.persistence.capture-interval` was removed in 2.0.0.

### 5. Side effects
- No GET side effects.

### 6. Streams
- `GET /bootui/api/activity/stream`: SSE change stream emits when new requests/events are recorded.

### 7. MCP tools and CLI
- `get_live_activity`: schema changed from `LIMIT` to `QUERY_LIMIT` (compacted default limit: 25 via `McpAgentViews.LIVE_ACTIVITY_DEFAULT_LIMIT`).
- `get_request_profile`: NEW MCP tool! (schema: `ID`, required argument `id`, panel `activity`, read-only).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: M**.
  1. Add `restCalls: []`, `cacheAccesses: []`, `sections: []`, `correlationTiers: []`, and `approximate: false` to `RequestProfileDto` in `src/sharpit/fastapi/capture.py`.
  2. Implement `get_request_profile` MCP tool in `src/sharpit/engine/mcp.py`.
  3. Support `GET /sharpit/api/activity/journal` returning a disabled or basic in-memory status DTO (`RuntimeJournalStatusDto`).

---

## 11. HTTP Exchanges

### 1. Endpoints
- `GET /bootui/api/http-exchanges` (`AC/web/HttpExchangesController.java:82`):
  - Query parameters: `q`, `method`, `statusClass`, `offset`, `limit`.
  - **New parameter added in 2.2.0:** `route` (str|null): filter exchanges by low-cardinality route identifier.
- **New endpoint added in 2.2.0:**
  - `GET /bootui/api/http-exchanges/routes` (`AC/web/HttpExchangesController.java:94`):
    - Query parameters:
      - `limit` (int, default 25, clamped 1..100 via `HttpRouteSummaryService.MAX_TOP_PER_CRITERION = 100`).
      - `route` (str|null): optional pinned route to include even if outside top rankings.
    - Request body: none.

### 2. Response DTOs
- `HttpExchangesReport` (`DTO/HttpExchangesReport.java:10`):
  - Added key: `retention` (`CaptureRetentionDto|null`): how the buffer retains records (`DTO/CaptureRetentionDto.java:23`).
- `HttpExchangeDto` (`DTO/HttpExchangeDto.java:17-36`):
  - Added key: `route` (`String|null`): low-cardinality handler route or masked path.
  - Added key: `routeSource` (`String|null`): `"FRAMEWORK_TEMPLATE"|"DECLARED_MAPPING"|"MASKED_PATH"`.
  - Added key: `requestId` (`String|null`): BootUI correlation request ID.
- `CaptureRetentionDto` (`DTO/CaptureRetentionDto.java:23`):
  - `applicationManaged` (bool), `capacity` (int|null), `reservedCapacity` (int|null), `retained` (int), `reserved` (int|null), `evicted` (long|null), `slowThresholdMillis` (long|null).
- `HttpRoutesReport` (`DTO/HttpRoutesReport.java:21-29`):
  - `available` (bool), `unavailableReason` (str|null), `window` (`HttpRouteWindowDto`), `routes` (`List<HttpRouteDto>`), `topPerCriterion` (int), `routesTruncated` (bool), `distinctRoutes` (int), `notes` (str[]).
- `HttpRouteDto` (`DTO/HttpRouteDto.java:32-52`):
  - `id` (str: `"METHOD route"`), `method` (str), `route` (str), `routeSource` (str), `requests` (long), `status2xx` (long), `status3xx` (long), `status4xx` (long), `status5xx` (long), `statusOther` (long), `errorCount` (long), `timedRequests` (long), `totalDurationMs` (long), `avgDurationMs` (Double|null), `p50DurationMs` (Long|null), `p95DurationMs` (Long|null), `p99DurationMs` (Long|null), `maxDurationMs` (Long|null), `shareOfRetainedTimePercent` (double), `topFor` (str[]).

```json
{
  "available": true,
  "unavailableReason": null,
  "window": {
    "retainedExchanges": 150,
    "bufferSize": 200,
    "evicted": 0,
    "hiddenSelfExchanges": 12,
    "summarizedExchanges": 138,
    "timedExchanges": 138,
    "oldestTimestamp": 1729700000000,
    "newestTimestamp": 1729700100000,
    "totalDurationMs": 4250
  },
  "routes": [
    {
      "id": "GET /api/pets/{id}",
      "method": "GET",
      "route": "/api/pets/{id}",
      "routeSource": "FRAMEWORK_TEMPLATE",
      "requests": 80,
      "status2xx": 78,
      "status3xx": 0,
      "status4xx": 2,
      "status5xx": 0,
      "statusOther": 0,
      "errorCount": 2,
      "timedRequests": 80,
      "totalDurationMs": 2400,
      "avgDurationMs": 30.0,
      "p50DurationMs": 25,
      "p95DurationMs": 55,
      "p99DurationMs": 80,
      "maxDurationMs": 95,
      "shareOfRetainedTimePercent": 56.47,
      "topFor": ["REQUESTS", "TOTAL_TIME", "P95_DURATION"]
    }
  ],
  "topPerCriterion": 25,
  "routesTruncated": false,
  "distinctRoutes": 1,
  "notes": []
}
```

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: false`, prefix: `/http-exchanges`.
- Setting `bootui.http-exchanges.reserved-share`: default `10` (% of buffer reserved for 5xx and slow requests).

### 5. Side effects
- No GET side effects.

### 6. Streams
- None.

### 7. MCP tools and CLI
- Tool `get_http_exchanges`: compacted default limit 25 rows (`McpAgentViews.INVENTORY_DEFAULT_LIMIT`).
- Tool `get_http_routes`: NEW tool! (schema: `LIMIT`, panel `http-exchanges`, read-only).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: M**.
  1. Add `route`, `routeSource`, and `requestId` to `HttpExchangeDto` in `src/sharpit/fastapi/capture.py`.
  2. Add `retention` (`CaptureRetentionDto`) to `HttpExchangesReport`.
  3. Implement `GET /sharpit/api/http-exchanges/routes` calculating `HttpRoutesReport` from the exchange buffer.
  4. Register `get_http_routes` tool in `src/sharpit/engine/mcp.py`.

---

## 12. Exceptions

### 1. Endpoints
- `GET /bootui/api/exceptions` (`AC/web/ExceptionsController.java` / `AC/reactive/ReactiveExceptionsController.java:93`).
- **New endpoint added in 2.2.0:**
  - `GET /bootui/api/exceptions/caught`: returns caught-in-code report from agent sensor (`AC/web/ExceptionsController.java` / `AC/reactive/ReactiveExceptionsController.java:103`).
- `GET /bootui/api/exceptions/{id}`.
- `POST /bootui/api/exceptions/{id}/status`: update group status (`OPEN`, `ACKNOWLEDGED`, `RESOLVED`).
- `DELETE /bootui/api/exceptions`: clear captured exceptions.
- `GET /bootui/api/exceptions/stream`: SSE change stream.

### 2. Response DTOs
- `ExceptionsReport` (`DTO/ExceptionsReport.java:12`):
  - Added key: `caughtInCode` (`CaughtExceptionsSummaryDto|null`): summary of exceptions caught in application code (`null` without agent sensor).
- `CaughtExceptionsReport` (`DTO/CaughtExceptionsReport.java:16`):
  - `available` (bool), `unavailableReason` (str|null), `limitations` (str[]), `settling` (long), `occurrences` (long), `findings` (int), `rows` (List<CaughtExceptionRowDto>).

```json
{
  "available": true,
  "unavailableReason": null,
  "maxGroups": 100,
  "totalExceptions": 2,
  "groups": [],
  "caughtInCode": null
}
```

### 3. Error bodies and reason strings verbatim
- Unavailable caught exceptions reason when sensor missing:
  `"Caught exceptions are recorded by the BootUI Java agent's caught-exceptions sensor."`

### 4. Panel flags & settings
- `actionCapable: true`, prefix: `/exceptions`.

### 5. Side effects
- No GET side effects.

### 6. Streams
- `GET /bootui/api/exceptions/stream`: SSE change stream.

### 7. MCP tools and CLI
- `get_exceptions`, `get_exception_detail`, `clear_exceptions`.

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. Add `caughtInCode: null` to `ExceptionsReport` and add endpoint `GET /sharpit/api/exceptions/caught` returning `CaughtExceptionsReport.unavailable("Caught exceptions are not supported in this runtime.")`.

---

## 13. SQL Trace

### 1. Endpoints
- `GET /bootui/api/sql-trace` (`AC/sqltrace/SqlTraceController.java:44`).
- `POST /bootui/api/sql-trace/clear` (`AC/sqltrace/SqlTraceController.java:55`).
- `POST /bootui/api/sql-trace/recording` (`AC/sqltrace/SqlTraceController.java:60`).
- `GET /bootui/api/sql-trace/stream` (`AC/sqltrace/SqlTraceController.java:67`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `SqlTraceReport` (`DTO/SqlTraceReport.java:23`):
  - Added key: `retention` (`CaptureRetentionDto|null`): retention stats with reserved slow/failed share.
- `SqlTraceEntryDto` (`DTO/SqlTraceEntryDto.java:34`):
  - Added key: `durationMicros` (`long`, non-null): exact wall-clock execution time in microseconds. `durationMillis` is retained and derived by rounding.

```json
{
  "id": 1,
  "timestamp": 1729700000000,
  "sql": "SELECT id, name FROM pets WHERE id = ?",
  "statementType": "PREPARED",
  "category": "SELECT",
  "durationMicros": 350,
  "durationMillis": 0,
  "success": true,
  "errorMessage": null,
  "affectedRows": 1,
  "batchSize": 0,
  "connectionId": "conn-1",
  "thread": "async-worker-1",
  "slow": false,
  "parameters": ["42"],
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "callSite": "petclinic.repository.PetRepository.findById(PetRepository.py:34)"
}
```

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: true`, prefix: `/sql-trace`.
- Setting `bootui.sql-trace.reserved-share`: default `10` (% reserved for slow/failed queries).

### 5. Side effects
- No GET side effects.

### 6. Streams
- `GET /bootui/api/sql-trace/stream`: SSE change stream.

### 7. MCP tools and CLI
- Tool `get_sql_traces`: schema upgraded from `NONE` to `QUERY_LIMIT` (`ENG/mcp/McpToolCatalog.java:182`). Compacted default limit: 20 statements via `McpAgentViews.SQL_TRACES_DEFAULT_LIMIT`.
- `clear_sql_traces`, `pause_sql_trace_recording`, `resume_sql_trace_recording`.

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. Add `durationMicros` (from nanosecond timers) to `SqlTraceEntryDto` and `retention: null` to `SqlTraceReport` in `src/sharpit/engine/sqla.py`. Update `get_sql_traces` MCP tool to accept `query` and `limit`.

---

## 14. Log Tail

### 1. Endpoints
- `GET /bootui/api/log-tail/recent` (`AC/logging/LogTailController.java`).
- `GET /bootui/api/log-tail/stream` (`AC/logging/LogTailController.java`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `LogLineDto` (`DTO/LogLineDto.java:18`):
  - Added key: `messageOmitted` (`boolean`, non-null): `true` when the value-exposure policy withheld the message (e.g. `bootui.expose-values=METADATA_ONLY`), so `message: null` is distinguishable from an empty string.
  - Retained keys: `timestamp` (long), `level` (str), `logger` (str), `message` (str|null), `thread` (str).

```json
{
  "timestamp": 1729700000000,
  "level": "INFO",
  "logger": "petclinic.service.ClinicService",
  "message": "Fetched 12 pet records",
  "thread": "main",
  "messageOmitted": false
}
```

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: false`, prefix: `/log-tail`.

### 5. Side effects
- No GET side effects.

### 6. Streams
- `GET /bootui/api/log-tail/stream`: text/event-stream of recent application log lines.

### 7. MCP tools and CLI
- Tool `get_log_tail`: schema upgraded from `NONE` to `QUERY_LIMIT` (`ENG/mcp/McpToolCatalog.java:213`). Compacted default limit: 50 lines via `McpAgentViews.LOG_TAIL_DEFAULT_LIMIT`.

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. Add `messageOmitted: false` (or `true` if in `METADATA_ONLY` mode) to `LogLineDto` in `src/sharpit/fastapi/capture.py`. Update `get_log_tail` MCP tool to accept `query` and `limit`.

---

## 15. Alembic (Flyway / Liquibase)

### 1. Endpoints
- Flyway: `GET /bootui/api/flyway/migrations`, `POST /bootui/api/flyway/migrate`, `POST /bootui/api/flyway/clean`.
- Liquibase: `GET /bootui/api/liquibase/changesets`, `POST /bootui/api/liquibase/update`.
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `FlywayReport`, `FlywayDatabaseDto`, `FlywayMigrationDto`, `LiquibaseReport`, `LiquibaseDatabaseDto`, `LiquibaseChangeSetDto`.
- No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: true` (in BootUI; in sharpit: action-capable only for `POST /alembic/refresh`).

### 5. Side effects
- In BootUI: `GET /flyway/migrations` queries `flyway.info()` (queries DB schema history table).
- In sharpit: GET is strictly read-only and cached; refreshed only via `POST /alembic/refresh` to preserve sharpit's zero-side-effects-on-GET rule.

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_flyway_migrations`, `get_liquibase_changesets` (in sharpit: `get_alembic_migrations`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes.

---

## 16. Database Connection Pools

### 1. Endpoints
- `GET /bootui/api/database-connection-pools/pools` (`AC/web/DatabaseConnectionPoolsController.java:37`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `HikariPoolsReport` (`DTO/HikariPoolsReport.java:13`):
  - **Renamed key:** `hikariPresent` → `poolLibraryPresent` (`boolean`, non-null): whether a supported pool library is present (HikariCP on Spring, Agroal on Quarkus, SQLAlchemy on sharpit).
  - Retained keys: `total` (int), `pools` (List<HikariPoolDto>).
- `HikariPoolDto` (`DTO/HikariPoolDto.java:13-31`):
  - **Added key:** `implementation` (`String|null`): name of connection pool library (`"HikariCP"|"Agroal"|"SQLAlchemy"`).
  - **Nullability changes:**
    - `connectionTimeoutMs`, `idleTimeoutMs`, `maxLifetimeMs`, `validationTimeoutMs`, `keepaliveTimeMs`: changed from primitive `long` to nullable `Long` (unexposed settings are emitted as `null`).
    - `readOnly`, `autoCommit`: changed from primitive `boolean` to nullable `Boolean` (unexposed flags are emitted as `null`).

```json
{
  "poolLibraryPresent": true,
  "total": 1,
  "pools": [
    {
      "beanName": "default",
      "poolName": "default",
      "implementation": "SQLAlchemy",
      "jdbcUrl": "sqlite:///./app.db",
      "username": "******",
      "driverClassName": "sqlite3",
      "minimumIdle": 5,
      "maximumPoolSize": 10,
      "connectionTimeoutMs": 30000,
      "idleTimeoutMs": 600000,
      "maxLifetimeMs": null,
      "validationTimeoutMs": null,
      "keepaliveTimeMs": null,
      "readOnly": null,
      "autoCommit": true,
      "available": true,
      "unavailableReason": null,
      "snapshot": {
        "active": 2,
        "idle": 3,
        "total": 5,
        "pending": 0,
        "max": 10
      }
    }
  ]
}
```

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: false`, prefix: `/database-connection-pools`.

### 5. Side effects
- No GET side effects (reads in-memory pool counters).

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_database_connection_pools` (`McpToolCatalog.java:233`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. In `src/sharpit/engine/collectors/pools.py`:
  1. Rename JSON key `hikariPresent` to `poolLibraryPresent`.
  2. Add `implementation: "SQLAlchemy"` to each pool entry.
  3. Emit unmeasured timeout values (`validationTimeoutMs`, `keepaliveTimeMs`, etc.) and `readOnly` as `null` rather than sentinel numbers or booleans.

---

## 17. Health

### 1. Endpoints
- `GET /bootui/api/health` (`AC/web/HealthController.java:31`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `HealthNodeDto` (`DTO/HealthNodeDto.java:8`):
  - `name` (str), `status` (str), `details` (object|null), `components` (List<HealthNodeDto>), `available` (bool), `unavailableReason` (str|null), `guidanceReason` (str|null), `setup` (List<HealthSetupStepDto>).
  - No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: false` (in BootUI; in sharpit: `true` for `POST /health/check`).

### 5. Side effects
- BootUI executes health checks on GET. sharpit caches on GET, runs checks on `POST /health/check` only.

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_health` (`McpToolCatalog.java:216`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes.

---

## 18. Threads

### 1. Endpoints
- `GET /bootui/api/threads` (`AC/web/ThreadDumpController.java:38`).
- `POST /bootui/api/threads/download` (`AC/web/ThreadDumpController.java`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `ThreadDumpReport`, `ThreadInfoDto`, `ThreadStateCountDto`.
- No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: true` in BootUI (for download action); in sharpit: `false`.

### 5. Side effects
- No GET side effects.

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_threads` (schema: `QUERY_LIMIT`, compacted default limit: 25 threads via `McpAgentViews.INVENTORY_DEFAULT_LIMIT`).

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes.

---

## 19. REST API Advisor

### 1. Endpoints
- `GET /bootui/api/rest-api` (`AC/restapi/RestApiController.java:44`).
- `POST /bootui/api/rest-api/scan` (`AC/restapi/RestApiController.java:50`).
- No path changes.

### 2. Response DTOs
- `RestApiReport` (`DTO/RestApiReport.java:10`):
  - `violationDetails` (`AdvisorViolationDetailsDto|null`): carries `locationNotes` (str[]) and `changes` (object|null).
- `RestApiRuleResultDto` (`DTO/RestApiRuleResultDto.java:19`):
  - **Added key:** `sampleLocations` (`List<AdvisorViolationLocationDto>`): source code locations aligned index-for-index with `sampleViolations`.
- `AdvisorViolationLocationDto` (`DTO/AdvisorViolationLocationDto.java`):
  - `file` (str|null), `line` (int|null), `uri` (str|null).

```json
{
  "id": "RAPI-RESP-010",
  "name": "Do not set @ResponseStatus reason on body-returning REST handlers",
  "category": "RESPONSES",
  "severity": "MEDIUM",
  "description": "On Spring MVC a non-blank @ResponseStatus reason makes Spring call HttpServletResponse.sendError...",
  "status": "VIOLATION",
  "violationCount": 1,
  "sampleViolations": [
    "OrderController#getOrder — @ResponseStatus reason \"not found\" discards the returned body"
  ],
  "sampleLocations": [
    {
      "file": "com/example/OrderController.java",
      "line": 42,
      "uri": "file:///path/to/com/example/OrderController.java#L42"
    }
  ],
  "recommendation": "Remove the reason attribute. Return a ResponseEntity...",
  "learnMoreUrl": "https://docs.spring.io/...",
  "dismissed": false
}
```

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: true`, prefix: `/rest-api`.

### 5. Side effects
- Static analysis on routes and controllers; no socket or database operations on GET.

### 6. Streams
- None.

### 7. MCP tools and CLI
- `get_rest_api_advisor_report`, `rest_api_advisor_scan`.

### 8. Advisor rules
- **4 new REST API rules added in 2.2.0 (`ENG/restapi/RestApiRuleRegistry.java`):**
  1. **`RAPI-RESP-010`**:
     - Title: `"Do not set @ResponseStatus reason on body-returning REST handlers"`
     - Category: `RESPONSES`
     - Severity: `MEDIUM`
     - Trigger: A Spring MVC handler or exception handler returns a body while `@ResponseStatus` specifies a non-blank `reason` attribute (causing Spring to call `HttpServletResponse.sendError` and discard the returned body).
     - Applicability: Spring MVC only (skipped on WebFlux and JAX-RS).
  2. **`RAPI-RESP-011`**:
     - Title: `"Map an empty Optional read to an explicit status"`
     - Category: `RESPONSES`
     - Severity: `LOW`
     - Trigger: A Spring GET handler returns `Optional<T>` directly as its body, which Spring serializes as 200 with `null` rather than mapping empty to 404 Not Found.
     - Applicability: Spring only.
  3. **`RAPI-VALID-006`**:
     - Title: `"Bind at most one @RequestBody per handler"`
     - Category: `VALIDATION`
     - Severity: `HIGH`
     - Trigger: A handler declares multiple `@RequestBody` parameters on a non-form request, causing the second parameter binding to fail with "Required request body is missing".
     - Applicability: Spring only.
  4. **`RAPI-VER-007`**:
     - Title: `"Bodyless handlers must not require a Content-Type"`
     - Category: `VERSIONING`
     - Severity: `HIGH`
     - Trigger: A GET, HEAD, or DELETE handler declares or inherits a `consumes` condition without binding a request body, rejecting bodyless requests with HTTP 415.
     - Applicability: Spring only.

### What sharpit must change
- **Size: M**.
  1. Add `sampleLocations: []` to each item in `results` in `src/sharpit/engine/collectors/restapi/rules.py`.
  2. Add Python counterparts for the relevant rules:
     - `RAPI-VER-007` analog: FastAPI GET/HEAD/DELETE routes requiring a request body.
     - `RAPI-RESP-011` analog: FastAPI endpoints returning `Optional[T]` without translating `None` to HTTP 404.

---

## 20. HTTP Probe

### 1. Endpoints
- `POST /bootui/api/http-probe` (`AC/web/HttpProbeController.java:39`).
  - Request body: `HttpProbeRequest` (`method`, `path`, `headers`, `body`, `timeoutMillis`).
- No endpoint drift in 2.2.0.

### 2. Response DTOs
- `HttpProbeResponse` (`DTO/HttpProbeResponse.java`): `status`, `durationMs`, `headers`, `body`, `error`, `truncated`.
- No DTO drift in 2.2.0 (100% similarity).

### 3. Error bodies and reason strings verbatim
- Unchanged.

### 4. Panel flags & settings
- `actionCapable: true`, prefix: `/http-probe`.

### 5. Side effects
- In BootUI: loopback socket HTTP request on POST. In sharpit: in-process ASGI call without opening a socket.

### 6. Streams
- None.

### 7. MCP tools and CLI
- None.

### 8. Advisor rules
- Not an advisor panel.

### What sharpit must change
- **Size: S**. No contract changes.

---

## Summary Contract Drift Table

| Panel | Endpoints | DTO Count | GET Side Effects? | Optional Lib | Gatekeeper Module | Size |
|---|---|---|---|---|---|---|
| **envelope** | 4 reads, 4 actions | 4 | No | None | `engine/guard.py` | S |
| **overview** | 1 read | 2 | No | None | `engine/collectors/overview.py` | S |
| **config** | 2 reads, 2 actions | 6 | No | `pydantic-settings` | `engine/collectors/config/settings_source.py` | S |
| **mappings** | 1 read | 2 | No | None | `engine/collectors/mappings.py` | S |
| **loggers** | 1 read, 1 action | 2 | No | None | `engine/collectors/loggers.py` | S |
| **beans** | 1 read | 2 | No | None | `engine/collectors/beans.py` | S |
| **vulnerabilities** | 1 read, 1 action | 7 | No (queries on POST) | None (stdlib urllib) | `engine/collectors/vulns/` | M |
| **mcp-server** | 1 read, 2 actions | 3 | No | None | `engine/mcp.py` | M |
| **cli** | 1 read, 1 action | 2 | No | None | `engine/tools.py` | S |
| **activity** | 5 reads, 2 actions, 1 stream | 7 | No | `sqlalchemy` (optional) | `engine/sqla.py` | M |
| **http-exchanges** | 2 reads | 4 | No | None | `fastapi/capture.py` | M |
| **exceptions** | 2 reads, 2 actions, 1 stream | 4 | No | None | `fastapi/capture.py` | S |
| **sql-trace** | 1 read, 2 actions, 1 stream | 4 | No | `sqlalchemy` | `engine/sqla.py` | S |
| **log-tail** | 1 read, 1 stream | 1 | No | None | `fastapi/capture.py` | S |
| **alembic** | 2 reads, 3 actions | 4 | No (refreshes on POST) | `alembic` | `engine/collectors/alembic.py` | S |
| **database-connection-pools** | 1 read | 3 | No | `sqlalchemy` | `engine/sqla.py` | S |
| **health** | 1 read (1 check action) | 2 | No (checks on POST) | None | `engine/collectors/health.py` | S |
| **threads** | 1 read, 1 action | 3 | No | None | `engine/collectors/threads.py` | S |
| **rest-api** | 1 read, 1 action | 5 | No | None | `engine/collectors/restapi/` | M |
| **http-probe** | 1 action | 2 | No (in-process ASGI) | None | `engine/probe.py` | S |
