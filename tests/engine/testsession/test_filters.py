from __future__ import annotations

import pytest

from sharpit.engine.testsession.filters import FILTER_RULES, filtered_rule


@pytest.mark.parametrize(
    ("sql", "rule"),
    [
        ("PRAGMA foreign_keys=ON", "PRAGMA"),
        ("  pragma table_info(users)", "PRAGMA"),
        ("/* x */ PRAGMA journal_mode", "PRAGMA"),
        ("SELECT * FROM sqlite_master", "sqlite_schema"),
        ("select name from main.sqlite_schema where type = 'table'", "sqlite_schema"),
        ("SELECT * FROM sqlite_temp_master", "sqlite_schema"),
        ("SELECT version_num FROM alembic_version", "migration tables"),
        ("INSERT INTO alembic_version (version_num) VALUES ('1')", "migration tables"),
        ("BEGIN", "transaction control"),
        ("begin immediate", "transaction control"),
        ("COMMIT", "transaction control"),
        ("ROLLBACK TO SAVEPOINT a", "transaction control"),
        ("SAVEPOINT sa_1", "transaction control"),
        ("RELEASE SAVEPOINT sa_1", "transaction control"),
        ("SELECT * FROM users", None),
        ("SELECT pragma_name FROM users", None),
        ("INSERT INTO commits (id) VALUES (1)", None),
        ("UPDATE users SET begin_at = 1", None),
    ],
)
def test_filtered_rules_table(sql: str, rule: str | None) -> None:
    """B7: the built-in filter names the rule a statement hits."""
    assert filtered_rule(sql) == rule


def test_filter_rules_are_listed_by_name() -> None:
    assert FILTER_RULES == ("PRAGMA", "sqlite_schema", "migration tables", "transaction control")


@pytest.mark.parametrize(
    "table", ["alembic_version", "schema_migrations", "flyway_schema_history", "django_migrations", "knex_migrations"]
)
@pytest.mark.parametrize("sql", ["SELECT * FROM {}", "INSERT INTO {} (id) VALUES (1)"])
def test_migration_tables_filtered(table: str, sql: str) -> None:
    assert filtered_rule(sql.format(table)) == "migration tables"
