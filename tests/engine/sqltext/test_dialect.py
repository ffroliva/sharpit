"""``Dialect`` and ``dialect_of_name``: a present name always resolves, an absent one does not."""

from __future__ import annotations

import pytest

from sharpit.engine.sqltext.dialect import Dialect, dialect_of_name

MAPPED = {
    "postgresql": Dialect.POSTGRESQL,
    "mysql": Dialect.MYSQL_FAMILY,
    "mariadb": Dialect.MYSQL_FAMILY,
    "sqlite": Dialect.SQLITE,
}
UNMAPPED = (
    "cockroachdb",
    "redshift",
    "yugabytedb",
    "duckdb",
    "redis",
    "mongodb",
    "mssql",
    "microsoft.sql_server",
    "oracle",
    "oracle.db",
    "other_sql",
    "",
)


def test_the_four_values_are_pinned() -> None:
    assert {d.name: d.value for d in Dialect} == {
        "POSTGRESQL": "postgresql",
        "MYSQL_FAMILY": "mysql_family",
        "SQLITE": "sqlite",
        "UNSUPPORTED": "unsupported",
    }


@pytest.mark.parametrize(("name", "expected"), MAPPED.items())
def test_name_table_maps(name: str, expected: Dialect) -> None:
    assert dialect_of_name(name) is expected


@pytest.mark.parametrize("name", UNMAPPED)
def test_name_table_unmapped_is_unsupported(name: str) -> None:
    assert dialect_of_name(name) is Dialect.UNSUPPORTED


def test_name_table_none_is_none() -> None:
    assert dialect_of_name(None) is None
