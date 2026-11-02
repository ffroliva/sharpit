"""The catalog SQL the ``postgresql`` panel runs, ported from BootUI ``engine/postgres/*Collector.java`` (2.2.0).

List queries have no ``limit`` here: ``sections.read_list`` appends ``limit <max + 1>`` itself. No text may contain
``%``: ``exec_driver_sql`` hands it to psycopg, which reads ``%`` as a placeholder (BootUI's
``state like 'idle in transaction%'`` is spelled as an ``in`` list for that reason).
"""

from __future__ import annotations

import re

# PostgresInsightService.readRole
ROLE_SQL = "select current_user as role_name, pg_has_role(current_user, 'pg_read_all_stats', 'usage') as monitoring"

# PostgresVitalSignsCollector.DATABASE_SQL
DATABASE_SQL = """
select current_database() as database_name,
       pg_database_size(current_database()) as database_size,
       d.xact_commit as xact_commit,
       d.xact_rollback as xact_rollback,
       d.blks_read as blks_read,
       d.blks_hit as blks_hit,
       (select sum(numbackends)::int from pg_stat_database) as backends,
       d.deadlocks as deadlocks,
       d.temp_files as temp_files,
       d.temp_bytes as temp_bytes,
       age(p.datfrozenxid) as xid_age,
       (select setting::bigint from pg_settings where name = 'autovacuum_freeze_max_age') as freeze_max_age,
       (select setting::int from pg_settings where name = 'max_connections') as max_connections
from pg_stat_database d
join pg_database p on p.oid = d.datid
where d.datname = current_database()
"""

# PostgresVitalSignsCollector.ACTIVITY_SQL
ACTIVITY_SQL = """
select (count(*) filter (where state = 'active'))::int as active_sessions,
       (count(*) filter (where state in ('idle in transaction', 'idle in transaction (aborted)')))::int
           as idle_in_transaction,
       (count(*) filter (where wait_event_type = 'Lock'))::int as blocked_sessions,
       max(extract(epoch from (clock_timestamp() - xact_start))) as longest_transaction_seconds
from pg_stat_activity
where backend_type = 'client backend'
  and datname = current_database()
"""

# PostgresSessionCollector.SQL
SESSIONS_SQL = """
select a.pid as pid,
       a.usename as user_name,
       a.application_name as application_name,
       host(a.client_addr) as client_address,
       a.state as state,
       a.wait_event_type as wait_event_type,
       a.wait_event as wait_event,
       (select string_agg(blocker::text, ', ') from unnest(pg_blocking_pids(a.pid)) as blocker) as blocked_by,
       extract(epoch from (clock_timestamp() - a.state_change)) as state_seconds,
       extract(epoch from (clock_timestamp() - a.xact_start)) as transaction_seconds,
       extract(epoch from (clock_timestamp() - a.query_start)) as query_seconds,
       a.query as query
from pg_stat_activity a
where a.backend_type = 'client backend'
  and a.datname = current_database()
order by (a.state = 'active') desc nulls last,
         coalesce(a.xact_start, a.query_start) asc nulls last,
         a.pid asc
"""

# PostgresStatementCollector.EXTENSION_SQL
EXTENSION_SQL = """
select (select c.oid::regclass::text
          from pg_class c
          join pg_extension e on e.extname = 'pg_stat_statements' and e.extnamespace = c.relnamespace
         where c.relname = 'pg_stat_statements') as relation,
       (select count(*) from pg_attribute a
          join pg_class c on c.oid = a.attrelid and c.relname = 'pg_stat_statements'
          join pg_extension e on e.extname = 'pg_stat_statements' and e.extnamespace = c.relnamespace
         where a.attname = 'total_exec_time' and not a.attisdropped)::int as exec_naming
"""

# PostgresStatementCollector.RELATION_NAME: the catalog-rendered name, interpolated only when it has this shape
_RELATION_NAME = re.compile(r'(?:[a-z_][a-z0-9_$]*|"(?:[^"]|"")+")(?:\.(?:[a-z_][a-z0-9_$]*|"(?:[^"]|"")+"))?')


def statement_sql(relation: str | None, exec_naming: bool) -> str:
    """PostgresStatementCollector.sql: pg_stat_statements 1.8 renamed the timing columns to ``*_exec_time``."""
    view = relation if relation is not None and _RELATION_NAME.fullmatch(relation) else "pg_stat_statements"
    total, mean, peak = (
        ("total_exec_time", "mean_exec_time", "max_exec_time")
        if exec_naming
        else ("total_time", "mean_time", "max_time")
    )
    return (
        f"select s.queryid::text as query_id, s.query as query, s.calls as calls, s.{total} as total_time,"
        f" s.{mean} as mean_time, s.{peak} as max_time, s.rows as rows_returned,"
        " s.shared_blks_hit as shared_blks_hit, s.shared_blks_read as shared_blks_read"
        f" from {view} s"
        " join pg_database d on d.oid = s.dbid and d.datname = current_database()"
        f" order by s.{total} desc nulls last"
    )


