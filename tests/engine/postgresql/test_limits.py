from __future__ import annotations

from sharpit.engine.collectors.postgresql.limits import (
    LOCK_TIMEOUT,
    MAX_ROW_LIMIT,
    READ_BUDGET,
    STATEMENT_TIMEOUT,
    RowLimits,
    read_one_past,
)
from sharpit.settings import load_settings


def test_default_limits_match_properties_contract() -> None:
    # ported: PostgresRowLimitsTests.defaultLimitsMatchPropertiesContract
    limits = RowLimits()
    assert limits.to_dto() == {
        "maxSessions": 100,
        "maxStatements": 100,
        "maxIndexes": 500,
        "maxTables": 200,
        "maxVacuumTables": 200,
        "maxReplicas": 10,
        "maxSettings": 40,
    }
    assert (STATEMENT_TIMEOUT, LOCK_TIMEOUT, READ_BUDGET) == (5.0, 2.0, 15.0)
    assert read_one_past([1, 2, 3], 2) == ([1, 2], True)
    assert read_one_past([1, 2], 2) == ([1, 2], False)


def test_rejects_non_positive_limits() -> None:
    # ported: PostgresRowLimitsTests.rejectsNonPositiveLimits
    fields = (
        "max_sessions",
        "max_statements",
        "max_indexes",
        "max_tables",
        "max_vacuum_tables",
        "max_replicas",
        "max_settings",
    )
    rejected: list[str] = []
    for name in fields:
        try:
            RowLimits(**{name: 0})
        except ValueError:
            rejected.append(name)
    assert rejected == list(fields)


def test_rejects_integer_max_value_which_cannot_read_one_row_past_the_limit() -> None:
    # ported: PostgresRowLimitsTests.rejectsIntegerMaxValueWhichCannotReadOneRowPastTheLimit
    assert RowLimits(max_sessions=MAX_ROW_LIMIT).max_sessions == MAX_ROW_LIMIT
    too_large = False
    try:
        RowLimits(max_sessions=2_147_483_647)
    except ValueError:
        too_large = True
    assert too_large is True


def test_reads_from_sharpit_settings_and_env() -> None:
    settings = load_settings(
        {"postgresql_max_sessions": 25, "postgresql_max_indexes": 300},
        {"SHARPIT_POSTGRESQL_MAX_TABLES": "50", "SHARPIT_POSTGRESQL_MAX_SETTINGS": "15"},
    )
    limits = RowLimits.from_settings(settings)
    assert limits.to_dto() == {
        "maxSessions": 25,
        "maxStatements": 100,
        "maxIndexes": 300,
        "maxTables": 50,
        "maxVacuumTables": 200,
        "maxReplicas": 10,
        "maxSettings": 15,
    }
