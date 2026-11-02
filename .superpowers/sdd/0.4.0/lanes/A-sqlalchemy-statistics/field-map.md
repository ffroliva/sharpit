# Field map: sqlalchemy-statistics (BootUI hibernate-statistics)

| BootUI key | Python source |
|---|---|
| `available` | `ctx.capture.sql_trace is not None` and `sql_trace_unavailable_reason(ctx) is None` |
| `enableAvailable` | `false` (nothing to enable: always on while SQL Trace records) |
| `unavailableReason` | SQL Trace's reason, else `null` |
| `statistics.queryExecutionCount` | lifetime SELECT statements (`SqlTraceRecorder.totals().selects`) |
| `statistics.queryExecutionMaxTime` | lifetime max `durationMillis` (`totals().max_millis`) |
| `statistics.queryExecutionMaxTimeQueryString` | normalised SQL of that statement (`totals().max_sql`); `null` before any |
| `statistics.queryCacheEnabled`, `secondLevelCacheEnabled` | `false` (SQLAlchemy has no result or second-level cache) |
| `statistics.queryCache{Hit,Miss,Put}Count`, `secondLevelCache{Hit,Miss,Put}Count` | `0` (cache disabled) |
| `statistics.secondLevelCacheRegions` | `[]` |
| `statistics.sessionOpenCount`, `sessionCloseCount`, `flushCount`, `connectCount`, `transactionCount`, `successfulTransactionCount`, `entityLoad/Fetch/Insert/Update/DeleteCount`, `collectionLoad/Fetch/Recreate/Update/RemoveCount` | `null` + reason "SQLAlchemy reports SQL statements, not ORM session or entity operations" (`tests/fixtures/bootui/2.2.0/sqlalchemy-statistics/nullable.json`) |
| extra `statistics.statementCount` | lifetime statements, all categories |
| extra `statistics.nPlusOne` | `[{method, route, routeReason, sql, executionsPerRequest, requests, threshold}]`, at most 20; route = exchange `endpoint` else `path` |
| extra `statistics.nPlusOneWindow` | `"retained SQL Trace window (<n> statements)"` |
