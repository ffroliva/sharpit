"""The server oracle's driver: a statement goes through a live engine with sharpit installed (design section 8, A11).

``drive`` sends text the way an application does and reads back what sharpit shows, so what the server does with a
statement is the server's own answer, never a table of ours. It tells sharpit nothing about the server: the only way
in is the wiring a host has. A worker for the planted builds: ``python -m tests.live.oracle <json>`` runs one leg on
the ``sharpit`` that ``PYTHONPATH`` finds, and prints the rows that leak.

The span is shaped like an SDK span and fed to sharpit's real processor, as ``test_a_traces_masking`` does: the SDK is
not a dependency of this repo. Its ``db.system`` is what an instrumentation would have read from the connection.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import cache
from itertools import count
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.masking import server_corpus
from tests.masking.server_corpus import ServerRow

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import otel

from .conftest import LiveServer

API = "/sharpit/api"
MYSQL_FAMILY = ("mysql", "mariadb")
_NO_BACKSLASH = "SELECT 'a\\', 'BACKSLASHVALUE', 'b'"  # no corpus row needs the backslash cut: this one does
_BSV = (  # a backslash before a quote: an escape in E'' on, in every '' off (standard_conforming_strings)
    ("SELECT 'it''s', 'BSVCONTROL'", "BSVCONTROL"),
    ("SELECT 'a\\'', 'BSVONE', 'b'", "BSVONE"),
    ("SELECT 'a\\' -- ', 'BSVTWO'", "BSVTWO"),
    ("SELECT 'a\\'' AS x, 'BSVTHREE' AS y -- '", "BSVTHREE"),
    ("SELECT '\\', 'BSVFOUR'", "BSVFOUR"),
    ("SELECT 'a\\\\', 'BSVFIVE'", "BSVFIVE"),
    ("SELECT E'a\\'', 'BSVSIX', 'b'", "BSVSIX"),
    ("SELECT 'a\\'' || 'BSVSEVEN' /* ' */", "BSVSEVEN"),
    ("SELECT $$a'$$, 'BSVEIGHT'", "BSVEIGHT"),
    ("SELECT 'a\\'b', 'BSVNINE'", "BSVNINE"),
)
HAND_ROWS = (  # no seed made these. The server's answer decides each, as with every other row
    *(ServerRow(text, "postgresql", s, marker, None, 0) for s in ("on", "off") for text, marker in _BSV),
    *(
        ServerRow(_NO_BACKSLASH, s, "NO_BACKSLASH_ESCAPES", "BACKSLASHVALUE", None, 0)
        for s in ("my84", "my80", "maria")
    ),
    # Stripping ``\`` closes ``*\/`` early and turns ``'\'`` into ``''``, matching the default reading at the marker.
    ServerRow("SELECT /* *\\/ ' */ '\\', 'ZQXJKV'", "maria", "NO_BACKSLASH_ESCAPES", "ZQXJKV", None, 0),
    ServerRow("SELECT 1 /*! , 'BANGVALUE' */", "my84", "", "BANGVALUE", None, 0),
    ServerRow("SELECT 1 /*! , 'BANGVALUE' */", "my80", "", "BANGVALUE", None, 0),
    ServerRow("SELECT 1 /*! , 'BANGVALUE' */", "maria", "", "BANGVALUE", None, 0),
    ServerRow("SELECT 1 /*M! , 'MARIAVALUE' */", "maria", "", "MARIAVALUE", None, 0),
    ServerRow("SELECT 1 AS [it's], 'SECRET'", "maria", "MSSQL", "SECRET", None, 0),  # the brief's
    # ``]]`` is a ``]`` in a MariaDB bracket: the first needs the bracket cut, the second no opener in its bracket stops
    ServerRow("SELECT 1 AS [a']]'b], 'BRACKETVALUE'", "maria", "MSSQL", "BRACKETVALUE", None, 0),
    ServerRow("SELECT 1 AS [a]]'b], 'BRACKETVALUE'", "maria", "MSSQL", "BRACKETVALUE", None, 0),
    ServerRow("WITH x$a(')') AS (SELECT 'ZQMARKA') SELECT * FROM x$a", "sqlite", "", "ZQMARKA", None, 0),
    ServerRow("SELECT 1 AS [:a(],'ZQMARKB'", "sqlite", "", "ZQMARKB", None, 0),
    ServerRow('SELECT 1 AS [@b(],"ZQMARKD"', "sqlite", "", "ZQMARKD", None, 0),
    ServerRow("WITH x﻿$a(')x,') AS (SELECT 'ZQKK') SELECT * FROM x﻿$a", "sqlite", "", "ZQKK", None, 0),
)

# (server key, session setting) -> the corpus's name of that server. A MySQL-family session is a ``sql_mode``, as the
# readings hold it; a PostgreSQL session is the value of ``standard_conforming_strings``.
LEGS: dict[tuple[str, str], str] = {
    **{("mysql84", s): "my84" for s in ("", "NO_BACKSLASH_ESCAPES", "ANSI_QUOTES")},
    **{("mysql80", s): "my80" for s in ("", "NO_BACKSLASH_ESCAPES", "ANSI_QUOTES")},
    **{("mariadb", s): "maria" for s in ("", "NO_BACKSLASH_ESCAPES", "ANSI_QUOTES", "MSSQL", "ORACLE")},
    **{("postgresql", s): "postgresql" for s in ("on", "off")},
    ("sqlite", ""): "sqlite",
}
SERVER_KEYS = dict.fromkeys(key for key, _ in LEGS)
_REAL_LEAKS = {"my84": "mysql", "my80": "mysql", "maria": "mysql", "postgresql": "postgresql", "sqlite": "sqlite"}


def rows_for(key: str, session: str) -> list[ServerRow]:
    """One leg's rows, each text once: its readings, plus the real leaks of its family, on every session it has."""
    name = LEGS[key, session]
    readings = [r for r in server_corpus.rows("reading") if (r.server, r.session) == (name, session)]
    leaks = [r for r in server_corpus.rows("real_leak") if r.server == _REAL_LEAKS[name]]
    hand = [r for r in HAND_ROWS if (r.server, r.session) == (name, session)]
    return list({r.text: r for r in (*readings, *leaks, *hand)}.values())


