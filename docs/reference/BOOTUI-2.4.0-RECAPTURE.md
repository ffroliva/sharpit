# BootUI 2.4.0 Recapture

The capture pipeline was rerun from the pinned `v2.4.0` source. This ledger compares every committed fixture field with the recapture. Classification: (a) the committed fixture already matched and remains unchanged; (b) the recapture reflects source or capture metadata more accurately; (c) unexplained.

## Fixture ledger

### `meta.json`

| Field | Committed | Recaptured | Classification and cause |
|---|---|---|---|
| `command` | `python scripts/capture_bootui_24.py` | `python scripts/capture_bootui.py --version 2.4.0` | (b) Records the capture command now used. This is capture metadata, so BootUI source citation does not apply. |
| `javaVersionOutput`, `jdk` | Corretto OpenJDK 25.0.3 (build 25.0.3+9-LTS) | Corretto OpenJDK 25.0.5.1 (build 25.0.5.1+2-LTS) | (b) Records the JDK present for this recapture; capture metadata, no BootUI source citation applies. |
| `mavenVersionOutput` | Maven 3.9.9, Java 25.0.3 | Maven 3.9.9, Java 25.0.5.1 | (b) Records the recapture toolchain; capture metadata, no BootUI source citation applies. |

### `panels.json`, `tools.json`, `bootui-tests.json`

No differences (a). The panel and tool payloads match exactly. The test inventory remains 1,128 classes and 10,927 methods.

### `routes.json`

| Field | Committed | Recaptured | Classification and cause |
|---|---|---|---|
| `reads`, `actions`, `starterMappingsCount`, `gaps` count, `unpanelledRoutes` count | 82, 78, 269, 76, 73 | Same | (a) Contract and route counts match. |
| `crossCheck.starterMappings[183:187]`, `gaps[50:52]`, `unpanelledRoutes[50:52]` | `DatabaseConnectionPoolsController` records precede `DataController` records | `DataController` records precede `DatabaseConnectionPoolsController` records | (b) The records are identical and are serialized in stable source-path order. BootUI mappings: `DataController.java:41,52`; `DatabaseConnectionPoolsController.java:41,46`. |
| `crossCheck.starterMappings[224:228]` | `LoggersController` GET/POST records precede `LogTailController` recent/stream records | `LogTailController` recent/stream records precede `LoggersController` GET/POST records | (b) The records are identical and are serialized in stable source-path order. BootUI mappings: `LoggersController.java:29,37`; `LogTailController.java:101,106`. |

The two record-order changes above account for the route-array field diffs; they do not add or remove mappings. No unexplained route differences remain.

### `properties.json`

The property names and `defaultValue` values are unchanged across all 209 entries. The recapture adds the generated `total` field with value `209` (b), computed from the source metadata inventory. The `defaultValueSource` differences are listed below; each (b) citation is read from the v2.4.0 Java source rather than supplied by a hand-maintained table.

