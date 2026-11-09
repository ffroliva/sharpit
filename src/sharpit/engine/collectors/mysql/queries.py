"""The catalog SQL the ``mysql`` panel runs (BootUI 2.2.0 contract §6)."""

from __future__ import annotations

CAPABILITIES_SQL = (
    "SELECT @@version AS version, @@version_comment AS version_comment, @@performance_schema AS performance_schema"
)

DATABASE_SQL = "SELECT database() AS current_database"

STATUS_SQL = "SHOW GLOBAL STATUS"

SETTINGS_SQL = "SHOW GLOBAL VARIABLES"

CURATED_SETTINGS: tuple[str, ...] = (
    "autocommit",
    "binlog_format",
    "character_set_server",
    "collation_server",
    "connect_timeout",
    "default_authentication_plugin",
    "innodb_buffer_pool_instances",
    "innodb_buffer_pool_size",
    "innodb_flush_log_at_trx_commit",
    "innodb_lock_wait_timeout",
    "innodb_log_file_size",
    "interactive_timeout",
    "lock_wait_timeout",
    "log_queries_not_using_indexes",
    "long_query_time",
    "max_connections",
    "max_execution_time",
    "max_heap_table_size",
    "read_only",
    "slow_query_log",
    "sql_mode",
    "super_read_only",
    "sync_binlog",
    "table_open_cache",
    "thread_cache_size",
    "tmp_table_size",
    "transaction_isolation",
    "version",
    "version_comment",
    "version_compile_os",
    "wait_timeout",
)

SESSIONS_PFS_SQL = """
SELECT t.PROCESSLIST_ID AS id,
       t.PROCESSLIST_USER AS user,
       t.PROCESSLIST_HOST AS host,
       t.PROCESSLIST_DB AS db,
       t.PROCESSLIST_COMMAND AS command,
       t.PROCESSLIST_TIME AS time,
       t.PROCESSLIST_STATE AS state,
       t.PROCESSLIST_INFO AS info,
       s.SQL_TEXT AS current_statement
FROM performance_schema.threads t
LEFT JOIN performance_schema.events_statements_current s
  ON s.THREAD_ID = t.THREAD_ID AND s.NESTING_EVENT_LEVEL = 0
WHERE t.PROCESSLIST_ID IS NOT NULL
ORDER BY t.PROCESSLIST_TIME DESC
"""

SESSIONS_FALLBACK_SQL = """
SELECT ID AS id,
       USER AS user,
       HOST AS host,
       DB AS db,
       COMMAND AS command,
       TIME AS time,
       STATE AS state,
       INFO AS info
FROM information_schema.PROCESSLIST
ORDER BY TIME DESC
"""

STATEMENTS_SQL = """
SELECT SCHEMA_NAME AS schema_name,
       DIGEST AS digest,
       DIGEST_TEXT AS digest_text,
       COUNT_STAR AS count_star,
       SUM_TIMER_WAIT AS sum_timer_wait,
       AVG_TIMER_WAIT AS avg_timer_wait,
       MAX_TIMER_WAIT AS max_timer_wait,
       SUM_ROWS_AFFECTED AS sum_rows_affected,
       SUM_ROWS_SENT AS sum_rows_sent,
       SUM_ROWS_EXAMINED AS sum_rows_examined,
       SUM_NO_INDEX_USED AS sum_no_index_used
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
"""

INDEXES_SQL = """
SELECT TABLE_SCHEMA AS table_schema,
       TABLE_NAME AS table_name,
       INDEX_NAME AS index_name,
       NON_UNIQUE AS non_unique,
       SEQ_IN_INDEX AS seq_in_index,
       COLUMN_NAME AS column_name,
       CARDINALITY AS cardinality,
       INDEX_TYPE AS index_type
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
ORDER BY TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
"""

TABLES_SQL = """
SELECT TABLE_SCHEMA AS table_schema,
       TABLE_NAME AS table_name,
       TABLE_TYPE AS table_type,
       ENGINE AS engine,
       TABLE_ROWS AS table_rows,
       AVG_ROW_LENGTH AS avg_row_length,
       DATA_LENGTH AS data_length,
       INDEX_LENGTH AS index_length,
       DATA_FREE AS data_free
FROM information_schema.TABLES
WHERE TABLE_SCHEMA NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
ORDER BY (COALESCE(DATA_LENGTH, 0) + COALESCE(INDEX_LENGTH, 0)) DESC
"""

# MySQL 8.0+: performance_schema.data_lock_waits (information_schema.INNODB_LOCK_WAITS was removed in 8.0).
LOCK_WAITS_SQL = """
SELECT w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
       rt.trx_mysql_thread_id AS waiting_pid,
       rt.trx_query AS waiting_query,
       w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
       bt.trx_mysql_thread_id AS blocking_pid,
       bt.trx_query AS blocking_query
FROM performance_schema.data_lock_waits w
JOIN information_schema.INNODB_TRX rt ON rt.trx_id = w.REQUESTING_ENGINE_TRANSACTION_ID
JOIN information_schema.INNODB_TRX bt ON bt.trx_id = w.BLOCKING_ENGINE_TRANSACTION_ID
ORDER BY rt.trx_wait_started
"""

# MariaDB has no performance_schema.data_lock_waits; it keeps information_schema.INNODB_LOCK_WAITS.
LOCK_WAITS_MARIADB_SQL = """
SELECT w.requesting_trx_id AS waiting_trx_id,
       rt.trx_mysql_thread_id AS waiting_pid,
       rt.trx_query AS waiting_query,
       w.blocking_trx_id AS blocking_trx_id,
       bt.trx_mysql_thread_id AS blocking_pid,
       bt.trx_query AS blocking_query
FROM information_schema.INNODB_LOCK_WAITS w
JOIN information_schema.INNODB_TRX rt ON rt.trx_id = w.requesting_trx_id
JOIN information_schema.INNODB_TRX bt ON bt.trx_id = w.blocking_trx_id
ORDER BY rt.trx_wait_started
"""

REPLICATION_PFS_SQL = """
SELECT CHANNEL_NAME AS channel_name,
       SERVICE_STATE AS service_state,
       SOURCE_UUID AS source_uuid,
       LAST_ERROR_NUMBER AS last_error_number,
       LAST_ERROR_MESSAGE AS last_error_message,
       LAST_ERROR_TIMESTAMP AS last_error_timestamp
FROM performance_schema.replication_connection_status
"""
