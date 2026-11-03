"""MySQL insight sections, collectors, masking and limits tests."""

from __future__ import annotations

from tests.engine.collectors.mysql.fakes import FakeMySqlConnection

from sharpit.engine.collectors.mysql.limits import RowLimits
from sharpit.engine.collectors.mysql.sections import (
    DataSourceData,
    collect_capabilities,
    collect_sessions,
    collect_statements,
    collect_tables,
    compare_changes,
)
from sharpit.engine.masking import Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)


def test_statement_text_masked() -> None:
    # ported: MySqlValuesTests.statementTextMasked
    conn = FakeMySqlConnection().with_rows(
        "STATEMENTS",
        {
            "schema_name": "app",
            "digest": "d1",
            "digest_text": "SELECT * FROM tokens WHERE secret = 'super-secret-key-123'",
            "count_star": 5,
            "sum_timer_wait": 5000,
            "avg_timer_wait": 1000,
            "max_timer_wait": 2000,
            "sum_rows_affected": 0,
            "sum_rows_sent": 5,
            "sum_rows_examined": 5,
            "sum_no_index_used": 0,
        },
    )
    data = DataSourceData("primary")
    collect_statements(conn, MASKED, RowLimits(), data)
    assert len(data.statements) == 1
    assert "super-secret-key-123" not in data.statements[0]["digestText"]
    assert "SELECT" in data.statements[0]["digestText"]


def test_session_current_statement_masked() -> None:
    # ported: MySqlValuesTests.sessionCurrentStatementMasked
    conn = FakeMySqlConnection().with_rows(
        "SESSIONS",
        {
            "id": 42,
            "user": "root",
            "host": "localhost",
            "db": "app",
            "command": "Query",
            "time": 2,
            "state": "executing",
            "info": "SELECT * FROM users WHERE password='x'",
            "current_statement": "SELECT * FROM users WHERE password='x'",
        },
    )
    data = DataSourceData("primary")
    collect_sessions(conn, MASKED, RowLimits(), data)
    assert len(data.sessions) == 1
    assert "password='x'" not in data.sessions[0]["info"]
    assert data.sessions[0]["id"] == 42


def test_row_limits_truncate_and_flag() -> None:
    # ported: MySqlRowLimitsTests.rowLimitsTruncateAndFlag
    conn = FakeMySqlConnection().with_rows(
        "TABLES",
        {
            "table_schema": "app",
            "table_name": "orders",
            "table_type": "BASE TABLE",
            "engine": "InnoDB",
            "table_rows": 10,
            "avg_row_length": 10,
            "data_length": 100,
            "index_length": 100,
            "data_free": 0,
        },
        {
            "table_schema": "app",
            "table_name": "items",
            "table_type": "BASE TABLE",
            "engine": "InnoDB",
            "table_rows": 20,
            "avg_row_length": 10,
            "data_length": 200,
            "index_length": 200,
            "data_free": 0,
        },
        {
            "table_schema": "app",
            "table_name": "customers",
            "table_type": "BASE TABLE",
            "engine": "InnoDB",
            "table_rows": 30,
            "avg_row_length": 10,
            "data_length": 300,
            "index_length": 300,
            "data_free": 0,
        },
    )
    data = DataSourceData("primary")
    section = collect_tables(conn, RowLimits(max_tables=2), data)
    assert section["status"] == "AVAILABLE"
    assert section["rowCount"] == 2
    assert section["truncated"] is True
    assert len(data.tables) == 2


def test_mariadb_capabilities_differ() -> None:
    # ported: MySqlMariaDbTests.mariaDbCapabilitiesDiffer
    maria_conn = FakeMySqlConnection(dialect="mariadb", version=(10, 6, 12)).with_rows(
        "CAPABILITIES",
        {"version": "10.6.12-MariaDB", "version_comment": "mariadb.org binary distribution", "performance_schema": 1},
    )
    maria_data = DataSourceData("primary")
    collect_capabilities(maria_conn, maria_data)
    assert maria_data.capabilities["isMariaDb"] is True
    assert "10.6.12" in maria_data.capabilities["serverVersion"]

    mysql_conn = FakeMySqlConnection(dialect="mysql", version=(8, 4, 0)).with_rows(
        "CAPABILITIES",
        {"version": "8.4.0", "version_comment": "MySQL Community Server - GPL", "performance_schema": 1},
    )
    mysql_data = DataSourceData("primary")
    collect_capabilities(mysql_conn, mysql_data)
    assert mysql_data.capabilities["isMariaDb"] is False


def test_performance_schema_off_is_a_diagnostic() -> None:
    # ported: MySqlValuesTests.performanceSchemaOffIsADiagnostic
    conn = FakeMySqlConnection().with_rows(
        "CAPABILITIES",
        {"version": "8.4.0", "version_comment": "MySQL Community Server", "performance_schema": 0},
    )
    data = DataSourceData("primary")
    collect_capabilities(conn, data)
    assert data.capabilities["performanceSchema"] is False
    assert len(data.diagnostics) >= 1
    assert any("performance_schema" in d["message"].lower() for d in data.diagnostics)


def test_changes_between_reads() -> None:
    # ported: MySqlComparisonTests.changesBetweenReads
    first = {"Threads connected": {"value": 10, "rendered": "10"}}
    second = {"Threads connected": {"value": 25, "rendered": "25"}}
    first_changes = compare_changes(None, first)
    assert first_changes == []
    second_changes = compare_changes(first, second)
    assert len(second_changes) == 1
    assert second_changes[0] == {
        "metric": "Threads connected",
        "previous": "10",
        "current": "25",
        "direction": "UP",
    }
