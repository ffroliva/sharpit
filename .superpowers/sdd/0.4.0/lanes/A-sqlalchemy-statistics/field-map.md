# Field map: sqlalchemy-statistics (BootUI hibernate-statistics)

| BootUI key | Python source |
|---|---|
| `available` | `unavailableReason is null` |
| `enableAvailable` | `false` (nothing to enable: always on while SQL Trace records) |
| `unavailableReason` | the sql-trace panel switch (`panels.disabled_reason`), else SQL Trace's reason (`sqla.sql_trace_unavailable_reason`), else `null` |
| `statistics.queryExecutionCount` | lifetime SELECT statements (`SqlTraceRecorder.totals().selects`) |
| `statistics.queryExecutionMaxTime` | max SELECT `durationMillis` since the last SQL Trace clear (`totals().max_millis`) |
| `statistics.queryExecutionMaxTimeQueryString` | normalised, masked SQL of that SELECT (`totals().max_sql`); `null` before any / after clear |
| `statistics.queryCacheEnabled`, `secondLevelCacheEnabled` | `false` (SQLAlchemy has no result or second-level cache) |
| `statistics.queryCache{Hit,Miss,Put}Count`, `secondLevelCache{Hit,Miss,Put}Count` | `0` (cache disabled) |
| `statistics.secondLevelCacheRegions` | `[]` |
| `statistics.sessionOpenCount`, `sessionCloseCount`, `flushCount`, `connectCount`, `transactionCount`, `successfulTransactionCount`, `entityLoad/Fetch/Insert/Update/DeleteCount`, `collectionLoad/Fetch/Recreate/Update/RemoveCount` | `null` + reason "SQLAlchemy reports SQL statements, not ORM session or entity operations (transactions live in the transactions panel)" (`tests/fixtures/bootui/2.2.0/sqlalchemy-statistics/nullable.json`) |
| extra `statistics.statementCount` | lifetime statements, all categories |
| extra `statistics.nPlusOne` | `[{method, route, routePath, routeReason, sql, executionsPerRequest, requests, threshold}]`, at most 20; route = exchange `endpoint` else `path`; routePath = the request path (the HTTP Exchanges link filter) |
| extra `statistics.nPlusOneWindow` | `"retained SQL Trace window (<n> statements)"` |
| extra `statistics.warnings` | `["SQL Trace recording is paused: ..."]` while recording is paused, else `[]` |
