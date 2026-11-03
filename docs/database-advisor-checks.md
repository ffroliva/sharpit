# Database advisor checks

The `database-advisor` panel is sharpit's port of BootUI 2.2.0's Database Advisor (`docs/DATABASE-ADVISOR-CHECKS.md`
upstream; contract `docs/reference/BOOTUI-CONTRACT-0.4-WAVE-A.md` §4). It runs on demand only: `POST
{api}/database-advisor/scan`, or `sharpit db scan` from the CLI (the scan is not an MCP tool). `GET
{api}/database-advisor` returns the last scan and never connects.

## How a scan reads the database

- Every SQLAlchemy engine sharpit has registered is read through `run_db_read(read_only=True)`: PostgreSQL in a
  verified read-only transaction, MySQL/MariaDB with the session's read-only variable, SQLite with `PRAGMA
  query_only`, each verified on the server and put back afterwards. Any other dialect, and an engine that runs in
  autocommit, is refused before a catalog statement runs; the datasource is reported `FAILED` with the reason.
- The catalog comes from the SQLAlchemy inspector for the connection's default schema: at most 300 tables, 300
  columns and 100 indexes per table, 500 rows per vendor query, inside a cooperative 20-second budget with a 5-second
  statement timeout. A bound that is reached sets `truncated`; a rule never claims an absence from a cut inventory.
  The bounds are the `SHARPIT_DATABASE_ADVISOR_MAX_*` settings.
- The driver and pool rules read the engine object (`echo`, the pool class, `pool_size`, `max_overflow`,
  `pool_recycle`, `pool_pre_ping`) and the *presence* of the URL query keys `connect_timeout`, `charset` and
  `sslmode`. A URL value is never read, and neither is the password.
- PostgreSQL and MySQL/MariaDB server limits (`max_connections`, the reserved connections, `idle_session_timeout`,
  `wait_timeout`) are read by name in the same read-only read.

## Rules

BootUI registers 48 checks. `P` marks a check sharpit ports (33); the others are dropped with the reason shown.
`Status` says which lane implements a ported check.

| Rule | Title | Family | Port | Status | Reason |
|---|---|---|---|---|---|
| DB-SCHEMA-001 | Tables without a primary key | Schema | P | implemented | |
| DB-SCHEMA-002 | Foreign-key access-path review | Schema | P | implemented | |
| DB-SCHEMA-003 | Exact duplicate index candidates | Schema | P | implemented | |
| DB-SCHEMA-004 | Foreign key column type mismatch with the referenced column | Schema | P | implemented | |
| DB-SCHEMA-005 | Unique index duplicating a proven primary-key backing index | Schema | P | implemented | |
| DB-SCHEMA-006 | Potential duplicate foreign-key definitions | Schema | P | implemented | |
| DB-SCHEMA-007 | Narrow auto-generated primary key | Schema | P | implemented | |
| DB-SCHEMA-010 | Invisible or ignored indexes | Schema | P | implemented | |
| DB-PG-001 | Invalid PostgreSQL indexes | PostgreSQL | P | implemented | |
| DB-PG-002 | PostgreSQL sequence nearing exhaustion | PostgreSQL | P | implemented | |
| DB-PG-003 | PostgreSQL NOT VALID constraint never validated | PostgreSQL | P | implemented | |
| DB-PG-004 | PostgreSQL table lacking usable replica identity | PostgreSQL | P | implemented | |
| DB-PG-005 | PostgreSQL unlogged tables | PostgreSQL | P | implemented | |
| DB-MYSQL-001 | Tables on a non-transactional storage engine | MySQL | P | implemented | |
| DB-MYSQL-002 | Tables/columns using the legacy utf8mb3 character set | MySQL | P | implemented | |
| DB-MYSQL-003 | MySQL/MariaDB AUTO_INCREMENT nearing exhaustion | MySQL | P | implemented | |
| DB-ORACLE-001 | Unusable Oracle indexes | Oracle | dropped | dropped | Oracle has no verified read-only path in sharpit (spec §5.0) |
| DB-ORACLE-002 | Disabled or unvalidated Oracle constraints | Oracle | dropped | dropped | Oracle has no verified read-only path in sharpit (spec §5.0) |
| DB-ORACLE-003 | Oracle sequence or identity generator nearing exhaustion | Oracle | dropped | dropped | Oracle has no verified read-only path in sharpit (spec §5.0) |
| DB-HIB-002 | Declared entity relation name not found in the observed schema | ORM mapping | P | implemented | |
| DB-HIB-003 | Declared column nullability differs from observed metadata | ORM mapping | P | implemented | |
| DB-HIB-004 | Declared column length exceeds observed column size | ORM mapping | P | implemented | |
| DB-HIB-005 | Declared uniqueness has no observed enforcing key | ORM mapping | P | implemented | |
| DB-HIB-006 | Declared column name not found in the observed relation | ORM mapping | P | implemented | |
| DB-HIB-007 | Declared association has no matching observed foreign key | ORM mapping | P | implemented | |
| DB-HIB-009 | IDENTITY identifier column without database-side generation | ORM mapping | P | implemented | |
| DB-HIB-010 | Declared numeric precision or scale exceeds the observed column | ORM mapping | P | implemented | |
| DB-RUNTIME-001 | SQL text variations with predicate literals | Runtime SQL | P | implemented | |
| DB-DRIVER-001 | PostgreSQL driver does not rewrite batched inserts | Driver | dropped | dropped | pgjdbc property; SQLAlchemy 2.0 batches inserts itself (insertmanyvalues) |
| DB-DRIVER-002 | MySQL Connector/J does not rewrite batched statements | Driver | dropped | dropped | Connector/J property; SQLAlchemy 2.0 batches inserts itself (insertmanyvalues) |
| DB-DRIVER-003 | MySQL Connector/J reports affected rows instead of found rows | Driver | dropped | dropped | Connector/J property; SQLAlchemy's MySQL dialects set the found-rows client flag |
| DB-DRIVER-004 | MySQL Connector/J prepared-statement cache is off or small | Driver | dropped | dropped | Connector/J property with no Python driver analogue |
| DB-DRIVER-005 | PostgreSQL driver prepared-statement cache is disabled | Driver | dropped | dropped | pgjdbc property; Python drivers do not configure it in the URL |
| DB-DRIVER-006 | PostgreSQL driver sets a savepoint before every query | Driver | dropped | dropped | pgjdbc `autosave` has no Python driver analogue |
| DB-DRIVER-007 | Engine statement logging is enabled | Driver | P | implemented | |
| DB-DRIVER-008 | PostgreSQL driver has no connect timeout | Driver | P | implemented | |
| DB-DRIVER-009 | PostgreSQL connections do not carry an application name | Driver | dropped | dropped | `application_name` is outside the URL key allow-list (spec §5.8) and is usually set through connect_args, which sharpit does not read |
| DB-POOL-001 | Connection pool can keep a connection idle longer than the server allows | Connection pool | P | implemented | |
| DB-POOL-002 | Connection pool is larger than the server's connection limit | Connection pool | P | implemented | |
| DB-POOL-003 | Connection pool has no maximum connection lifetime | Connection pool | P | implemented | |
| DB-POOL-004 | Connection pool leaves no headroom for a second instance | Connection pool | P | implemented | |
| DB-SERVER-001 | PostgreSQL does not end sessions that are idle in a transaction | Server | P | implemented | |
| DB-SERVER-002 | PostgreSQL has no statement timeout | Server | P | implemented | |
| DB-SERVER-003 | PostgreSQL autovacuum is disabled | Server | dropped | dropped | server-wide maintenance setting, not this application's use of the server; the postgresql panel shows it |
| DB-SERVER-004 | PostgreSQL `pg_stat_statements` is not available | Server | dropped | dropped | server observability, not this application's use of the server; the postgresql panel reports it |
| DB-SERVER-005 | PostgreSQL does not measure I/O time | Server | dropped | dropped | server observability (`track_io_timing`); the postgresql panel shows it |
| DB-SERVER-006 | PostgreSQL does not log slow statements | Server | dropped | dropped | server logging policy; sharpit's SQL Trace measures the application's own statements |
| DB-SERVER-007 | MySQL Performance Schema is disabled | Server | dropped | dropped | server observability; the mysql panel reports it |

## How sharpit differs from BootUI

- Driver and pool evidence is SQLAlchemy's, not JDBC's or HikariCP's: `pool_recycle` is the maximum lifetime and
  `pool_pre_ping` the check that replaces a connection the server closed (it settles DB-POOL-001 as covered).
  SQLAlchemy pools have no idle timeout and no keepalive.
- `dataSources[].identifierCase` is always `null`: the inspector does not report the server's identifier folding.
- Rule results carry the shared advisor core's `sampleLocations` and no `suppressedCount`; `suppression` is always the
  empty `AdvisorSuppressionDto.none()`.
- The scan is a CLI action (`sharpit db scan`), not an MCP tool (spec §14).
