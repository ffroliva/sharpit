"""One container serves a whole session per server (field log F16): the live oracle must not start one per row.

Mixing direct and indirect arguments in one ``parametrize`` gives the parameter function scope, and pytest then lets it
override the ``scope="session"`` of the ``server`` fixture (``_pytest/fixtures.py:769``): a container per row, CI's
``live`` job 2 h 38 min with no verdict. This runs the real oracle test in a nested session against a fake server start
and counts the starts.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.needs_sqlalchemy

ORACLE_TESTS = str(Path(__file__).parent / "live" / "test_server_oracle.py")
LEGS = ("mysql84-default", "mariadb-default")
ROWS = [f"{ORACLE_TESTS}::test_oracle_row[{leg}-{n}]" for n in (0, 1) for leg in LEGS]  # interleaved: two servers


class _FakeServers:
    """Patches the nested session's own modules once it has collected: it loads its own copy of the live conftest."""

    def __init__(self, starts: list[str]) -> None:
        self.starts = starts

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        conftest = next(p for p in session.config.pluginmanager.get_plugins() if hasattr(p, "_boot"))
        starts = self.starts

        @contextmanager
        def fake_boot(key: str) -> Iterator[Any]:
            starts.append(key)
            yield conftest.LiveServer("sqlite://", key, "fake", key)

        conftest._boot = fake_boot  # noqa: SLF001 - the one seam that starts a container
        oracle = session.items[0].module.oracle  # type: ignore[attr-defined]
        oracle.drive = lambda *_: oracle.Observed([], False, {})  # no server: only the starts are counted


@pytest.mark.timeout(300)  # the nested run collects the whole oracle corpus
def test_the_oracle_starts_one_server_per_key_for_all_its_rows(pytester: pytest.Pytester) -> None:
    starts: list[str] = []
    result = pytester.runpytest_inprocess(
        *ROWS, "--live", "-n", "0", "-p", "no:cacheprovider", "-rs", plugins=[_FakeServers(starts)]
    )
    assert result.parseoutcomes().get("passed", 0) == len(ROWS), result.stdout.str()
    assert sorted(starts) == ["mariadb", "mysql84"]
