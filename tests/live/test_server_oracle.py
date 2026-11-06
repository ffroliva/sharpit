"""What a real server returned reaches no surface, through the real wiring (design section 8, A11).

# derived: the oracle is new in the architecture plan; BootUI's ``mysql-live`` profile is the shape it follows.
Each row runs on a live server and that server's own answer decides whether the row counts: the corpus's ``returned`` is
not read here. So PostgreSQL, which has no readings in the corpus, runs its 128 real-leak statements and its 10 hand
rows on both settings.
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
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path

import pytest
from tests.masking import sql_corpus
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
    ("postgresql", "on"): 138,
    ("postgresql", "off"): 138,
    ("sqlite", ""): 2817,
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


@pytest.mark.parametrize(
    ("key", "session", "row"), _rows()
)  # ``key`` direct: an indirect one here is a container a row
def test_oracle_row(
    key: str, live_servers: Callable[[str], LiveServer], session: str, row: ServerRow, request: pytest.FixtureRequest
) -> None:
    observed = oracle.drive(live_servers(key), session, row.text)
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


def test_a_postgresql_row_of_the_corpus_keeps_its_words(live_servers: Callable[[str], LiveServer]) -> None:
    """Anti-blanking: a row of the corpus keeps its words / non-literal structure on PostgreSQL."""
    row = next(r for r in sql_corpus.rows(7, 20, sql_corpus.POSTGRESQL) if r.plain and r.tail)
    statement = row.text.replace("FROM t", "FROM pg_catalog.pg_class LIMIT 1")
    observed = oracle.drive(live_servers("postgresql"), "on", statement)
    assert not observed.refused, f"the control row was refused: {observed.returned!r}"
    assert any("pg_catalog.pg_class" in text for text in observed.shown.values())


def test_a_sqlite_row_of_the_corpus_keeps_its_words(live_servers: Callable[[str], LiveServer]) -> None:
    """Anti-blanking, as on PostgreSQL: a row the server takes keeps its words on SQLite."""
    rows = sql_corpus.rows(7, 200, sql_corpus.POSTGRESQL)
    row = next(r for r in rows if r.plain and r.tail and "FROM t" in r.text and not set("$\\") & set(r.text))
    statement = row.text.replace("FROM t", "FROM sqlite_master LIMIT 1")
    observed = oracle.drive(live_servers("sqlite"), "", statement)
    assert not observed.refused, f"the control row was refused: {observed.returned!r}"
    assert any("sqlite_master" in text for text in observed.shown.values())


# Every surface the row reads comes from ``statement_text``: blanking ``normalize`` alone leaves them all showing.
BLANK_RENDER = Mutant(
    "render = shown(sql, relaxed, dialect, reading)", 'render = "?"', "", "", "engine/capture/statement.py"
)


@pytest.mark.parametrize("family", ["postgresql", "sqlite"])
def test_a_planted_blanking_build_fails_the_keep_row(family: str, tmp_path: Path) -> None:
    keep_row = f"test_a_{family}_row_of_the_corpus_keeps_its_words"
    copy = _scratch_copy(tmp_path)
    _mutate(copy, BLANK_RENDER)
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--live",
            f"tests/live/test_server_oracle.py::{keep_row}",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:xdist",
        ],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=2 * PLANT_SECONDS,
    )  # fmt: skip
    assert done.returncode == 1, done.stdout[-1500:]
    assert keep_row in done.stdout


# --- the planted builds: each must raise what the oracle finds, on rows the real build hides ----------------------


# MySQL text read as another family's: the bit was hard-coded ``False`` here before Task 12
WRONG_WIRED = Mutant(
    "dialect_of_name(conn.dialect.name) or Dialect.UNSUPPORTED,",
    "Dialect.POSTGRESQL,",
    "",
    "",
    "engine/sqla/listeners.py",
)
# The scanner never reads ``\`` as an escape inside a quote (field log F16, probes pg-plant and b2).
NEVER_ESCAPES = Mutant(
    'if c == "\\\\" and escaped and cursor + 1 < length:',
    "if False and cursor + 1 < length:",
    "",
    "",
)
# The hand rows ``standard_conforming_strings = off`` reads with ``\`` as a plain character, and the plant then shows.
FIVE_ON_OFF = {
    "SELECT 'a\\'', 'BSVONE', 'b'",
    "SELECT 'a\\'' AS x, 'BSVTHREE' AS y -- '",
    "SELECT E'a\\'', 'BSVSIX', 'b'",
    "SELECT 'a\\'' || 'BSVSEVEN' /* ' */",
    "SELECT 'a\\'b', 'BSVNINE'",
}
CONTROLS: dict[str, tuple[str, str, Mutant]] = {
    "scs_off_no_cut": (
        "postgresql",
        "off",
        Mutant("if rules.cut_backslash and _backslash_reads_two_ways(scan, rules):", "if False:", "", ""),
    ),
    "backslash-postgresql-on": ("postgresql", "on", NEVER_ESCAPES),
    "backslash-postgresql-off": ("postgresql", "off", NEVER_ESCAPES),
    "backslash-mysql": (
        "mysql84",
        "NO_BACKSLASH_ESCAPES",
        Mutant("if rules.cut_backslash and _backslash_reads_two_ways(scan, rules):", "if False:", "", ""),
    ),
    "dollar-mariadb": (
        "mariadb",
        "",
        Mutant("return _family_cut(scan, rules) if rules.dollar is DollarOpen.MYSQL_TAG else -1", "return -1", "", ""),
    ),
    "bracket-mssql": (
        "mariadb",
        "MSSQL",
        Mutant('rules.cut_bracket\n        and "[" in source', 'False and "[" in source', "", ""),
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
    ("key", "session", "mutant"), [pytest.param(*control, id=name) for name, control in CONTROLS.items()]
)
def test_oracle_control(
    key: str, live_servers: Callable[[str], LiveServer], session: str, mutant: Mutant, tmp_path: Path
) -> None:
    assert _gained(live_servers(key), session, mutant, tmp_path)


@pytest.mark.timeout(2 * PLANT_SECONDS)
def test_the_inverse_plant_shows_five_rows_on_off(live_servers: Callable[[str], LiveServer], tmp_path: Path) -> None:
    """A scanner that never reads ``\\`` as an escape is right on ``off`` only where ``\\`` is a plain character.

    The plant keeps the quote open on ``'a\\''``, which ``off`` closes: five hand rows show their value there (field
    log F16, probe run b2). On ``on`` the same plant shows one (``E'a\\''``), the other direction.
    """
    gained = _gained(live_servers("postgresql"), "off", NEVER_ESCAPES, tmp_path)
    assert gained == FIVE_ON_OFF


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
