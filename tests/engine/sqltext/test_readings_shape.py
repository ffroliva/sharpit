"""The shape of ``READINGS``, the end state the dialect tasks (16 to 23) build. Task 12 stages ``READINGS`` (the family
reads one MySQL entry, PostgreSQL and SQLite read ``GENERIC``) and changes these expectations here, and nowhere else:
the rule-table cells in ``test_rules_table.py`` read the named constants and do not move.
"""

from __future__ import annotations

from sharpit.engine.sqltext.dialect import Dialect
from sharpit.engine.sqltext.rules import MARIADB, MYSQL_84, READINGS


def test_readings_is_not_empty() -> None:
    assert READINGS


def test_the_family_has_two_readings_and_the_others_one() -> None:
    assert [len(READINGS.get(d, ())) for d in (Dialect.MYSQL_FAMILY, Dialect.POSTGRESQL, Dialect.SQLITE)] == [2, 1, 1]


def test_unsupported_has_no_reading() -> None:
    # the design maps mssql and oracle to UNSUPPORTED: no second-hand column is built
    assert Dialect.UNSUPPORTED not in READINGS


def test_the_family_reads_mysql_then_mariadb() -> None:
    assert READINGS.get(Dialect.MYSQL_FAMILY) == (MYSQL_84, MARIADB)
