"""Which SQL dialect a database name means. A present but unknown name is ``UNSUPPORTED`` and ends the search."""

from __future__ import annotations

from enum import Enum


class Dialect(Enum):
    POSTGRESQL = "postgresql"
    MYSQL_FAMILY = "mysql_family"
    SQLITE = "sqlite"
    UNSUPPORTED = "unsupported"


_NAMES = {
    "postgresql": Dialect.POSTGRESQL,
    "mysql": Dialect.MYSQL_FAMILY,
    "mariadb": Dialect.MYSQL_FAMILY,
    "sqlite": Dialect.SQLITE,
}


def dialect_of_name(name: str | None) -> Dialect | None:
    """``None`` for no name at all; ``UNSUPPORTED`` for any other name the table does not know."""
    return None if name is None else _NAMES.get(name, Dialect.UNSUPPORTED)
