"""The shape of ``READINGS`` as Task 12 stages it: the family reads one MySQL entry, PostgreSQL and SQLite read
``GENERIC``. The dialect tasks (16 to 23) change these expectations here, and nowhere else: the rule-table cells in
``test_rules_table.py`` read the named constants and do not move.
"""

from __future__ import annotations

import pytest

from sharpit.engine.sqltext.dialect import Dialect
from sharpit.engine.sqltext.lexer import readings
from sharpit.engine.sqltext.rules import GENERIC, MARIADB, MYSQL_84, POSTGRESQL, READINGS, SQLITE


def test_readings_is_not_empty() -> None:
    assert READINGS


def test_each_dialect_has_its_rule_readings() -> None:
    assert [len(READINGS.get(d, ())) for d in (Dialect.MYSQL_FAMILY, Dialect.POSTGRESQL, Dialect.SQLITE)] == [2, 1, 1]


def test_unsupported_has_no_reading() -> None:
    # the design maps mssql and oracle to UNSUPPORTED: no second-hand column is built
    assert Dialect.UNSUPPORTED not in READINGS


def test_the_family_reads_mysql_and_mariadb() -> None:
    assert READINGS.get(Dialect.MYSQL_FAMILY) == (MYSQL_84, MARIADB)


def test_sqlite_reads_its_own_rules() -> None:
    assert READINGS.get(Dialect.SQLITE) == (SQLITE,)


def test_postgresql_reads_postgresql() -> None:
    assert READINGS.get(Dialect.POSTGRESQL) == (POSTGRESQL,)


def test_unsupported_reads_generic() -> None:
    assert readings(Dialect.UNSUPPORTED) == (GENERIC,)


def test_a_leftover_flag_is_no_dialect() -> None:
    with pytest.raises(KeyError):
        readings(True)
