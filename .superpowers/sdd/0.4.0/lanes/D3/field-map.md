# D3 BootUI 2.2.0 Field Map

## Alembic

No BootUI DTO drift (§15). Python source: `src/sharpit/engine/collectors/alembic.py::alembic_report`.

| BootUI field | Python source |
|---|---|
| `alembicPresent` | `alembic_report` report root |
| `configPath` | `alembic_report` report root |
| `total` | `len(files.revisions)` in `_report` |
| `heads` | `files.heads` in `_report` |
| `databases[]` | `_database` in `alembic.py` |
| `databases[].name` | `_database` |
| `databases[].currentVersion` | `_database` |
| `databases[].applied` | `_database` |
| `databases[].pending` | `_database` |
| `databases[].total` | `_database` |
| `databases[].migrations[]` | `_row` |
| `databases[].migrations[].type` | `_row` |
| `databases[].migrations[].version` | `_row` |
| `databases[].migrations[].description` | `_row` |
| `databases[].migrations[].script` | `_row` |
| `databases[].migrations[].state` | `_row` |
| `databases[].migrations[].installedBy` | `_row` (null; Alembic does not expose BootUI's installer) |
| `databases[].migrations[].installedOn` | `_row` (null; Alembic does not expose BootUI's timestamp) |
| `databases[].migrations[].installedRank` | `_row` (null; Alembic does not expose BootUI's rank) |
| `databases[].migrations[].executionTime` | `_row` (null; Alembic does not expose BootUI's duration) |
| `databases[].migrations[].checksum` | `_row` (null; Alembic does not expose BootUI's checksum) |
| `databases[].migrateEnabled` | `_database` (false; sharpit never runs migration files) |
| `databases[].migrateDisabledReason` | `_database` |
| `databases[].cleanEnabled` | `_database` (false; sharpit never runs migration files) |
| `databases[].cleanDisabledReason` | `_database` |
| `databases[].checkedAt` | `_database` |
| `databases[].unavailableReason` | `_database` |

No 2.2.0 Alembic golden fixture exists in this lane's base. No nullable additions were identified.

## Database Connection Pools

Python source: `src/sharpit/engine/collectors/pools.py::pools_report` and `::_pool_dto`; pool counters come from the
SQLAlchemy gatekeeper `sharpit.engine.sqla` and the context registry.

| BootUI field | Python source / nullable reason |
|---|---|
| `poolLibraryPresent` | `pools_report`: `sqla.sqlalchemy_module() is not None` |
| `total` | `pools_report`: number of reported pools |
| `pools[]` | `_pool_dto` |
| `pools[].beanName` | registry display name |
| `pools[].poolName` | registry display name |
| `pools[].implementation` | `_pool_dto`: `"SQLAlchemy"` |
| `pools[].jdbcUrl` | `_pool_dto`: masked registry display name |
| `pools[].username` | `_pool_dto` through masker; null when URL has no user information |
| `pools[].driverClassName` | `_pool_dto`: backend, driver, and pool class |
| `pools[].minimumIdle` | null; documented in `tests/fixtures/bootui/2.2.0/database-connection-pools/nullable.json` |
| `pools[].maximumPoolSize` | `_pool_dto`: pool size plus overflow when measurable |
| `pools[].connectionTimeoutMs` | `_pool_dto`: QueuePool timeout |
| `pools[].idleTimeoutMs` | null; documented in `nullable.json` |
| `pools[].maxLifetimeMs` | `_pool_dto`: recycle duration, or null when disabled |
| `pools[].validationTimeoutMs` | null; documented in `nullable.json` |
| `pools[].keepaliveTimeMs` | null; documented in `nullable.json` |
| `pools[].readOnly` | null; no pool-level SQLAlchemy flag, documented in `nullable.json` |
| `pools[].autoCommit` | true only for AUTOCOMMIT isolation; otherwise null, documented in `nullable.json` |
| `pools[].available` | `_pool_dto`: whether the pool exposes counters |
| `pools[].unavailableReason` | `_pool_dto`: reason for pools without counters |
| `pools[].snapshot` | `_snapshot` |
| `pools[].snapshot.timestamp` | `_snapshot` epoch milliseconds |
| `pools[].snapshot.active` | `_snapshot` checked-out counter |
| `pools[].snapshot.idle` | `_snapshot` checked-in counter |
| `pools[].snapshot.total` | `_snapshot` total counter |
| `pools[].snapshot.pending` | null; QueuePool does not expose pending checkouts, documented in `nullable.json` |

## Health

No BootUI DTO drift (§17). Python source: `src/sharpit/engine/collectors/health.py::HealthService.report`,
`HealthService.check`, and `node`.

| BootUI field | Python source |
|---|---|
| `name` | `node` / `HealthService.report` |
| `status` | `aggregate` / `HealthService.check` |
| `details` | `node` / health contributor result after masking |
| `components[]` | `HealthService._pending` / check tree |
| `components[].name` | `node` |
| `components[].status` | `node` / aggregate |
| `components[].details` | `node` |
| `components[].components` | `node` |
| `components[].available` | `node` |
| `components[].unavailableReason` | `node` |
| `components[].guidanceReason` | `_with_guidance` |
| `components[].setup` | `_with_guidance` |
| `available` | `node` / report root |
| `unavailableReason` | `node` / report root |
| `guidanceReason` | `_with_guidance` |
| `setup` | `_with_guidance` |

## Threads

No BootUI DTO drift (§18). Python source: `src/sharpit/engine/collectors/threads.py::threads_report`, `task_info`, and
the thread-row construction in `threads_report`.

| BootUI field | Python source |
|---|---|
| `available` | `threads_report` |
| `unavailableReason` | `threads_report` |
| `capturedAt` | `threads_report` epoch milliseconds |
| `totalThreads` | `threads_report` |
| `daemonThreads` | `threads_report` |
| `peakThreads` | `threads_report` |
| `startedThreadCount` | `threads_report` |
| `virtualThreadsSupported` | `threads_report` |
| `cpuTimeSupported` | `threads_report` |
| `deadlockDetected` | `threads_report` |
| `deadlockedThreadIds` | `threads_report` |
| `stateCounts[]` | `threads_report` tally |
| `stateCounts[].state` | `threads_report` tally |
| `stateCounts[].count` | `threads_report` tally |
| `threads[].id` | thread-row construction |
| `threads[].name` | `_thread_name` (masked) |
| `threads[].state` | `infer_state` / free-threaded fallback |
| `threads[].priority` | thread-row construction; `0` (unavailable in CPython) |
| `threads[].daemon` | thread-row construction |
| `threads[].virtual` | thread-row construction; false (unsupported) |
| `threads[].cpuTimeMillis` | thread-row construction; null (unavailable in CPython) |
| `threads[].userTimeMillis` | thread-row construction; null (unavailable in CPython) |
| `threads[].blockedCount` | thread-row construction; `0` (unavailable in CPython) |
| `threads[].waitedCount` | thread-row construction; `0` (unavailable in CPython) |
| `threads[].inNative` | thread-row construction; false |
| `threads[].suspended` | thread-row construction; false |
| `threads[].deadlocked` | thread-row construction; false |
| `threads[].lockName` | thread-row construction; null (not measured) |
| `threads[].lockOwnerId` | thread-row construction; null (not measured) |
| `threads[].lockOwnerName` | thread-row construction; null (not measured) |
| `threads[].stackTrace` | `_frame_text` over current Python frames; omitted under metadata-only exposure |

`tasks`, `taskCount`, and `warnings` are sharpit additions. `task_info` maps task rows; `TASK_KEYS` lists their keys.