# PostgresIndexCollector.SQL
INDEXES_SQL = """
select s.schemaname as schema_name, s.relname as table_name, s.indexrelname as index_name,
       s.idx_scan as scans, s.idx_tup_read as tuples_read,
       pg_relation_size(s.indexrelid) as size_bytes,
       i.indisunique as is_unique, i.indisprimary as is_primary,
       exists (select 1 from pg_constraint c where c.conindid = s.indexrelid) as constraint_backed
from pg_stat_user_indexes s
join pg_index i on i.indexrelid = s.indexrelid
order by s.idx_scan asc nulls first, size_bytes desc
"""

# PostgresTableCollector.SQL
TABLES_SQL = """
select schemaname as schema_name, relname as table_name,
       pg_total_relation_size(relid) as total_size,
       pg_table_size(relid) as table_size,
       pg_indexes_size(relid) as index_size,
       n_live_tup as live_tuples, n_dead_tup as dead_tuples,
       seq_scan as sequential_scans, seq_tup_read as sequential_tuples,
       idx_scan as index_scans
from pg_stat_user_tables
order by total_size desc
"""

# PostgresVacuumCollector.SQL
VACUUM_SQL = """
select s.schemaname as schema_name, s.relname as table_name,
       s.n_live_tup as live_tuples, s.n_dead_tup as dead_tuples,
       (select option_value from pg_options_to_table(c.reloptions)
          where option_name = 'autovacuum_vacuum_threshold') as rel_threshold,
       (select option_value from pg_options_to_table(c.reloptions)
          where option_name = 'autovacuum_vacuum_scale_factor') as rel_scale_factor,
       (select option_value from pg_options_to_table(c.reloptions)
          where option_name = 'autovacuum_vacuum_max_threshold') as rel_max_threshold,
       (select option_value from pg_options_to_table(c.reloptions)
          where option_name = 'autovacuum_enabled') as rel_autovacuum_enabled,
       s.last_vacuum, s.last_autovacuum, s.last_analyze, s.last_autoanalyze
from pg_stat_user_tables s join pg_class c on c.oid = s.relid
order by s.n_dead_tup desc nulls last
"""

# PostgresReplicationCollector
RECOVERY_SQL = (
    "select pg_is_in_recovery() as in_recovery,"
    " (to_regclass('pg_catalog.pg_stat_checkpointer') is not null) as has_checkpointer"
)
REPLICAS_SQL = """
select application_name, client_addr::text as client_addr, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) as sent_lag,
       pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) as flush_lag,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) as replay_lag
from pg_stat_replication
order by application_name
"""
SLOTS_SQL = """
select (count(*))::int as slots,
       (count(*) filter (where not active))::int as inactive_slots
from pg_replication_slots
"""


def checkpoint_sql(has_checkpointer: bool) -> str:
    """PostgresReplicationCollector.checkpointSql: PostgreSQL 17 moved the counters to ``pg_stat_checkpointer``."""
    if has_checkpointer:
        return (
            "select num_timed as checkpoints_timed, num_requested as checkpoints_requested,"
            " write_time as write_time from pg_stat_checkpointer"
        )
    return (
        "select checkpoints_timed as checkpoints_timed, checkpoints_req as checkpoints_requested,"
        " checkpoint_write_time as write_time from pg_stat_bgwriter"
    )


# PostgresSettingsCollector.NOTABLE_SETTINGS (the timeouts sharpit pins are deliberately absent)
NOTABLE_SETTINGS: dict[str, str] = {
    "autovacuum": "Off means routine vacuum and analyze never run; anti-wraparound vacuum still does.",
    "autovacuum_analyze_scale_factor": "Share of a table that must change before ANALYZE runs.",
    "autovacuum_analyze_threshold": "Fixed row count added to the ANALYZE scale factor.",
    "autovacuum_freeze_max_age": "The transaction-id age that forces an anti-wraparound vacuum.",
    "autovacuum_vacuum_scale_factor": "Share of a table that must be dead before VACUUM runs.",
    "autovacuum_vacuum_threshold": "Fixed dead-row count added to the VACUUM scale factor.",
    "autovacuum_vacuum_max_threshold": (
        "PostgreSQL 18 and later: the cap the scale factor may not push the VACUUM threshold past."
    ),
    "checkpoint_timeout": "How often a time-triggered checkpoint runs.",
    "default_statistics_target": "How much detail ANALYZE collects for the planner.",
    "effective_cache_size": "The planner's estimate of the cache available to one query.",
    "fsync": "Turning fsync off trades crash safety for speed.",
    "full_page_writes": "Protects against torn pages after a crash.",
    "log_min_duration_statement": "The slow-query log threshold.",
    "maintenance_work_mem": "Memory available to VACUUM, ANALYZE and index builds.",
    "max_connections": "The hard ceiling on concurrent backends.",
    "max_wal_size": "WAL volume that forces a checkpoint before the timeout.",
    "random_page_cost": "The planner's index-versus-sequential-scan trade-off.",
    "shared_buffers": "PostgreSQL's own buffer cache size.",
    "synchronous_commit": "Whether COMMIT waits for WAL to reach durable storage.",
    "track_io_timing": "Off means per-statement I/O time is not measured at all.",
    "wal_level": "Determines what replication and recovery the WAL can support.",
    "work_mem": "Memory per sort or hash before it spills to temporary files.",
}
SETTINGS_SQL = (
    "select name, setting, unit, source from pg_settings where name in ("
    + ", ".join(f"'{name}'" for name in NOTABLE_SETTINGS)
    + ") order by name"
)
