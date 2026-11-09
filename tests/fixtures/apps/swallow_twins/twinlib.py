"""A planted library (copied under ``site-packages/``): it logs a WARN on a database error, then re-raises (U19)."""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger("twinlib")


def count_rows(table: str) -> int:
    connection = sqlite3.connect(":memory:")
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608 - a fixed fixture name
    except sqlite3.OperationalError:
        log.warning("no such table: %s", table)
        raise
    finally:
        connection.close()
