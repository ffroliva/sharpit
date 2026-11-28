from __future__ import annotations

import gc
import sqlite3

import pytest
from tests.pytest_plugin.inprocess import without_driver_modules

from sharpit.engine.sources import sqlite as sqlite_source


def test_a_connection_an_earlier_test_still_holds_is_not_counted_as_opened_before_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = sqlite3.connect(":memory:")  # an earlier test's connection on this worker, still referenced
    try:
        without_driver_modules(monkeypatch)
        assert sqlite_source._count_preexisting() == 0  # the scan the plugin runs on attach
    finally:
        held.close()


class _Cycle:
    def __init__(self) -> None:
        self.me = self
        self.connection = sqlite3.connect(":memory:")


def test_an_uncollected_connection_freed_before_the_run_does_not_make_the_count_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enabled = gc.isenabled()
    gc.disable()
    try:
        _Cycle()
        without_driver_modules(monkeypatch)
        gc.collect()
        assert sqlite_source._count_preexisting() == 0
    finally:
        if enabled:
            gc.enable()