| Property | Committed `defaultValueSource` | Recaptured `defaultValueSource` | Classification and cause |
|---|---|---|---|
| `bootui.activity.feed-source` | `<absent>` | `BootUiProperties.java:3227` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.max-entries` | `<absent>` | `BootUiProperties.java:3193` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.max-scheduled-task-runs` | `<absent>` | `BootUiProperties.java:3219` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.n-plus-one-threshold` | `<absent>` | `BootUiProperties.java:3207` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.persistence.buffer-max-entries` | `<absent>` | `BootUiProperties.java:3406` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.persistence.data-source-mode` | `<absent>` | `BootUiProperties.java:3374 (DataSourceMode.SHARED)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.persistence.enabled` | `<absent>` | `BootUiProperties.java:3366` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.persistence.flush-interval` | `<absent>` | `BootUiProperties.java:3399` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.persistence.retention` | `<absent>` | `BootUiProperties.java:3413` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.persistence.table-name` | `<absent>` | `BootUiProperties.java:3396` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.activity.request-slow-threshold-ms` | `<absent>` | `BootUiProperties.java:3201` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.advisors.max-retained-violations` | `<absent>` | `BootUiProperties.java:2256` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.agent.allow-in-disabled-profiles` | `<absent>` | `BootUiProperties.java:2949` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.agent.enabled` | `<absent>` | `BootUiProperties.java:2942` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.agent.mode` | `<absent>` | `BootUiProperties.java:2962` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.agent.security-sinks.request-values` | `<absent>` | `BootUiProperties.java:3064` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.ai.max-recent-chats` | `<absent>` | `BootUiProperties.java:2394` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.ai.show-content-capture-banner` | `<absent>` | `BootUiProperties.java:2399` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.ai.token-series-minutes` | `<absent>` | `BootUiProperties.java:2389` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.allow-non-localhost` | `<absent>` | `BootUiProperties.java:53` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.allowed-hosts` | `<absent>` | `BootUiProperties.java:59` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.cache.activity-capture-enabled` | `<absent>` | `BootUiProperties.java:793` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.cache.activity-max-events` | `<absent>` | `BootUiProperties.java:799` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.cache.clear-enabled` | `<absent>` | `BootUiProperties.java:785` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.claude-code.allow-raw-reveal` | `<absent>` | `BootUiProperties.java:2482` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.claude-code.enabled` | `<absent>` | `BootUiProperties.java:2439 (Mode.AUTO)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.claude-code.max-events-per-session` | `<absent>` | `BootUiProperties.java:2460` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.claude-code.max-parsed-sessions` | `<absent>` | `BootUiProperties.java:2470` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.claude-code.max-sessions` | `<absent>` | `BootUiProperties.java:2465` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.claude-code.stream-debounce` | `<absent>` | `BootUiProperties.java:2476` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.cli.enabled` | `<absent>` | `BootUiProperties.java:2715` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.cli.execution-timeout` | `BootUiProperties.java:2647 (Duration.ofSeconds(30))` | `BootUiProperties.java:2728 (McpProtocol.DEFAULT_EXECUTION_TIMEOUT_MILLIS)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.cli.max-concurrent-calls` | `BootUiProperties.java:2644` | `BootUiProperties.java:2725 (McpProtocol.DEFAULT_MAX_CONCURRENT_CALLS)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.cli.max-results` | `<absent>` | `BootUiProperties.java:2722` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.copilot.allow-raw-reveal` | `<absent>` | `BootUiProperties.java:2482` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.copilot.enabled` | `<absent>` | `BootUiProperties.java:2439 (Mode.AUTO)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.copilot.max-events-per-session` | `<absent>` | `BootUiProperties.java:2460` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.copilot.max-parsed-sessions` | `<absent>` | `BootUiProperties.java:2470` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.copilot.max-sessions` | `<absent>` | `BootUiProperties.java:2465` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.copilot.stream-debounce` | `<absent>` | `BootUiProperties.java:2476` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.dev-services.restart-enabled` | `<absent>` | `BootUiProperties.java:756` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.email.dev-trap` | `<absent>` | `BootUiProperties.java:3299` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.email.mask-content` | `<absent>` | `BootUiProperties.java:3309` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.email.max-body-length` | `<absent>` | `BootUiProperties.java:3317` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.email.max-entries` | `<absent>` | `BootUiProperties.java:3292` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.enabled` | `<absent>` | `BootUiProperties.java:38 (Mode.AUTO)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.exceptions.max-groups` | `<absent>` | `BootUiProperties.java:848` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.exceptions.max-occurrences-per-group` | `<absent>` | `BootUiProperties.java:853` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.exceptions.max-stack-frames` | `<absent>` | `BootUiProperties.java:858` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.expose-values` | `<absent>` | `BootUiProperties.java:91 (ValueExposure.MASKED)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.fault-tolerance.enabled` | `<absent>` | `BootUiProperties.java:1953` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.fault-tolerance.max-events` | `<absent>` | `BootUiProperties.java:1956` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.free-on-idle.enabled` | `<absent>` | `BootUiProperties.java:3544` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.free-on-idle.timeout` | `<absent>` | `BootUiProperties.java:3552` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.allowed-api-hosts` | `<absent>` | `BootUiProperties.java:1079` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.api-enabled` | `<absent>` | `BootUiProperties.java:1037` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.max-api-calls` | `<absent>` | `BootUiProperties.java:1074` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.max-issues` | `<absent>` | `BootUiProperties.java:1052` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.max-pull-requests` | `<absent>` | `BootUiProperties.java:1047` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.max-security-alerts` | `<absent>` | `BootUiProperties.java:1059` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.max-workflow-runs` | `<absent>` | `BootUiProperties.java:1064` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.quota-safety-threshold` | `<absent>` | `BootUiProperties.java:1069` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.github.request-timeout` | `<absent>` | `BootUiProperties.java:1042` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.graalvm.max-repository-lookups` | `<absent>` | `BootUiProperties.java:1005` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.graalvm.repository-lookup-enabled` | `<absent>` | `BootUiProperties.java:994` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.graalvm.repository-lookup-timeout` | `<absent>` | `BootUiProperties.java:999` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.heap-dump.allow-raw-download` | `<absent>` | `BootUiProperties.java:2182` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.heap-dump.capture-enabled` | `<absent>` | `BootUiProperties.java:2176` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.heap-dump.max-classes` | `<absent>` | `BootUiProperties.java:2199` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.heap-dump.max-dumps` | `<absent>` | `BootUiProperties.java:2192` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.heap-dump.output-dir` | `<absent>` | `BootUiProperties.java:2187` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.heap-dump.top-classes` | `<absent>` | `BootUiProperties.java:2204` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.http-exchanges.max-exchanges` | `<absent>` | `BootUiProperties.java:1159` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.http-exchanges.reserved-share-percent` | `<absent>` | `BootUiProperties.java:1167` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.http-sessions.max-sessions` | `<absent>` | `BootUiProperties.java:2047` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.jms.capture-message-id` | `<absent>` | `BootUiProperties.java:1807` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.jms.enabled` | `<absent>` | `BootUiProperties.java:1801` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.jms.max-entries` | `<absent>` | `BootUiProperties.java:1810` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.jms.max-message-id-length` | `<absent>` | `BootUiProperties.java:1813` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.kafka.capture-key` | `<absent>` | `BootUiProperties.java:1745` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.kafka.enabled` | `<absent>` | `BootUiProperties.java:1736` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.kafka.max-entries` | `<absent>` | `BootUiProperties.java:1750` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.kafka.max-key-length` | `<absent>` | `BootUiProperties.java:1755` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.log-tail.max-bytes` | `<absent>` | `BootUiProperties.java:1195` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mask-secrets` | `<absent>` | `BootUiProperties.java:87` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mcp.enabled` | `<absent>` | `BootUiProperties.java:2629 (Mode.OFF)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mcp.execution-timeout` | `BootUiProperties.java:2728 (McpProtocol.DEFAULT_EXECUTION_TIMEOUT_MILLIS)` | `BootUiProperties.java:2647` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mcp.max-concurrent-calls` | `BootUiProperties.java:2725 (McpProtocol.DEFAULT_MAX_CONCURRENT_CALLS)` | `BootUiProperties.java:2644` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mcp.max-results` | `<absent>` | `BootUiProperties.java:2635` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.monitoring.exclude-self` | `<absent>` | `BootUiProperties.java:2275` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mysql.max-indexes` | `<absent>` | `BootUiProperties.java:1288` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mysql.max-lock-waits` | `<absent>` | `BootUiProperties.java:1292` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mysql.max-replication-channels` | `<absent>` | `BootUiProperties.java:1294` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mysql.max-sessions` | `<absent>` | `BootUiProperties.java:1284` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mysql.max-settings` | `<absent>` | `BootUiProperties.java:1296` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mysql.max-statements` | `<absent>` | `BootUiProperties.java:1286` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.mysql.max-tables` | `<absent>` | `BootUiProperties.java:1290` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.overrides-file` | `<absent>` | `BootUiProperties.java:111` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.panels` | `BootUiProperties.java:82` | `BootUiProperties.java:115` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.path` | `<absent>` | `BootUiProperties.java:44` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.postgresql.max-indexes` | `<absent>` | `BootUiProperties.java:1213` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.postgresql.max-replicas` | `<absent>` | `BootUiProperties.java:1219` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.postgresql.max-sessions` | `<absent>` | `BootUiProperties.java:1209` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.postgresql.max-settings` | `<absent>` | `BootUiProperties.java:1221` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.postgresql.max-statements` | `<absent>` | `BootUiProperties.java:1211` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.postgresql.max-tables` | `<absent>` | `BootUiProperties.java:1215` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.postgresql.max-vacuum-tables` | `<absent>` | `BootUiProperties.java:1217` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rabbitmq.capture-correlation-id` | `<absent>` | `BootUiProperties.java:1996` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rabbitmq.enabled` | `<absent>` | `BootUiProperties.java:1988` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rabbitmq.max-correlation-id-length` | `<absent>` | `BootUiProperties.java:2007` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rabbitmq.max-entries` | `<absent>` | `BootUiProperties.java:2001` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.read-only` | `<absent>` | `BootUiProperties.java:99` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.capture-call-site` | `<absent>` | `BootUiProperties.java:1609` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.capture-headers` | `<absent>` | `BootUiProperties.java:1599` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.chatty-call-threshold` | `<absent>` | `BootUiProperties.java:1645` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.enabled` | `<absent>` | `BootUiProperties.java:1584` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.max-entries` | `<absent>` | `BootUiProperties.java:1614` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.max-header-value-length` | `<absent>` | `BootUiProperties.java:1638` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.max-uri-length` | `<absent>` | `BootUiProperties.java:1633` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.recording` | `<absent>` | `BootUiProperties.java:1591` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.reserved-share-percent` | `<absent>` | `BootUiProperties.java:1628` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.rest-client-trace.slow-call-threshold-millis` | `<absent>` | `BootUiProperties.java:1621` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.runtime-journal.enabled` | `<absent>` | `BootUiProperties.java:2827` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.security-logs.max-logs` | `<absent>` | `BootUiProperties.java:831` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.show-banner` | `<absent>` | `BootUiProperties.java:95` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.capture-call-site` | `<absent>` | `BootUiProperties.java:1386` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.capture-parameters` | `<absent>` | `BootUiProperties.java:1375` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.enabled` | `<absent>` | `BootUiProperties.java:1361` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.max-entries` | `<absent>` | `BootUiProperties.java:1391` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.max-parameter-length` | `<absent>` | `BootUiProperties.java:1414` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.max-sql-length` | `<absent>` | `BootUiProperties.java:1409` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.n-plus-one-threshold` | `<absent>` | `BootUiProperties.java:1420` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.recording` | `<absent>` | `BootUiProperties.java:1368` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.reserved-share-percent` | `<absent>` | `BootUiProperties.java:1404` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.sql-trace.slow-query-threshold-millis` | `<absent>` | `BootUiProperties.java:1397` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.startup.enabled` | `<absent>` | `BootUiProperties.java:38 (Mode.AUTO)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.telemetry.enabled` | `<absent>` | `BootUiProperties.java:2292` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.telemetry.enrich` | `<absent>` | `BootUiProperties.java:2320` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.telemetry.exclude-self-spans` | `<absent>` | `BootUiProperties.java:2312` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.telemetry.max-spans-per-trace` | `<absent>` | `BootUiProperties.java:2302` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.telemetry.max-traces` | `<absent>` | `BootUiProperties.java:2297` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.threads.capture-deadline-millis` | `<absent>` | `BootUiProperties.java:2063` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.threads.include-synchronizers` | `<absent>` | `BootUiProperties.java:2064` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.threads.max-captures` | `<absent>` | `BootUiProperties.java:2065` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.threads.max-owned-locks` | `<absent>` | `BootUiProperties.java:2062` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.threads.max-stack-depth` | `<absent>` | `BootUiProperties.java:2061` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.threads.observation-interval-millis` | `<absent>` | `BootUiProperties.java:2070` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.threads.observation-samples` | `<absent>` | `BootUiProperties.java:2069` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.threads.ttl-millis` | `<absent>` | `BootUiProperties.java:2068` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.transactions.connection-hold-threshold-millis` | `<absent>` | `BootUiProperties.java:1534` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.transactions.enabled` | `<absent>` | `BootUiProperties.java:1510` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.transactions.max-entries` | `<absent>` | `BootUiProperties.java:1522` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.transactions.recording` | `<absent>` | `BootUiProperties.java:1517` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.transactions.slow-transaction-threshold-millis` | `<absent>` | `BootUiProperties.java:1528` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.trust-container-gateway` | `<absent>` | `BootUiProperties.java:79 (Mode.OFF)` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.trusted-proxies` | `<absent>` | `BootUiProperties.java:66` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.vulnerabilities.epss-enabled` | `<absent>` | `BootUiProperties.java:921` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.vulnerabilities.max-advisories` | `<absent>` | `BootUiProperties.java:907` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.vulnerabilities.max-packages` | `<absent>` | `BootUiProperties.java:902` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.vulnerabilities.osv-enabled` | `<absent>` | `BootUiProperties.java:890` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.vulnerabilities.request-timeout` | `<absent>` | `BootUiProperties.java:895` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.websockets.capturing` | `<absent>` | `BootUiProperties.java:1864` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.websockets.enabled` | `<absent>` | `BootUiProperties.java:1861` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.websockets.max-activity-entries` | `<absent>` | `BootUiProperties.java:1876` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.websockets.max-endpoints` | `<absent>` | `BootUiProperties.java:1867` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.websockets.max-sessions` | `<absent>` | `BootUiProperties.java:1870` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.websockets.max-subscriptions` | `<absent>` | `BootUiProperties.java:1873` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |
| `bootui.websockets.max-tracked-sessions` | `<absent>` | `BootUiProperties.java:1879` | (b) Resolved from `BootUiProperties.java` at the cited field/expression line. |

These source citations cover 168 fields: 163 are newly present and five replace stale or incorrect citations. In particular, the CLI timeout and concurrent-call citations now point to the `Cli` fields (`BootUiProperties.java:2728` and `:2725`); the MCP properties resolve to their corresponding `Mcp` fields. `bootui.cli.max-*` properties remain in the inventory.

### `rule-ids.json`

| ID | Committed field/value | Recaptured field/value | Classification and BootUI source |
|---|---|---|---|
| `RAPI-DOC-003` | `retired=false`, no reason | `retired=true`; `Retired heuristic: generators can infer Java/Kotlin deprecation; static documents and filters can also supply it without an Operation annotation.` | (b) The rule returns `SKIPPED` with a retired definition; `RestApiRules.java:2373`. |
| `RAPI-ERR-011` | `retired=false`, `retiredExplanation=null` | `retired=true`; `Retired heuristic: stack-trace calls can be server-side logging; bytecode calls do not prove response exposure.` | (b) The rule's `doEvaluate` returns `SKIPPED` with the retired reason; `ExceptionHandlersDoNotExposeStackTracesRule.java:13`. |
| `RAPI-MAP-008` | `retired=false`, no reason | `retired=true`; `Retired heuristic: literal URIs identify resources; missing template variables do not establish a defect.` | (b) The `doEvaluate` result skips with this reason; `RestApiRules.java:1901`. |
| `RAPI-NAME-004` | `retired=false`, no reason | `retired=true`; `Retired heuristic: literal dotted mappings remain valid independently of implicit suffix negotiation.` | (b) The `doEvaluate` result skips with this reason; `RestApiRules.java:2128`. |
| `RAPI-DTO-004` | `Retired: Response DTO setters do not affect the HTTP contract; code style.` | `Retired heuristic: response DTO setters do not affect the HTTP contract; mutability is code style.` | (b) The Java rule body supplies the retired result; `RestApiRules.java:1364`. |
| `RAPI-ERR-002` | `Retired: throws clauses do not affect exception resolution or the HTTP contract; Java style.` | `Retired heuristic: throws clauses do not affect exception resolution or the HTTP contract.` | (b) The Java rule body supplies the retired result; `RestApiRules.java:1705`. |
| `RAPI-VALID-005` | Documentation-table retirement text | `Retired heuristic: method names and header bindings cannot establish missing retry deduplication.` | (b) The Java rule body supplies the retired result; `RestApiRules.java:2351`. |
| `RAPI-ERR-007` | Title `Correct header evidence wording; INFO retained` | Title `Fixed (Quarkus)` | (b) The v2.4.0 change table records `Fixed (Quarkus)`; `docs/REST-API-CHECKS.md:878`. |
| `RAPI-RESP-001` | Title `Narrow; MEDIUM → LOW` | Title `Fixed (Quarkus)` | (b) The v2.4.0 change table records `Fixed (Quarkus)`; `docs/REST-API-CHECKS.md:878`. |
| `RAPI-RESP-008` | Title `Reword; MEDIUM → INFO` | Title `Fixed (Quarkus)` | (b) The v2.4.0 change table records `Fixed (Quarkus)`; `docs/REST-API-CHECKS.md:878`. |
| `RAPI-VER-001` | Title `Correct signals/active stack; INFO retained` | Title `Fixed` | (b) The v2.4.0 change table records `Fixed`; `docs/REST-API-CHECKS.md:879`. |
| `RAPI-VER-006` | Title `Share corrected version signals; INFO retained` | Title `Fixed` | (b) The v2.4.0 change table records `Fixed`; `docs/REST-API-CHECKS.md:879`. |

### `rule-ids-diff.json`

| Field | Committed | Recaptured | Classification and cause |
|---|---:|---:|---|
| `docCount` | absent | 596 | (b) Count derived from the v2.4.0 documentation scan. |
| `javaCount` | absent | 571 | (b) Count derived from the v2.4.0 Java rule scan and retirement registries. |
| `unionCount` | absent | 604 | (b) Count derived from the documentation/Java ID union. |
| `inJavaOnlyCount` | 13 | 8 | (a) The committed `inJavaOnly` list was already correct and remains unchanged; the recaptured count now equals its eight entries. |

No differences are classified (c).

## v2.5.0 capture

The final repaired capture completed successfully from `v2.5.0`. It produced eight JSON fixtures: 65 panels; 116 tools; 85 reads and 78 actions; 269 starter mappings; 688 rule IDs (0 documentation-only, 32 Java-only); 212 properties; and 1,144 test classes with 11,204 test methods. The scratch capture remains outside the repository.

## Deviations and runtime scope

No BootUI behavior was adapted, so no matrix deviation row is required. No file under `src/` changed.
