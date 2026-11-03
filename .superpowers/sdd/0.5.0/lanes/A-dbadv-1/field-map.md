# Field map: BootUI `database-advisor` → sharpit `database-advisor` (contract Wave A §4)

| BootUI key | sharpit source |
|---|---|
| `localOnly`, `disclaimer`, `rulesEvaluated`, `violationsFound`, `severityCounts`, `scan.*`, `results`, `evidence`, `violationDetails` | F5a's advisor scan core (`engine/advisors/scan.py`), `ScanSpec("database-advisor", "sharpit Database Advisor", ...)` |
| `scan.message` (NOT_SCANNED) | BootUI's text with BootUI→sharpit (`(sharpit db scan)`) |
| `dataSourceNames` | the registered engines' display names (`EngineRegistry`: no credentials), sorted |
| `dataSources[].name` / `product` / `dialect` | engine name / `PostgreSQL`, `MySQL`, `MariaDB`, `SQLite` (else the dialect name) / `dialect.name` |
| `dataSources[].identifierCase` | always `null` (`nullable.json`): the inspector does not report identifier folding |
| `dataSources[].status` / `message` | `AVAILABLE`, `PARTIAL` (a bound reached or a table unreadable), `FAILED` with the read-only refusal, budget or first line of the driver error (masked) |
| `dataSources[].tablesAnalyzed` / `truncated` | tables read / the table, column or index bound was reached |
| `tablesAnalyzed` (top level and `scan`) | sum over datasources (scope hook count) |
| `rulesSkipped` / `rulesErrored` | rules that could judge no datasource (each an `INFO` diagnostic) / rules that raised (an `ERROR` diagnostic) |
| `truncated` | any datasource truncated |
| `diagnostics[]` (`source`, `level`, `message`) | datasource read failures (`ERROR`), catalog warnings (budget, unreadable table, server settings), bound reached (`WARNING`), skipped rules (`INFO`, source = rule id) |
| `suppression` | always `AdvisorSuppressionDto.none()`: per-finding suppression is reported through dismissals instead |
| `results[].suppressedCount` | not emitted (the shared core's `RuleResult` has `sampleLocations` instead); post-scan parity is `unverified` until G0 |
