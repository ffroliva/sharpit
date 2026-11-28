from __future__ import annotations

import gc
import sqlite3

import pytest
from tests.pytest_plugin.inprocess import without_driver_modules

from sharpit.engine.sources import sqlite as sqlite_source


class _Cycle:
    """Unreachable but not yet collected: an earlier test's unclosed connection held in a reference cycle."""

    def __init__(self) -> None:
        self.me = self
        self.connection = sqlite3.connect(":memory:")


def test_an_earlier_tests_uncollected_connection_is_not_counted_as_opened_before_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gc.disable()
    try:
        _Cycle()
        without_driver_modules(monkeypatch)
        assert sqlite_source._count_preexisting() == 0  # noqa: SLF001  # the scan the plugin runs on attach
    finally:
        gc.enable()
        gc.collect()
