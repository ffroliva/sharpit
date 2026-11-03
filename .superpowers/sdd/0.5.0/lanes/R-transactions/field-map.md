# Transaction field map

| BootUI key | Python source |
|---|---|
| `id` | recorder counter |
| `methodName` | `call_site(None)` at begin if SQL trace call-site capture is enabled; otherwise `unknown` |
| `propagation` | `NEW` root; `PARTICIPATING` nested savepoint |
| `isolation` | `"UNKNOWN"`, never queried (BootUI's value when it cannot tell; changed in R-transactions for golden parity) |
| `status` | commit → `COMMITTED`; rollback → `ROLLED_BACK`; failed commit/orphan → `UNKNOWN` |
| `startTimestamp`, `endTimestamp`, `durationMillis` | wall-clock ns at begin/end, converted to epoch ms/millis |
| `parentId` | enclosing transaction id for savepoint; else `null` |
| `thread` | current thread name at begin |
| `traceId` | request id at begin, else `null` |
| `sqlStatementCount` | correlate SQL Trace rows at report time by connection id and time interval; zero with warning if SQL Trace off |
| `connectionCount` | `1` |
| `readOnly` | `null`; SQLAlchemy exposes no read-only intent and hot path never queries |
| `slow`, `connectionHeld` | duration against respective thresholds |
| `errorMessage` | masked failed-commit error, else `null` |
| `unknownCount`, `nestedCount`, `evicted` | recorder counters |

Nullable golden reason: `entries[].readOnly` is null because SQLAlchemy does not expose read-only intent and the hot path never queries.
