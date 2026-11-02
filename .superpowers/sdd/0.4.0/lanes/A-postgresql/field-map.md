# Lane A-postgresql BootUI 2.2.0 → sharpit 0.4.0 field map

Source: `C:\development\github\boot-ui-ref\bootui-engine\src\main\java\io\github\jdubois\bootui\core\dto\Postgres*.java` (commit `ddfcb2436`).

## `PostgresInsightReport` (`GET /sharpit/api/postgresql`, `POST /sharpit/api/postgresql/read`)

| BootUI DTO / field | JSON key | Type | Nullability / notes |
|---|---|---|---|
| `PostgresInsightReport.status` | `status` | `str` | `"NOT_READ" \| "AVAILABLE" \| "PARTIAL" \| "UNAVAILABLE" \| "DISABLED"` |
| `PostgresInsightReport.message` | `message` | `str \| None` | Status message or `None` |
| `PostgresInsightReport.readAt` | `readAt` | `int \| None` | Epoch ms; `None` before first read (documented in `nullable.json`) |
| `PostgresInsightReport.durationMillis` | `durationMillis` | `int \| None` | Collection duration ms; `None` before first read |
| `PostgresInsightReport.sourceCount` | `sourceCount` | `int` | Registered PostgreSQL engine count |
| `PostgresInsightReport.availableSources` | `availableSources` | `int` | Count of `AVAILABLE` or `PARTIAL` database entries |
| `PostgresInsightReport.limits` | `limits` | `dict` | `PostgresRowLimits`: `maxSessions`, `maxStatements`, `maxIndexes`, `maxTables`, `maxVacuumTables`, `maxReplicas`, `maxSettings` |
| `PostgresInsightReport.databases` | `databases` | `list[dict]` | `PostgresDatabaseDto[]` |
| `PostgresInsightReport.changes` | `changes` | `list[dict]` | `PostgresChangeDto[]`: `source`, `metric`, `label`, `previousValue`, `currentValue`, `delta` |
| `PostgresInsightReport.diagnostics` | `diagnostics` | `list[dict]` | `PostgresDiagnosticDto[]`: `source`, `level`, `message` |
| `PostgresInsightReport.disclaimer` | `disclaimer` | `str` | Verbatim disclaimer with `BootUI` → `sharpit` |

## `PostgresDatabaseDto`

| BootUI field | JSON key | Type | Nullability / notes |
|---|---|---|---|
| `name` | `name` | `str` | Engine registry name |
| `status` | `status` | `str` | `"AVAILABLE" \| "PARTIAL" \| "UNAVAILABLE"` |
| `unavailableReason` | `unavailableReason` | `str \| None` | `None` when available/partial |
| `databaseName` | `databaseName` | `str \| None` | `current_database()` |
| `serverVersion` | `serverVersion` | `str \| None` | Formatted server version |
| `serverVersionNum` | `serverVersionNum` | `int \| None` | `server_version_num` integer |
| `currentUser` | `currentUser` | `str \| None` | Masked under `METADATA_ONLY` |
| `inRecovery` | `inRecovery` | `bool` | `pg_is_in_recovery()` |
| `uptimeSeconds` | `uptimeSeconds` | `int \| None` | Seconds since `pg_postmaster_start_time()` |
| `statsReset` | `statsReset` | `str \| None` | ISO-8601 timestamp from `pg_stat_database.stats_reset` |
| `readAt` | `readAt` | `int \| None` | Epoch ms |
| `durationMillis` | `durationMillis` | `int \| None` | Elapsed ms for this engine |
| `sections` | `sections` | `dict[str, dict]` | Keys in `SECTION_IDS` order: `vital-signs`, `sessions`, `statements`, `indexes`, `tables`, `vacuum`, `replication`, `settings` |
| `vitalSigns` | `vitalSigns` | `dict \| None` | `PostgresVitalSignsDto` |
| `sessions` | `sessions` | `list[dict]` | `PostgresSessionDto[]` |
| `statements` | `statements` | `list[dict]` | `PostgresStatementDto[]` |
| `indexes` | `indexes` | `list[dict]` | `PostgresIndexDto[]` |
| `tables` | `tables` | `list[dict]` | `PostgresTableDto[]` |
| `vacuum` | `vacuum` | `list[dict]` | `PostgresVacuumDto[]` |
| `replication` | `replication` | `dict \| None` | `PostgresReplicationDto` |
| `settings` | `settings` | `list[dict]` | `PostgresSettingDto[]` |
| `diagnostics` | `diagnostics` | `list[dict]` | `PostgresDiagnosticDto[]` |

