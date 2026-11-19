# Database efficiency

## Goal and entry

Use for repeated SQL, N+1 queries, slow database-backed requests, transaction surprises, or a database-focused review.
Load the [shared contract](README.md); the goal is confirmed application fixes, not speculative database tuning.

## Prerequisites

Confirm the relevant datasource, database engine (SQLite, PostgreSQL, MySQL), SQLAlchemy or DB-API client, SQL capture
state, representative data/request, source code, and authorization. Non-SQLAlchemy database clients or uninstrumented
connections provide partial evidence. Do not enable statistics or change SQL capture without approval.

## Investigation

| MCP tool | CLI equivalent | Read for |
| --- | --- | --- |
| `get_database_advisor_report` | `sharpit db report --json` | Cached database advisor findings and coverage |
| `get_runtime_insights` | `sharpit insights list --query all --json` | Transaction observations and SQL findings, including omitted kinds |
| `get_runtime_insight` | `sharpit insights show <id> --json` | One observation's evidence and follow-up calls |
| `get_request_profile` | `sharpit request-profile <id> --json` | SQL groups, timing, call sites, N+1 suspects, and request context |
| `get_sql_traces` | `sharpit sql traces --limit 20 --json` | Bounded retained SQL statements with timings and call sites |
| `get_transactions` | `sharpit tx list --json` | Retained transaction boundaries (when available) |
| `get_sqlalchemy_statistics` | `sharpit sqlalchemy-statistics list --json` | SQLAlchemy pool and execution counters, if enabled |
| `get_database_connection_pools` | `sharpit db pools --json` | Connection pool status and active/idle connections |
| `get_alembic_migrations` | `sharpit db alembic --json` | Applied Alembic migrations and head revisions |

1. Record SQL counts, fingerprints, affected rule/target identities, timestamps, response assertions, and workload.
   A scan summary is not the full report. Follow retained violation pages using `get_database_advisor_rule_violations`
   (`sharpit db violations <id> --scan-id <scan-id> --json`).
2. Use query `all` or the default list for transaction observations; `repeated-selects` alone filters those out.
   For repeats, narrow to query `repeated-selects`, open the observation ID, then its exemplar request ID in
   `get_request_profile`. Inspect profile source, truncation, and notes; approximate time-window correlation is
   weaker than exact ownership.
3. Locate source code from call sites and structured locations. Review query plans before adding an index. The DB-SCHEMA-002 rule is “Foreign-key access-path review”; it does not prescribe `index=True`. Check SQLAlchemy relationship loading strategies
   (`lazy="select"` vs `selectinload` or `joinedload`), unbatched write loops, sequential queries inside loops,
   column projections, pagination limits, and session lifecycle. Repetition alone does not prescribe a single fix.
4. For transaction observations, inspect actual session boundaries: `async with session.begin():` blocks, explicit
   commits, rollback triggers, and autocommit behavior. Never infer absence of work solely from the HTTP request counter.
5. If cached findings are stale or insufficient, propose `database_advisor_scan` (`sharpit db scan --json`). A named
   delegation covers only its named scan: `database_advisor_scan` contacts the database for schema and index metadata
   and needs that separate explicit approval. Rescan only within the approved scope.
6. If the hypothesis needs operational evidence, read `get_mysql_report` or `get_postgresql_report`. Raw live reads (`sharpit db mysql read --json`, `sharpit db postgres read --json`) are CLI-only actions and require explicit user approval first. Server-wide counters include other clients.
7. BootUI’s lazy-SQL-after-handler check is not applicable: sharpit reports this insight kind as `NOT_APPLICABLE` (`lazy_sql_after_handler.py`), so it cannot establish that behavior.

## Fix and verify

Validate the mechanism and read runtime impact before editing, as taught by [Verify my changes](verify-my-changes.md).
Consider a focused eager loading strategy (`selectinload` for collections, `joinedload` for many-to-one), batched writes,
or transaction scope fix only when evidence supports it. Do not mechanically add `joinedload`: on collections it may
multiply result rows and disrupt pagination. Do not hide statements or move work outside capture to improve a result.

In review-first mode propose the fix and stop. Under approved execution, add focused test assertions, reload the
application, and replay the same data/request. Require correct response contents, order, pagination, expected SQL work,
and intended transaction behavior. Compare stable rule plus target identities; Database advisor finding diffs are
useful only when their completion and limitation fields support the comparison.

## Stop and report

Report unresolved or unverified when statements were not captured, a rule failed, retention is partial, or no comparable
baseline exists. Schema migrations, index operations, dependency upgrades, and database configuration changes are
outside the ordinary code-fix scope and need separate explicit approval.
