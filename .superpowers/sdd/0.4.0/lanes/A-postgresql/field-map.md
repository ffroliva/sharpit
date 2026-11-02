# Lane A-postgresql field map: BootUI 2.2.0 DTO → sharpit source

Source: `C:\development\github\boot-ui-ref\bootui-engine\src\main\java\io\github\jdubois\bootui\core\dto\Postgres*.java`
(commit `ddfcb2436`). Keys are emitted exactly as the record components, in record order, nulls included. The sharpit
producer is `src/sharpit/engine/collectors/postgresql/` (`sections.py` for rows, `service.py` for the report); SQL is
`queries.py`. "as BootUI" = same catalog column and same null rule; a deviation is spelled out.

## `PostgresInsightReport` (`GET /sharpit/api/postgresql`, `POST /sharpit/api/postgresql/read`) — `service._report`

| Key | Source |
|---|---|
| `localOnly` | constant `true` |
| `disclaimer` | `DISCLAIMER`, verbatim |
| `status` | `NOT_READ` / `DISABLED` / `ERROR` / `PARTIAL` / `READ`, `PostgresInsightService.doRead` rules |
| `message` | BootUI messages (`BootUI`→`sharpit`); `null` on `READ` |
| `readAt` | epoch ms at the end of the read; `null` before the first read |
| `databasesRead` | number of PostgreSQL engines read (error databases included) |
| `truncated` | any database `truncated` |
| `databases` | `PostgresDatabaseDto[]` |
| `diagnostics` | `PostgresDiagnosticDto[]` (`source`, `level`, `message`): skipped non-PostgreSQL engines (INFO), unread engines (WARNING), failed engines (ERROR), every non-clean section (`<name>/<section>`) |
| `limitations` | `limitationsOf` text, `BootUI's row limit`→`sharpit's row limit` |

## `PostgresDatabaseDto` — `service._database`

| Key | Source |
|---|---|
| `name` | engine registry display name (credentials masked by `EngineRegistry`) |
| `databaseName` | `vitalSigns.databaseName` (`current_database()`), else `null` |
| `serverVersion` | `".".join(conn.dialect.server_version_info)` read inside the pinned transaction (BootUI: JDBC metadata); `null` if absent |
| `serverMajorVersion` | first element of `server_version_info`, else `-1` (as BootUI) |
| `role` | `current_user` (role probe) |
| `monitoringRole` | `pg_has_role(current_user, 'pg_read_all_stats', 'usage')` |
| `status` | `statusOf`: `ERROR` if no section `AVAILABLE`, `READ` if every section is clean and nothing truncated, else `PARTIAL`; `ERROR` for a refused/failed engine |
| `message` | `null` on a read (sharpit never runs a half-pinned read); the failure reason on an `ERROR` database (`READ_ONLY_REFUSED`, masked driver error, budget) |
| `vitalSigns`, `sections`, `sessions`, `statements`, `indexes`, `tables`, `vacuum`, `replication`, `settings` | the eight sections below |
| `changes` | `PostgresChangeDto[]` vs the previous in-memory read |
| `truncated` | any section `truncated` |

## Section and row DTOs — `sections.py`

| DTO | Keys → catalog source |
|---|---|
| `PostgresSectionDto` | `id`, `title` (BootUI titles), `status` (`AVAILABLE`/`SKIPPED`/`FAILED`), `reason` (masked), `hint`, `rowCount`, `truncated` (read one past the limit) |
| `PostgresVitalSignsDto` | `databaseName` current_database(); `cacheHitRatio` blks_hit/(hit+read); `rollbackRatio` xact_rollback/(commit+rollback); `transactionsCommitted` xact_commit; `transactionsRolledBack` xact_rollback; `connections` sum(pg_stat_database.numbackends); `maxConnections` pg_settings max_connections; `connectionUsageRatio`; `activeSessions`, `idleInTransactionSessions`, `blockedSessions`, `longestTransactionSeconds` from pg_stat_activity (null when the role is restricted); `transactionIdAge` age(datfrozenxid); `wraparoundLimit` autovacuum_freeze_max_age; `wraparoundUsageRatio`; `databaseSizeBytes` pg_database_size; `deadlocks`; `temporaryFiles` temp_files; `temporaryBytes` temp_bytes |
| `PostgresSessionDto` | `pid`, `user` usename, `applicationName` (query-text sanitised), `clientAddress` host(client_addr) (`******` under METADATA_ONLY), `state`, `waitEventType`, `waitEvent`, `blockedBy` pg_blocking_pids, `stateSeconds`/`transactionSeconds`/`querySeconds` vs clock_timestamp(), `query` (sanitised) |
| `PostgresStatementDto` | `queryId` queryid::text, `query` (sanitised), `calls`, `totalTimeMs`/`meanTimeMs`/`maxTimeMs` (`*_exec_time` or `*_time` by extension version), `rows`, `cacheHitRatio` shared_blks_hit/(hit+read) |
| `PostgresIndexDto` | `schema`, `table`, `index`, `scans` idx_scan, `tuplesRead` idx_tup_read, `sizeBytes` pg_relation_size, `unique`, `primaryKey`, `constraintBacked` |
| `PostgresTableDto` | `schema`, `table`, `totalSizeBytes`, `tableSizeBytes`, `indexSizeBytes`, `liveTuples` n_live_tup, `deadTuples` n_dead_tup, `sequentialScans`, `sequentialTuplesRead`, `indexScans`, `sequentialScanRatio` |
| `PostgresVacuumDto` | `schema`, `table`, `liveTuples`, `deadTuples`, `deadTupleRatio`, `vacuumThreshold` (floored, reloptions overrides, PG18 cap), `vacuumDue`, `autovacuumEnabled`, `lastVacuum`/`lastAutoVacuum`/`lastAnalyze`/`lastAutoAnalyze` epoch ms |
| `PostgresReplicationDto` | `inRecovery` pg_is_in_recovery(), `replicas`, `checkpointsTimed`/`checkpointsRequested`/`checkpointWriteSeconds` (pg_stat_checkpointer or pg_stat_bgwriter), `replicationSlots`, `inactiveReplicationSlots`, `walLevel` (settings), `replicasAvailable` |
| `PostgresReplicaDto` | `applicationName`, `clientAddress` (`******` under METADATA_ONLY), `state`, `syncState`, `sentLagBytes`/`flushLagBytes`/`replayLagBytes` pg_wal_lsn_diff |
| `PostgresSettingDto` | `name`, `value` (`******` under METADATA_ONLY, else cut to 120), `unit`, `source`, `note` (BootUI's curated allow-list text) |
| `PostgresChangeDto` | `metric`, `previous`, `current` (rendered), `direction` `UP`/`DOWN` |
| `PostgresDiagnosticDto` | `source`, `level`, `message` |

Nullable paths the golden check may meet as `null`: `tests/fixtures/bootui/2.2.0/postgresql/nullable.json`.
