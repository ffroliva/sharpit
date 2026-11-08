"""The twins' own suite (copied into a pytester project as ``test_twins.py``)."""

from __future__ import annotations

from twinapp import find_user, logged_order_count, order_count, total_price

LOOP = 200


def test_order_count() -> None:
    assert order_count() == 0


def test_find_user() -> None:
    assert find_user(1) == []


def test_total_price() -> None:
    assert total_price([object() for _ in range(LOOP)]) == 0


def test_logged_order_count() -> None:
    assert logged_order_count() == 0
