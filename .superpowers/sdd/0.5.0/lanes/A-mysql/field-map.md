# Field map: `MySqlInsightReport` (`GET /mysql`, `POST /mysql/read`)

Source: `src/sharpit/engine/collectors/mysql/service.py` over SQLAlchemy engines using `sqla.run_db_read(read_only=True)`.
Contract: `docs/reference/BOOTUI-CONTRACT-0.4-WAVE-A.md` §6. Golden: `tests/fixtures/bootui/2.2.0/mysql/captured.json`.

| Key | Type | Source / value |
|---|---|---|
| `localOnly` | boolean | always `true` |
| `disclaimer` | string | BootUI standard MySQL disclaimer verbatim |
| `status` | string | `"NOT_READ"`, `"READ"`, `"PARTIAL"`, `"ERROR"`, or `"DISABLED"` |
| `message` | string \| null | overall status message; `null` on a complete read |
| `readStartedAt` | number \| null | epoch ms timestamp when the read started; `null` before first read |
| `readAt` | number \| null | epoch ms timestamp when the read completed; `null` before first read |
| `dataSourcesRead` | number | count of datasources inspected |
| `dataSources` | array | list of `MySqlDataSourceDto` |
| `diagnostics` | array | list of `MySqlDiagnosticDto(source, level, message)` |
| `limitations` | array | list of strings describing any truncated sections, budget skips or restricted privileges |
| `truncated` | boolean | `true` if any section reached its row limit |

## `MySqlDataSourceDto`

| Key | Type | Source / value |
|---|---|---|
| `name` | string | datasource/engine display name from engine registry |
| `databaseName` | string \| null | current schema from `SELECT database()` |
| `status` | string | `"READ"`, `"PARTIAL"`, or `"ERROR"` |
| `message` | string \| null | datasource-level error/warning message; `null` when clean |
| `capabilities` | object | `MySqlCapabilityDto(serverVersion, serverComment, isMariaDb, performanceSchema)` |
| `sections` | array | list of `MySqlSectionDto(id, title, status, reason, hint, rowCount, truncated)` |
| `sessions` | array | list of `MySqlSessionDto` from `performance_schema.threads` / `information_schema.PROCESSLIST` |
| `statements` | array | list of `MySqlStatementDto` from `performance_schema.events_statements_summary_by_digest` |
| `indexes` | array | list of `MySqlIndexDto` from `information_schema.STATISTICS` |
| `tables` | array | list of `MySqlTableDto` from `information_schema.TABLES` |
| `lockWaits` | array | list of `MySqlLockWaitDto` from `performance_schema.data_lock_waits` / `sys.innodb_lock_waits` |
| `replicationChannels` | array | list of `MySqlReplicationChannelDto` from `performance_schema.replication_connection_status` / `SHOW REPLICA STATUS` |
| `metrics` | array | list of `MySqlMetricDto(id, label, value, unit, scope, source)` from `SHOW GLOBAL STATUS` |
| `settings` | array | list of `MySqlSettingDto(name, value, scope, source)` from `SHOW GLOBAL VARIABLES` allow-list |
| `changes` | array | list of `MySqlChangeDto(metric, previous, current, direction)` compared against previous read |
| `truncated` | boolean | `true` if any section in this datasource was truncated |
