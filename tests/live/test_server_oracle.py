"""What a real server returned reaches no surface, through the real wiring (design section 8, A11).

# derived: the oracle is new in the architecture plan; BootUI's ``mysql-live`` profile is the shape it follows.
Each row runs on a live server and that server's own answer decides whether the row counts: the corpus's ``returned`` is
not read here. So PostgreSQL, which has no readings in the corpus, runs its 128 real-leak statements on both settings.
That leg proves no more than those statements: nothing seeded on PostgreSQL ever ran through it.

Red on today's code by design: Tasks 16 to 19 turn those rows green, and nothing is fixed or skipped here. The legs and
counts need ``-n 0``: ``test_every_session_leg_ran`` reads this process's report, and runs last (``conftest.py``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path

import pytest
from tests.masking.server_corpus import ServerRow
from tests.masking.test_gates_bite import (
    Mutant,
    _mutate,  # pyright: ignore[reportPrivateUsage]
    _scratch_copy,  # pyright: ignore[reportPrivateUsage]
)

from . import oracle
from .conftest import LiveServer

pytestmark = [pytest.mark.live, pytest.mark.needs_sqlalchemy]

ROOT = Path(__file__).resolve().parents[2]
PLANT_SECONDS = 900  # a leg twice: the base here, the plant in a child

# The rows each leg runs: each text once, so a repeated reading counts one. Pinned, so a lost leg or a shrunk corpus
# fails; nothing here is derived from the corpus it checks.
PINNED: dict[tuple[str, str], int] = {
    ("mysql84", ""): 2149,
    ("mysql84", "NO_BACKSLASH_ESCAPES"): 2150,
    ("mysql84", "ANSI_QUOTES"): 1388,
    ("mysql80", ""): 1994,
    ("mysql80", "NO_BACKSLASH_ESCAPES"): 1995,
    ("mysql80", "ANSI_QUOTES"): 1233,
    ("mariadb", ""): 1994,
    ("mariadb", "NO_BACKSLASH_ESCAPES"): 1995,
    ("mariadb", "ANSI_QUOTES"): 1233,
    ("mariadb", "MSSQL"): 1403,
    ("mariadb", "ORACLE"): 1233,
    ("postgresql", "on"): 128,
    ("postgresql", "off"): 128,
    ("sqlite", ""): 2813,
}
ROW_ID = re.compile(r"test_oracle_row\[(\w+)-(\w+)-\d+\]$")


def _leg_id(key: str, session: str) -> str:
    return f"{key}-{session or 'default'}"


def _rows() -> list[object]:
    return [
        pytest.param(key, session, row, id=f"{_leg_id(key, session)}-{number}")
        for key, session in oracle.LEGS
        for number, row in enumerate(oracle.rows_for(key, session))
    ]


@pytest.fixture(scope="module", autouse=True)
def _closed_legs() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    yield
    oracle.close()


@pytest.mark.parametrize(("server", "session", "row"), _rows(), indirect=["server"])
def test_oracle_row(server: LiveServer, session: str, row: ServerRow, request: pytest.FixtureRequest) -> None:
    observed = oracle.drive(server, session, row.text)
    request.node.user_properties.append(("returned", observed.returns(row.marker)))
    shown = observed.holding(row.marker) if observed.returns(row.marker) else []
    assert not shown, f"the server returned {row.marker!r} and these show it"


@pytest.mark.parametrize("server", [*oracle.SERVER_KEYS], indirect=True)
def test_a_refused_statement_keeps_its_value_hidden(server: LiveServer) -> None:
    """Council finding 1: a refused row never counts in ``test_oracle_row``, and a driver can quote what it refused."""
    value = "REFUSEDVALUE7Q"
    session = "on" if server.family == "postgresql" else ""
    observed = oracle.drive(server, session, f"SELECT 1 FROM WHERE '{value}'")
    assert observed.refused, f"the server took it: {observed.returned!r}"
    assert not observed.holding(value)


# --- the planted builds: each must raise what the oracle finds, on rows the real build hides ----------------------


WRONG_WIRED = Mutant("conn.dialect.name in MYSQL_DIALECTS,", "False,", "", "", "engine/sqla/listeners.py")
CONTROLS: dict[str, tuple[str, str, Mutant]] = {
    "backslash-mysql": (
        "mysql84",
        "NO_BACKSLASH_ESCAPES",
        Mutant("if _backslash_reads_two_ways(scan, mysql):", "if False:", "", ""),
    ),
    "dollar-mariadb": ("mariadb", "", Mutant("return _family_cut(scan) if mysql else -1", "return -1", "", "")),
    "bracket-mssql": (
        "mariadb",
        "MSSQL",
        Mutant('if "[" in source and any(kind == _LITERAL', "if False and any(kind == _LITERAL", "", ""),
    ),
}


def _gained(server: LiveServer, session: str, mutant: Mutant, tmp: Path) -> set[str]:
    """The rows the plant leaks and the real build does not. The real build is red already: leaking proves nothing."""
    _mutate(_scratch_copy(tmp), mutant)
    spec = json.dumps({"server": asdict(server), "session": session})
    env = {**os.environ, "PYTHONPATH": str(tmp / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-m", "tests.live.oracle", spec],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=PLANT_SECONDS,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-2000:]
    return set(json.loads(done.stdout.strip().splitlines()[-1])) - set(oracle.leaking(server, session))


@pytest.mark.timeout(2 * PLANT_SECONDS)
@pytest.mark.parametrize("server", ["mysql84"], indirect=True)
def test_a_wrong_wired_dialect_fails_the_oracle(server: LiveServer, tmp_path: Path) -> None:
    assert _gained(server, "", WRONG_WIRED, tmp_path)


@pytest.mark.timeout(2 * PLANT_SECONDS)
@pytest.mark.parametrize(
    ("server", "session", "mutant"),
    [pytest.param(*control, id=name) for name, control in CONTROLS.items()],
    indirect=["server"],
)
def test_oracle_control(server: LiveServer, session: str, mutant: Mutant, tmp_path: Path) -> None:
    assert _gained(server, session, mutant, tmp_path)


# --- every leg ran: a skip of a row is this failing, so the live job cannot pass on a server that never answered ------


def _counted(config: pytest.Config) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    assert reporter is not None, "no report in this process: run the oracle with -n 0"
    ran: dict[tuple[str, str], int] = {}
    returned: dict[tuple[str, str], int] = {}
    for report in (*reporter.stats.get("passed", ()), *reporter.stats.get("failed", ())):
        found = ROW_ID.search(report.nodeid)
        if report.when == "call" and found:
            leg = found[1], "" if found[2] == "default" else found[2]
            ran[leg] = ran.get(leg, 0) + 1
            returned[leg] = returned.get(leg, 0) + bool(dict(report.user_properties).get("returned"))
    return ran, returned


@pytest.mark.parametrize(("key", "session"), PINNED, ids=[_leg_id(*leg) for leg in PINNED])
def test_every_session_leg_ran(key: str, session: str, request: pytest.FixtureRequest) -> None:
    ran, returned = _counted(request.config)
    assert ran.get((key, session), 0) == PINNED[key, session]
    assert returned.get((key, session), 0) > 0, "no row returned its marker: the leg proved nothing"
