"""Python twins of the benchmark's swallowed-error cases (D12-D15, Java D13, U17), copied into a pytester project."""

from __future__ import annotations

import logging
import sqlite3

from twinlib import count_rows

log = logging.getLogger(__name__)


def order_count() -> int:
    """U19: the library logs a WARN underneath; the application's handler still swallows."""
    try:
        return count_rows("orders")
    except Exception:  # twin: order_count
        return 0


def find_user(user_id: int) -> list[tuple[str]]:
    """U2 / D13: a database error swallowed into an empty result."""
    connection = sqlite3.connect(":memory:")
    try:
        return connection.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchall()
    except Exception:  # twin: find_user
        return []
    finally:
        connection.close()


def total_price(items: list[object]) -> int:
    """U17: the same handler swallows on every iteration of a loop."""
    total = 0
    for item in items:
        try:
            total += item.price  # type: ignore[attr-defined]
        except Exception:  # twin: total_price
            continue
    return total


def logged_order_count() -> int:
    """The handled twin: the application logs the error it absorbs."""
    try:
        return count_rows("orders")
    except Exception:  # twin: logged_order_count
        log.exception("order count failed")
        return 0
