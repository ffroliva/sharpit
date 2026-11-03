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
  ON s.THREAD_ID = t.THREAD_ID
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

LOCK_WAITS_SQL = """
SELECT r.TRX_ID AS waiting_trx_id,
       r.TRX_MYSQL_THREAD_ID AS waiting_pid,
       r.TRX_QUERY AS waiting_query,
       b.TRX_ID AS blocking_trx_id,
       b.TRX_MYSQL_THREAD_ID AS blocking_pid,
       b.TRX_QUERY AS blocking_query
FROM sys.innodb_lock_waits
"""

REPLICATION_PFS_SQL = """
SELECT CHANNEL_NAME AS channel_name,
       SERVICE_STATE AS service_state,
       LAST_ERROR_NUMBER AS last_error_number,
       LAST_ERROR_MESSAGE AS last_error_message,
       LAST_ERROR_TIMESTAMP AS last_error_timestamp
FROM performance_schema.replication_connection_status
"""
