"""Test ids for a parametrized ``Dialect`` that once was a bool: the ids keep their ``False`` and ``True``."""

from __future__ import annotations

from sharpit.engine.sqltext import Dialect


def dialect_id(value: object) -> str | None:
    """``True`` for MySQL text, ``False`` for any other dialect; ``None`` leaves pytest its own id for other values."""
    return str(value is Dialect.MYSQL_FAMILY) if isinstance(value, Dialect) else None
