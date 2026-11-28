"""Isolation for tests that run the plugin in this process (``pytester.runpytest_inprocess``)."""

from __future__ import annotations

import gc
import sys

import pytest

from sharpit.engine.sources import sqlite as sqlite_source
from sharpit.engine.testsession import outcome


def without_driver_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """An in-process run shares this process's modules: a driver another test imported would add its own reason.

    So would a module holding an early ``sqlite3.connect`` alias (another test module's ``REAL_CONNECT``), and an
    earlier test's unclosed connection still waiting in a reference cycle: the attach scan would count it as opened
    before capture.
    """
    gc.collect()
    for module in outcome.DRIVER_DIALECTS:
        monkeypatch.delitem(sys.modules, module, raising=False)
    for alias in sqlite_source.early_aliases():
        monkeypatch.delitem(sys.modules, alias.rpartition(".")[0], raising=False)
