"""scripts/dev/live_fuzz.py: the runners hand the oracle what the server returned, and nothing else.

No server here: a fake cursor records what the MySQL-family runner sends, and the PostgreSQL leg runs on SQLAlchemy's
sqlite pool, which wraps its driver connection in the same ``_ConnectionFairy`` as psycopg's.
"""

import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import sqlalchemy as sa
from _load import load_script

pytestmark = pytest.mark.needs_sqlalchemy
live_fuzz = load_script("scripts/dev/live_fuzz.py")


class _Cursor:
    def __init__(self, refuse: str = "") -> None:
        self.sent: list[str] = []
        self.refuse = refuse

    def execute(self, text: str, _args: object = None) -> None:
        self.sent.append(text)
        if self.refuse and text.startswith(self.refuse):
            raise RuntimeError("refused")

    def fetchall(self) -> tuple[tuple[str], ...]:
        return (("row",),)


class _Raw:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor


def test_a_sql_bodied_routine_is_read_by_calling_it() -> None:
    """``routine_definition`` of a SQL body is its source, names included: what the routine returns is the value."""
    cursor = _Cursor()
    live_fuzz._mysql_runner(_Raw(cursor))(live_fuzz.MARIADB_ROUTINE + "SELECT 1234567 SECRET")
    assert "CALL zp()" in cursor.sent


def test_a_sql_bodied_routine_never_reads_its_definition() -> None:
    cursor = _Cursor()
    live_fuzz._mysql_runner(_Raw(cursor))(live_fuzz.MARIADB_ROUTINE + "SELECT 1234567 SECRET")
    assert not any("routine_definition" in sent for sent in cursor.sent)


def test_a_javascript_routine_is_still_read_from_its_definition() -> None:
    """MySQL's JavaScript body is a string: the definition is the value, as before."""
    cursor = _Cursor()
    live_fuzz._mysql_runner(_Raw(cursor))(live_fuzz.ROUTINE + "AS $$SECRET$$")
    assert any("routine_definition" in sent for sent in cursor.sent)


def test_a_refused_call_still_drops_the_routine() -> None:
    """A routine left behind makes every later CREATE refuse: the drop must run when the call fails."""
    cursor = _Cursor(refuse="CALL")
    with pytest.raises(RuntimeError):
        live_fuzz._mysql_runner(_Raw(cursor))(live_fuzz.MARIADB_ROUTINE + "SELECT t.x")
    assert cursor.sent[-1] == "DROP PROCEDURE zp"


def test_the_postgresql_runner_sets_autocommit_on_the_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    """On the pool's proxy the attribute never reaches the driver: one refusal would abort every later statement."""
    raws: list[Any] = []
    engine = sa.create_engine("sqlite://")
    real = engine.raw_connection

    def recorded() -> Any:
        raws.append(real())
        return raws[-1]

    monkeypatch.setattr(engine, "raw_connection", recorded)
    monkeypatch.setattr(sa, "create_engine", lambda _url: engine)

    @contextmanager
    def boot(_key: str) -> Iterator[Any]:
        yield types.SimpleNamespace(url="sqlite://", family="postgresql")

    monkeypatch.setitem(sys.modules, "tests.live.conftest", types.SimpleNamespace(_boot=boot))
    with live_fuzz.server_runner("postgresql", ""):
        assert raws[0].dbapi_connection.autocommit is True


def _echo(text: str) -> str:
    return text


def test_a_double_quoted_value_counts_on_the_mysql_family() -> None:
    """Without ANSI_QUOTES, MySQL and MariaDB read ``"..."`` as a string: a twin shown inside it is a value shown."""
    held = live_fuzz._twin_holds('SELECT "SECRET"', _echo, _echo)
    assert held is not None


def test_a_double_quoted_name_stays_out_where_quotes_name() -> None:
    held = live_fuzz._twin_holds('SELECT "SECRET"', _echo, _echo, names_quoted=True)
    assert held is None


@pytest.mark.parametrize(
    ("family", "session", "expected"),
    [
        ("mysql", "", False),
        ("mariadb", "NO_BACKSLASH_ESCAPES", False),
        ("mysql", "ANSI_QUOTES", True),
        ("mariadb", "NO_BACKSLASH_ESCAPES,ansi_quotes", True),
        ("mysql", "ANSI", True),
        ("postgresql", "off", True),
        ("sqlite", "", True),
    ],
)
def test_double_quotes_name_only_where_the_server_says(family: str, session: str, expected: bool) -> None:
    assert live_fuzz.quotes_names(family, session) is expected


@pytest.mark.parametrize("family", ["mysql", "mariadb"])
def test_the_generator_puts_a_marker_inside_double_quotes(family: str) -> None:
    """Owner 2026-11-08: a ``"..."`` value on the MySQL family is exercised by every run, not by a hand probe."""
    quoted = sum('"SECRET"' in text for text in live_fuzz.strings(family, 1, 10_000))
    assert quoted >= 100
