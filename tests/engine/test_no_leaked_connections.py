"""Test modules that open a stdlib ``sqlite3`` connection close it, so no later test counts it as opened early.

The pytest plugin counts live connections when capture starts (``sqlite._count_preexisting``); a connection a test left
open makes a later in-process run report ``SQL may have run outside capture`` (the sink gate test failed on CI's last
Linux shard for this). Garbage collection is switched off while measuring, so a connection only a reference cycle keeps
alive still counts, the way it does on a runner that has not collected yet.
"""

import gc
import importlib.util
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest

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


@pytest.mark.parametrize(
    "name",
    ["test_sqlite_bom_is_space_at_a_token_start", "test_sqlite_bom_continues_an_identifier_before_dollar_variable"],
)
def test_the_sqlite_rule_tests_close_the_connection_they_open(name: str) -> None:
    module = _load("engine/sqltext/test_rules_sqlite.py")
    with _counted_delta() as delta:
        getattr(module, name)()
    assert delta[0] == 0