@dataclass(frozen=True)
class Observed:
    returned: Any  # the server's rows, or the refusal
    refused: bool
    shown: dict[str, str]  # surface -> its text, lower-cased: an ``id`` is lower-cased, and it still leaks

    def holding(self, value: str) -> list[str]:
        """The surfaces that show ``value``."""
        return [surface for surface, text in self.shown.items() if value.lower() in text]

    def returns(self, marker: str) -> bool:
        return not self.refused and marker in repr(self.returned)

    def leaks(self, marker: str) -> bool:
        return self.returns(marker) and bool(self.holding(marker))


class _Provider:
    def add_span_processor(self, processor: Any) -> None:
        pass


def _enter_session(connection: Any, family: str, session: str) -> None:
    """On the raw connection, so no listener sees it. A session setting that did not take would pass as a leg."""
    set_it, read_it = {
        "postgresql": (f"SET standard_conforming_strings = {session}", "SHOW standard_conforming_strings"),
    }.get(family, (f"SET SESSION sql_mode = '{session}'", "SELECT @@SESSION.sql_mode"))
    cursor = connection.cursor()
    cursor.execute(set_it)
    cursor.execute(read_it)
    held = str(cursor.fetchone()[0])
    connection.commit()  # PostgreSQL rolls a ``SET`` back with its transaction, and the pool rolls back on return
    cursor.close()
    assert session in held, f"{family} is on {held!r}, not {session!r}"


def _routines(engine: sa.Engine) -> list[Any]:
    """What ``CREATE`` stored, read and dropped on a raw connection: the report never sees this."""
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        where = "FROM information_schema.routines WHERE routine_schema = DATABASE()"
        cursor.execute(f"SELECT routine_definition {where}")  # noqa: S608 - two constants
        bodies = list(cursor.fetchall())
        cursor.execute(f"SELECT routine_name, routine_type {where}")  # noqa: S608 - two constants
        for name, kind in cursor.fetchall():
            quoted = name.replace("`", "``")
            cursor.execute(f"DROP {kind} `{quoted}`")
        return bodies
    finally:
        raw.close()


