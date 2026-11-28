"""Isolation for tests that run the plugin in this process (``pytester.runpytest_inprocess``)."""

from __future__ import annotations

import gc
import sqlite3
import sys
from typing import Any

import pytest

from sharpit.engine.sources import sqlite as sqlite_source
from sharpit.engine.testsession import outcome


class _WithoutEarlier:
    """``gc`` as the attach scan sees it, minus the connections that existed when the helper ran.

    It holds them, so no id is reused by a connection the inner run opens.
    """

    def __init__(self) -> None:
        self._earlier = {id(o): o for o in gc.get_objects() if issubclass(type(o), sqlite3.Connection)}

    def get_objects(self) -> list[Any]:
        return [o for o in gc.get_objects() if id(o) not in self._earlier]

    def __getattr__(self, name: str) -> Any:
        return getattr(gc, name)


def without_driver_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """An in-process run shares this process's modules: a driver another test imported would add its own reason.

    So would a module holding an early ``sqlite3.connect`` alias (another test module's ``REAL_CONNECT``), and a
    connection an earlier test left open (held or awaiting collection): the attach scan ignores every connection
    that exists when this runs, and scans afresh. The cached scan is restored when the test ends.
    """
    for name in ("_preexisting", "_count_failed", "_early", "_scanned_at"):  # undo restores the cached scan
        monkeypatch.setattr(sqlite_source, name, getattr(sqlite_source, name))
    sqlite_source._scanned_at = None  # an earlier test's cached scan would skip the filtered scan
    monkeypatch.setattr(sqlite_source, "gc", _WithoutEarlier())
    for module in outcome.DRIVER_DIALECTS:
        monkeypatch.delitem(sys.modules, module, raising=False)
    for alias in sqlite_source.early_aliases():
        monkeypatch.delitem(sys.modules, alias.rpartition(".")[0], raising=False)
