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


class _Pool:
    """Stands in for a library owner (its module is SQLAlchemy's), whose connections the scan skips."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection


_Pool.__module__ = "sqlalchemy.pool.fake"


def test_a_connection_an_earlier_test_still_holds_is_not_counted_as_opened_before_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = sqlite3.connect(":memory:")  # an earlier test's connection on this worker, still referenced
    try:
        without_driver_modules(monkeypatch)
        assert _attached_count() == 0
    finally:
        held.close()


def test_an_earlier_connection_whose_owner_is_freed_before_the_run_is_not_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = sqlite3.connect(":memory:")
    pool = _Pool(held)
    try:
        without_driver_modules(monkeypatch)
        del pool  # the owner goes; the connection, opened before the helper, stays
        assert _attached_count() == 0
    finally:
        held.close()


def test_a_connection_opened_after_the_helper_is_still_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    without_driver_modules(monkeypatch)
    early = sqlite3.connect(":memory:")  # opened before the inner run attaches: a real early connection
    try:
        assert _attached_count() == 1
    finally:
        early.close()


def test_a_fresh_scan_an_earlier_test_cached_is_not_reused_by_the_inner_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sqlite_source, "_preexisting", 5)
    monkeypatch.setattr(sqlite_source, "_scanned_at", time.monotonic())
    without_driver_modules(monkeypatch)
    assert _attached_count() == 0


def _cache() -> tuple[object, ...]:
    return (sqlite_source._preexisting, sqlite_source._count_failed, sqlite_source._early, sqlite_source._scanned_at)


def test_the_inner_runs_scan_does_not_outlive_the_test(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (("_preexisting", 7), ("_count_failed", True), ("_early", ["m.connect"]), ("_scanned_at", 1.0)):
        monkeypatch.setattr(sqlite_source, name, value)
    before = _cache()
    with pytest.MonkeyPatch.context() as inner:
        without_driver_modules(inner)
        _attached_count()
    assert _cache() == before