class _Leg:
    """One engine and one installed app. A leg outlives a row: installing per row would be most of the run."""

    def __init__(self, server: LiveServer, session: str) -> None:
        self.server = server
        self.sql = ""
        self.returned: Any = None
        self.refused = False
        # a sync route runs on worker threads, and the SQLite pool closes one thread's connection from another
        arguments = {"check_same_thread": False} if server.family == "sqlite" else {}
        self.engine = sa.create_engine(server.url, connect_args=arguments)
        if server.family in MYSQL_FAMILY:
            self._trust_function_creators()
        if session or server.family == "postgresql":
            sa.event.listen(self.engine, "connect", lambda c, _: _enter_session(c, server.family, session))
            self.engine.dispose()
        app = FastAPI()
        app.add_api_route("/run", self.run)
        self.handle = install(app, enabled="ON", show_banner=False)
        self.client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    def _trust_function_creators(self) -> None:
        """As the spike: a binary log refuses ``CREATE FUNCTION`` without it. Refused, those rows only stop counting."""
        try:
            with self.engine.connect() as connection:
                connection.exec_driver_sql("SET GLOBAL log_bin_trust_function_creators = 1")
        except sa.exc.DBAPIError as refused:
            print(f"oracle: {self.server.key}: {refused.orig}")

    def run(self) -> None:
        """Runs in a request, as a host's query does. The text stays out of the URL: a request is a surface too."""
        self.refused = False
        try:
            with self.engine.connect() as connection:
                result = connection.execution_options(no_parameters=True).exec_driver_sql(self.sql)
                self.returned = [tuple(row) for row in result.fetchall()] if result.returns_rows else []
        except sa.exc.SQLAlchemyError as refusal:
            self.refused, self.returned = True, refusal
        if self.server.family in MYSQL_FAMILY and self.sql.startswith("CREATE") and not self.refused:
            self.returned = _routines(self.engine)

    def close(self) -> None:
        self.handle.uninstall_capture()
        self.engine.dispose()


_TRACES = count(1)
_legs: dict[tuple[str, str], _Leg] = {}
_sdk = pytest.MonkeyPatch()


@cache
def _arm_spans() -> None:
    """What ``install`` looks for: an SDK imported, and a provider that takes processors. Undone by ``close``."""
    trace = ModuleType("opentelemetry.trace")
    trace._TRACER_PROVIDER = _Provider()  # type: ignore[attr-defined]  # noqa: SLF001
    _sdk.setitem(sys.modules, "opentelemetry.trace", trace)
    _sdk.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))


def _span(family: str, sql: str, trace: int) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(trace_id=trace, span_id=1),
        parent=None,
        name="SELECT",
        kind=SimpleNamespace(name="CLIENT"),
        resource=SimpleNamespace(attributes={"service.name": "oracle"}),
        instrumentation_scope=SimpleNamespace(name="tests"),
        start_time=1,
        end_time=2,
        status=SimpleNamespace(status_code=SimpleNamespace(name="OK"), description=None),
        attributes={"db.system": family, "db.statement": sql},
        events=[],
    )


def drive(server: LiveServer, session: str, sql: str) -> Observed:
    """Send ``sql`` through the leg's engine and read every surface: statement rows, totals, the DTO, a span."""
    _arm_spans()
    leg = _legs.get((server.key, session)) or _legs.setdefault((server.key, session), _Leg(server, session))
    leg.client.post(f"{API}/sql-trace/clear").raise_for_status()  # the corpus's markers repeat: a row owns its report
    leg.sql = sql
    leg.client.get("/run").raise_for_status()
    trace = next(_TRACES)
    otel.PROCESSOR.on_end(_span(server.family, sql, trace))
    report = leg.client.get(f"{API}/sql-trace")
    body = report.json()
    assert body["entries"], "the statement reached no report: this row proved nothing"
    return Observed(
        leg.returned,
        leg.refused,
        {
            "entries": json.dumps(body["entries"]).lower(),
            "topStatements": json.dumps(body["topStatements"]).lower(),
            "dto": report.text.lower(),
            "insights": leg.client.get(f"{API}/sql-trace/insights").text.lower(),
            "span": leg.client.get(f"{API}/traces/{trace:032x}").text.lower(),
        },
    )


def leaking(server: LiveServer, session: str) -> list[str]:
    """The texts of a leg that the server returned and sharpit showed."""
    rows = rows_for(server.key, session)
    return [row.text for row in rows if drive(server, session, row.text).leaks(row.marker)]


def close() -> None:
    while _legs:
        _legs.popitem()[1].close()
    _sdk.undo()
    _arm_spans.cache_clear()


if __name__ == "__main__":
    spec = json.loads(sys.argv[1])
    print(json.dumps(leaking(LiveServer(**spec["server"]), spec["session"])))
    close()
