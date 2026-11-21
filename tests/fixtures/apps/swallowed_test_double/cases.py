"""The fixture's own suite (copied into a pytester project as ``test_double.py``)."""

from __future__ import annotations

from unittest.mock import MagicMock

from doubleapp import label, title


class Client:
    pass


def test_label_with_a_mocked_client() -> None:
    assert label(MagicMock()) == "unknown"


def test_title_with_a_real_client() -> None:
    assert title(Client()) == ""