## Section & Row DTOs

- `PostgresSectionDto`: `id`, `title`, `status`, `available`, `unavailableReason`, `rowCount`, `limit`, `truncated`, `durationMillis`, `note`.
- `PostgresVitalSignsDto`: `databaseSizeBytes`, `databaseSizePretty`, `activeConnections`, `idleConnections`, `idleInTransactionConnections`, `waitingConnections`, `totalConnections`, `maxConnections`, `connectionUtilizationRatio`, `transactionsCommitted`, `transactionsRolledBack`, `rollbackRatio`, `blocksRead`, `blocksHit`, `cacheHitRatio`, `tuplesReturned`, `tuplesFetched`, `tuplesInserted`, `tuplesUpdated`, `tuplesDeleted`, `tempFiles`, `tempBytes`, `deadlocks`, `conflicts`, `blkReadTimeMillis`, `blkWriteTimeMillis`, `checksumFailures`, `longestTransactionSeconds`, `longestQuerySeconds`, `longestIdleInTransactionSeconds`.
- `PostgresSessionDto`: `pid`, `userName`, `applicationName`, `clientAddress`, `state`, `waitEventType`, `waitEvent`, `backendType`, `transactionAgeSeconds`, `queryAgeSeconds`, `stateAgeSeconds`, `blockingPids`, `blockedByCount`, `blockingCount`, `query`.
- `PostgresStatementDto`: `queryId`, `query`, `calls`, `totalExecTimeMillis`, `meanExecTimeMillis`, `maxExecTimeMillis`, `rows`, `sharedBlksHit`, `sharedBlksRead`, `sharedHitRatio`, `tempBlksRead`, `tempBlksWritten`, `walBytes`.
- `PostgresIndexDto`: `schema`, `tableName`, `indexName`, `indexSizeBytes`, `indexSizePretty`, `tableSizeBytes`, `indexScans`, `tuplesRead`, `tuplesFetched`, `valid`, `ready`, `primary`, `unique`, `definition`, `usageStatus`, `recommendation`.
- `PostgresTableDto`: `schema`, `tableName`, `totalSizeBytes`, `totalSizePretty`, `tableSizeBytes`, `indexesSizeBytes`, `toastSizeBytes`, `estimatedLiveRows`, `deadRows`, `deadRowRatio`, `sequentialScans`, `sequentialTuplesRead`, `indexScans`, `indexTuplesFetched`, `indexScanRatio`, `tuplesInserted`, `tuplesUpdated`, `tuplesDeleted`, `hotUpdates`, `hotUpdateRatio`.
- `PostgresVacuumDto`: `schema`, `tableName`, `liveRows`, `deadRows`, `deadRowRatio`, `estimatedThreshold`, `needsVacuum`, `lastVacuum`, `lastAutovacuum`, `lastAnalyze`, `lastAutoanalyze`, `vacuumCount`, `autovacuumCount`, `analyzeCount`, `autoanalyzeCount`, `transactionIdAge`, `freezeMaxAge`, `wraparoundRatio`, `status`, `note`.
- `PostgresReplicationDto`: `role`, `walLevel`, `replicas`, `activeSlotCount`, `inactiveSlotCount`, `maxSlotRetainedWalBytes`, `maxReplicationLagSeconds`, `lastWalReplayPaused`, `replayLagSeconds`, `note`.
- `PostgresReplicaDto`: `applicationName`, `clientAddress`, `state`, `syncState`, `writeLagSeconds`, `flushLagSeconds`, `replayLagSeconds`, `sentLagBytes`, `replayLagBytes`.
- `PostgresSettingDto`: `name`, `setting`, `unit`, `DisplayValue` (`displayValue`), `category`, `source`, `pendingRestart`, `description`.
- `PostgresChangeDto`: `source`, `metric`, `label`, `previousValue`, `currentValue`, `delta`.
- `PostgresDiagnosticDto`: `source`, `level`, `message`.
