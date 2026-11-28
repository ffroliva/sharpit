from __future__ import annotations

import sqlite3
import time

import pytest
from tests.pytest_plugin.inprocess import without_driver_modules

from sharpit.engine.sources import sqlite as sqlite_source


def _attached_count() -> int:
    """The count the plugin's attach records, read through the public path."""
    sqlite_source.attach("t")
    try:
        return sqlite_source.preexisting_connections()
    finally:
        sqlite_source.detach("t")


def test_a_connection_an_earlier_test_still_holds_is_not_counted_as_opened_before_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = sqlite3.connect(":memory:")  # an earlier test's connection on this worker, still referenced
    try:
        without_driver_modules(monkeypatch)
        assert _attached_count() == 0
    finally:
        held.close()


def test_a_fresh_scan_an_earlier_test_cached_is_not_reused_by_the_inner_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sqlite_source, "_preexisting", 5)
    monkeypatch.setattr(sqlite_source, "_scanned_at", time.monotonic())
    without_driver_modules(monkeypatch)
    assert _attached_count() == 0


def test_the_inner_runs_scan_does_not_outlive_the_test() -> None:
    before = (sqlite_source._preexisting, sqlite_source._count_failed, sqlite_source._early, sqlite_source._scanned_at)
    with pytest.MonkeyPatch.context() as monkeypatch:
        without_driver_modules(monkeypatch)
        _attached_count()
    after = (sqlite_source._preexisting, sqlite_source._count_failed, sqlite_source._early, sqlite_source._scanned_at)
    assert after == before


def test_a_connection_freed_after_the_helper_does_not_make_the_count_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    held = sqlite3.connect(":memory:")
    without_driver_modules(monkeypatch)
    held.close()
    del held  # freed at once by reference counting: the live count drops below the helper's baseline
    assert _attached_count() == 0
