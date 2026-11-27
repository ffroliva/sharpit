"""Test modules that open a stdlib ``sqlite3`` connection close it, so no later test counts it as opened early.

The pytest plugin counts live connections when capture starts (``sqlite._count_preexisting``); a connection a test left
open makes a later in-process run report ``SQL may have run outside capture`` (the sink gate test failed on CI's last
Linux shard for this). Garbage collection is switched off while measuring, so a connection only a reference cycle keeps
alive still counts, the way it does on a runner that has not collected yet. The count is also cached for 60 s across
tests, so a scan that counted a test's own connection must not outlive that test either.
"""

import gc
import importlib.util
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest
from tests.conftest import reset_sqlite_source

from sharpit.engine.sources import sqlite

TESTS = Path(__file__).resolve().parents[1]


@contextmanager
def _counted_delta() -> Iterator[list[int]]:
    """Yields ``[connections left behind]``, filled on exit; collects afterwards so the probe leaves nothing."""
    delta = [0]
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        before = sqlite._count_preexisting()
        yield delta
        delta[0] = sqlite._count_preexisting() - before
    finally:
        if was_enabled:
            gc.enable()
        gc.collect()


def _load(rel: str) -> ModuleType:
    path = TESTS / rel
    spec = importlib.util.spec_from_file_location(f"_leakprobe_{path.stem}", path)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_importing_the_masking_property_tests_opens_no_connection() -> None:
    with _counted_delta() as delta:
        module = _load("masking/test_properties.py")
    for held in vars(module).values():
        if isinstance(held, sqlite3.Connection):
            held.close()
    assert delta[0] == 0


class _FactoryConnection(sqlite3.Connection):
    """A caller's connection factory: ``_count_preexisting`` counts subclasses of ``sqlite3.Connection`` too."""


@pytest.mark.parametrize("factory", [sqlite3.Connection, _FactoryConnection])
def test_a_scan_that_counted_a_test_connection_does_not_outlive_the_test(factory: type[sqlite3.Connection]) -> None:
    """The per-test reset keeps the 60 s scan cache; a cache that counted a closed connection must not survive it.

    ``test_console_shows_early_connections_limitation`` opens a connection before capture starts; the scan it caused
    was reused by the next in-process ``--sharpit`` run on the same worker, which then reported its evidence as
    incomplete (the baseline owner tests failed on CI's last Linux shard).
    """
    sqlite.detach_all()  # a fresh scan, the way the first attach of a worker sees the heap
    early = sqlite3.dbapi2.connect(":memory:", factory=factory)
    sqlite.attach("leak-guard")
    try:
        assert sqlite.preexisting_connections() >= 1, "precondition: the scan counted the early connection"
    finally:
        early.close()
        del early
        gc.collect()
        reset_sqlite_source()
    sqlite.attach("leak-guard")
    try:
        assert sqlite.preexisting_connections() == 0
    finally:
        reset_sqlite_source()


@pytest.mark.parametrize(
    "name",
    ["test_sqlite_bom_is_space_at_a_token_start", "test_sqlite_bom_continues_an_identifier_before_dollar_variable"],
)
def test_the_sqlite_rule_tests_close_the_connection_they_open(name: str) -> None:
    module = _load("engine/sqltext/test_rules_sqlite.py")
    with _counted_delta() as delta:
        getattr(module, name)()
    assert delta[0] == 0
