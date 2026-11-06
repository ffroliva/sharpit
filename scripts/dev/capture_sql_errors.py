"""Capture real SQL error text from live drivers into ``tests/fixtures/sql_errors``.

Nothing here is hand-written error text: each case drives a failing statement through SQLAlchemy (or
straight through the DBAPI) against a live server, and writes what the driver and SQLAlchemy produced.
Only machine-specific paths and names are replaced afterwards.

The driver packages are test-only; run this in a throwaway environment, never add them to pyproject.toml::

    uv run --no-project --with sqlalchemy --with psycopg2-binary --with "psycopg[binary]" --with asyncpg \\
        --with pymysql --with mysqlclient --with aiomysql --with aiosqlite \\
        python scripts/dev/capture_sql_errors.py --pg-port 5432 --mysql-port 3306

A server whose port is not given is skipped (its drivers are then not in the manifest). PostgreSQL needs a
user ``postgres`` without a password, MySQL a ``root`` without one, and the script creates database ``sqlerr``.
Markers are derived from the driver and case name, so a rerun writes the same markers.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import logging
import platform
import re
import shutil
import socket
import sqlite3
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "fixtures" / "sql_errors"
CLOSER = "]\n(Background on x"
CREATE = "CREATE TABLE u (id INTEGER PRIMARY KEY, name VARCHAR(200) UNIQUE, secret TEXT)"


@dataclass(frozen=True)
class Driver:
    name: str
    flavor: str  # sqlite | postgresql | mysql
    url: str  # SQLAlchemy URL template: {port}, {path}
    module: str
    is_async: bool = False
    placeholder: str = "%s"  # the DBAPI's own placeholder, for the raw cases


DRIVERS = [
    Driver("sqlite3", "sqlite", "sqlite+pysqlite:///{path}", "sqlite3", placeholder="?"),
    Driver("aiosqlite", "sqlite", "sqlite+aiosqlite:///{path}", "aiosqlite", True, "?"),
    Driver("psycopg2", "postgresql", "postgresql+psycopg2://postgres@127.0.0.1:{port}/sqlerr", "psycopg2"),
    Driver("psycopg", "postgresql", "postgresql+psycopg://postgres@127.0.0.1:{port}/sqlerr", "psycopg"),
    Driver("asyncpg", "postgresql", "postgresql+asyncpg://postgres@127.0.0.1:{port}/sqlerr", "asyncpg", True, "$1"),
    Driver("pymysql", "mysql", "mysql+pymysql://root@127.0.0.1:{port}/sqlerr", "pymysql"),
    Driver("mysqlclient", "mysql", "mysql+mysqldb://root@127.0.0.1:{port}/sqlerr", "MySQLdb"),
    Driver("aiomysql", "mysql", "mysql+aiomysql://root@127.0.0.1:{port}/sqlerr", "aiomysql", True),
]


@dataclass
class Case:
    name: str
    sql: str
    marker: str
    params: Any = field(default_factory=dict)
    hide: bool = False
    log: bool = False
    pre: list[str] = field(default_factory=list)  # driver SQL run first on the same connection
    ok_first: list[str] = field(default_factory=list)  # statements that succeed before the failing one
    seed_name: str | None = None  # the name the seed row holds (the unique clash)
    only: str | None = None  # restrict to one flavor


def mk(driver: Driver, case: str, part: str = "") -> str:
    """A generated, searchable marker; the same on every run."""
    return "mk" + hashlib.sha1(f"{driver.name}/{case}/{part}".encode()).hexdigest()[:10]


def cases(d: Driver) -> list[Case]:
    def n(case: str, part: str = "") -> str:
        return mk(d, case, part)

    long_lits = ", ".join(f"'{n('long_statement')}{i}'" for i in range(1, 4000))
    many = [
        {"i": 100 + i, "n": n("many_params") if i == 0 else f"{n('many_params')}-{i}", "s": f"s{i}"} for i in range(40)
    ]
    ins = "INSERT INTO u VALUES (:i, :n, :s)"
    return [
        Case("unique_params", ins, n("unique_params"), {"i": 2, "n": n("unique_params"), "s": n("unique_params", "s")}),
        Case(
            "hide_parameters",
            f"INSERT INTO u VALUES (:i, :n, '{n('hide_parameters', 'lit')}')",
            n("hide_parameters", "lit"),
            {"i": 2, "n": n("hide_parameters")},
            hide=True,
            seed_name=n("hide_parameters"),
        ),
        Case(
            "syntax_inline_literal",
            f"SELECT name FROM u WHERE name = '{n('syntax_inline_literal')}' AND",
            n("syntax_inline_literal"),
        ),
        Case(
            "syntax_mid_literal",
            f"SELECT name FROM u WHERE AND name = '{n('syntax_mid_literal')}'",
            n("syntax_mid_literal"),
        ),
        Case(
            "bracket_syntax",
            f"SELECT [name], name[1] FROM u WHERE name = '{n('bracket_syntax')}' AND",
            n("bracket_syntax"),
        ),
        Case(
            "bracket_block",
            f"{ins} -- arr[1] [bracket]",
            n("bracket_block"),
            {"i": 2, "n": n("bracket_block"), "s": "s"},
        ),
        Case(
            "closer_in_param",
            ins,
            n("closer_in_param"),
            {"i": 2, "n": n("closer_in_param") + CLOSER, "s": n("closer_in_param", "s") + CLOSER},
            seed_name=n("closer_in_param") + CLOSER,
        ),
        Case(
            "closer_in_literal",
            f"INSERT INTO u VALUES (2, :n, '{n('closer_in_literal')}{CLOSER}')",
            n("closer_in_literal"),
            {"n": n("closer_in_literal", "n")},
        ),
        Case(
            "sql_marker_in_param",
            ins,
            n("sql_marker_in_param"),
            {"i": 2, "n": n("sql_marker_in_param") + " [SQL: x", "s": "s"},
            seed_name=n("sql_marker_in_param") + " [SQL: x",
        ),
        Case(
            "sql_marker_in_literal",
            f"INSERT INTO u VALUES (2, :n, '{n('sql_marker_in_literal')} [SQL: x')",
            n("sql_marker_in_literal"),
            {"n": n("sql_marker_in_literal", "n")},
        ),
        Case(
            "multiline_literal",
            f"INSERT INTO u VALUES (2, :n, '{n('multiline_literal')}\nsecond line')",
            n("multiline_literal"),
            {"n": n("multiline_literal", "n")},
        ),
        Case(
            "crlf",
            f"INSERT INTO u\r\nVALUES (2, :n,\r\n '{n('crlf')}\r\nsecond line')",
            n("crlf"),
            {"n": n("crlf", "n")},
        ),
        Case("long_statement", f"SELECT {long_lits} FROM u WHERE", n("long_statement")),
        Case(
            "long_params",
            ins,
            n("long_params"),
            {"i": 2, "n": n("long_params", "n"), "s": n("long_params") + "x" * 30000 + n("long_params", "tail")},
        ),
        Case("many_params", ins, n("many_params"), many, seed_name=n("many_params")),
        Case(
            "engine_log",
            ins,
            n("engine_log"),
            {"i": 2, "n": n("engine_log", "n"), "s": "s"},
            log=True,
            ok_first=[
                f"SELECT name FROM u WHERE name = '{n('engine_log')}' -- note",
                f"SELECT name FROM u WHERE name = '{n('engine_log')}'",
            ],
        ),
        Case(
            "engine_log_long",
            ins,
            n("engine_log_long"),
            {"i": 2, "n": n("engine_log_long", "n"), "s": n("engine_log_long") + "x" * 30000},
            log=True,
            # 1,400 columns: under every server's limit, so the statement succeeds and is logged whole
            ok_first=[f"SELECT {', '.join(repr(n('engine_log_long') + str(i)) for i in range(1400))} FROM u"],
        ),
        Case(
            "pg_line_hint",
            f"SELECT name + 1\nFROM u\nWHERE name = '{n('pg_line_hint')}'",
            n("pg_line_hint"),
            only="postgresql",
        ),
        Case(
            "pg_context",
            "DO $$ BEGIN RAISE EXCEPTION 'boom' "
            f"USING DETAIL = 'detail {n('pg_context')}', HINT = 'hint {n('pg_context')}'; END $$",
            n("pg_context"),
            only="postgresql",
        ),
        Case(
            "mysql_no_backslash_param",
            ins,
            n("mysql_no_backslash_param"),
            {"i": 2, "n": n("mysql_no_backslash_param") + "\\'x", "s": "s"},
            pre=["SET SESSION sql_mode = 'NO_BACKSLASH_ESCAPES'"],
            seed_name=n("mysql_no_backslash_param") + "\\'x",
            only="mysql",
        ),
        Case(
            "mysql_no_backslash_literal",
            f"INSERT INTO u VALUES (2, :n, '{n('mysql_no_backslash_literal')}\\')",
            n("mysql_no_backslash_literal"),
            {"n": n("mysql_no_backslash_literal", "n")},
            pre=["SET SESSION sql_mode = 'NO_BACKSLASH_ESCAPES'"],
            only="mysql",
        ),
    ]


# -- running -------------------------------------------------------------------------------------------


class Ctx:
    def __init__(self, tmp: Path, pg_port: int | None, mysql_port: int | None) -> None:
        self.tmp, self.pg_port, self.mysql_port = tmp, pg_port, mysql_port
        self.sqlite_path = tmp / "sqlerr.db"

    def url(self, d: Driver) -> str:
        port = {"postgresql": self.pg_port, "mysql": self.mysql_port}.get(d.flavor)
        return d.url.format(path=self.sqlite_path.as_posix(), port=port)

    def available(self, d: Driver) -> bool:
        return d.flavor == "sqlite" or {"postgresql": self.pg_port, "mysql": self.mysql_port}[d.flavor] is not None


def run_conn(d: Driver, ctx: Ctx, work: Any, **engine_kw: Any) -> Any:
    """Run ``work(conn)`` on a fresh engine; ``work`` is sync for sync drivers, async for async ones."""
    if d.is_async:

        async def go() -> Any:
            engine = create_async_engine(ctx.url(d), **engine_kw)
            try:
                async with engine.connect() as conn:
                    return await work(conn)
            finally:
                await engine.dispose()

        return asyncio.run(go())
    engine = sa.create_engine(ctx.url(d), **engine_kw)
    try:
        with engine.connect() as conn:
            return work(conn)
    finally:
        engine.dispose()


def seed(d: Driver, ctx: Ctx, name: str) -> None:
    stmts = [("DROP TABLE IF EXISTS u", {}), (CREATE, {}), ("INSERT INTO u VALUES (1, :n, 's0')", {"n": name})]
    if d.is_async:

        async def work(conn: Any) -> None:
            for sql, p in stmts:
                await conn.execute(sa.text(sql), p)
            await conn.commit()

    else:

        def work(conn: Any) -> None:
            for sql, p in stmts:
                conn.execute(sa.text(sql), p)
            conn.commit()

    run_conn(d, ctx, work)


DISTS = {"psycopg2": "psycopg2-binary", "mysqlclient": "mysqlclient"}


def driver_version(d: Driver) -> str:
    if d.name == "sqlite3":
        return f"python {platform.python_version()}, sqlite {sqlite3.sqlite_version}"
    return importlib.metadata.version(DISTS.get(d.name, d.name))


def server_version(d: Driver, ctx: Ctx) -> str:
    sql = {"sqlite": "SELECT sqlite_version()", "postgresql": "SHOW server_version", "mysql": "SELECT version()"}[
        d.flavor
    ]
    if d.is_async:

        async def work(conn: Any) -> str:
            return str((await conn.execute(sa.text(sql))).scalar())

    else:

        def work(conn: Any) -> str:
            return str(conn.execute(sa.text(sql)).scalar())

    return str(run_conn(d, ctx, work))


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def fail_sqlalchemy(d: Driver, ctx: Ctx, c: Case) -> tuple[BaseException, list[str]]:
    """Run the failing statement; return the exception and the ``sqlalchemy.engine`` records."""
    handler = ListHandler()
    logger = logging.getLogger("sqlalchemy.engine")
    if c.log:
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    try:
        if d.is_async:

            async def work(conn: Any) -> None:
                for sql in c.pre + c.ok_first:
                    await conn.exec_driver_sql(sql) if sql in c.pre else await conn.execute(sa.text(sql))
                await conn.execute(sa.text(c.sql), c.params)

        else:

            def work(conn: Any) -> None:
                for sql in c.pre + c.ok_first:
                    conn.exec_driver_sql(sql) if sql in c.pre else conn.execute(sa.text(sql))
                conn.execute(sa.text(c.sql), c.params)

        try:
            run_conn(d, ctx, work, hide_parameters=c.hide)
        except Exception as exc:  # noqa: BLE001 - the error text is the product
            return exc, handler.messages
        raise SystemExit(f"{d.name}/{c.name}: the statement did not fail")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)


async def _raw_aiosqlite(ctx: Ctx, mod: Any, sql: str, params: tuple[str, ...]) -> None:
    async with mod.connect(ctx.sqlite_path) as db:
        await db.execute(sql, params)


async def _raw_asyncpg(ctx: Ctx, mod: Any, sql: str, params: tuple[str, ...]) -> None:
    conn = await mod.connect(user="postgres", database="sqlerr", host="127.0.0.1", port=ctx.pg_port)
    try:
        await conn.execute(sql, *params)
    finally:
        await conn.close()


async def _raw_aiomysql(ctx: Ctx, mod: Any, sql: str, params: tuple[str, ...]) -> None:
    conn = await mod.connect(db="sqlerr", host="127.0.0.1", port=ctx.mysql_port, user="root")
    try:
        cur = await conn.cursor()
        await cur.execute(sql, params)
    finally:
        conn.close()


def _raw_connect(d: Driver, ctx: Ctx, mod: Any) -> Any:
    """A sync DBAPI connection to the driver's server."""
    if d.name == "sqlite3":
        return mod.connect(ctx.sqlite_path)
    if d.flavor == "postgresql":
        return mod.connect(user="postgres", dbname="sqlerr", host="127.0.0.1", port=ctx.pg_port)
    return mod.connect(database="sqlerr", host="127.0.0.1", port=ctx.mysql_port, user="root")


def _raw_sync(d: Driver, ctx: Ctx, mod: Any, sql: str, params: tuple[str, ...]) -> None:
    conn = _raw_connect(d, ctx, mod)
    try:
        conn.cursor().execute(sql, params)
    finally:
        conn.close()


_RAW_ASYNC = {"aiosqlite": _raw_aiosqlite, "asyncpg": _raw_asyncpg, "aiomysql": _raw_aiomysql}


def raw_run(d: Driver, ctx: Ctx, sql: str, params: tuple[str, ...]) -> BaseException:
    """The same failure without SQLAlchemy: the exception a bare DBAPI raises."""
    mod = importlib.import_module(d.module)
    try:
        if d.name in _RAW_ASYNC:
            asyncio.run(_RAW_ASYNC[d.name](ctx, mod, sql, params))
        else:
            _raw_sync(d, ctx, mod, sql, params)
    except Exception as exc:  # noqa: BLE001 - the error text is the product
        return exc
    raise SystemExit(f"{d.name} raw: the statement did not fail")


def raw_cases(d: Driver) -> list[Case]:
    p = d.placeholder
    return [
        Case(
            "raw_unique",
            f"INSERT INTO u VALUES (2, {p}, {p})" if p != "$1" else "INSERT INTO u VALUES (2, $1, $2)",
            mk(d, "raw_unique"),
        ),
        # the error sits before the literal, so a driver that quotes the text after it can show the value
        Case("raw_syntax", f"SELECT name FROM u WHERE AND name = '{mk(d, 'raw_syntax')}'", mk(d, "raw_syntax")),
    ]


# -- sanitising and writing ----------------------------------------------------------------------------


def sanitiser(ctx: Ctx) -> Any:
    home = Path.home()
    pairs = [(ctx.tmp, "<tmp>"), (ROOT, "<repo>"), (home, "<home>")]
    rules: list[tuple[re.Pattern[str], str]] = []
    for path, token in pairs:
        spellings = {str(path), path.as_posix(), str(path).replace("\\", "\\\\")}
        rules.extend((re.compile(re.escape(text), re.IGNORECASE), token) for text in spellings)
    for word, token in ((home.name, "<user>"), (socket.gethostname(), "<host>")):
        rules.append((re.compile(re.escape(word), re.IGNORECASE), token))

    def clean(text: str) -> str:
        for rule, token in rules:
            text = rule.sub(token, text)
        return text

    return clean


def section(title: str, body: str) -> str:
    return f"##### {title} #####\n{body}\n"


def write_case(
    d: Driver, c: Case, exc: BaseException, records: list[str], clean: Any, versions: dict[str, str]
) -> dict[str, Any]:
    orig = getattr(exc, "orig", None)
    parts = [
        (
            "types",
            f"{type(exc).__module__}.{type(exc).__qualname__}"
            + (f"\norig: {type(orig).__module__}.{type(orig).__qualname__}" if orig is not None else ""),
        )
    ]
    parts.append(("str(exc)", str(exc)))
    if orig is not None:
        parts.append(("str(exc.orig)", str(orig)))
    parts.append(("traceback", "".join(traceback.format_exception(exc)).rstrip("\n")))
    parts += [(f"log record {i}", m) for i, m in enumerate(records, 1)]
    target = OUT / d.name / f"{c.name}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = clean("".join(section(t, b) for t, b in parts))
    with target.open("w", encoding="utf-8", newline="") as fh:  # newline="": CRLF stays CRLF
        fh.write(text)
    return {
        "case": c.name,
        "driver": d.name,
        "file": f"{d.name}/{c.name}.txt",
        "driver_version": versions["driver"],
        "sqlalchemy_version": sa.__version__,
        "server_version": versions["server"],
        "marker": c.marker,
        # A bare driver may not echo the value at all (sqlite's UNIQUE message); that is a finding, so it is recorded
        "marker_in_text": c.marker in text,
        "sections": [t for t, _ in parts],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pg-port", type=int)
    ap.add_argument("--mysql-port", type=int)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="sqlerr-") as tmpdir:
        ctx = Ctx(Path(tmpdir), args.pg_port, args.mysql_port)
        for flavor, port, sql in (
            ("postgresql", args.pg_port, "CREATE DATABASE sqlerr"),
            ("mysql", args.mysql_port, "CREATE DATABASE IF NOT EXISTS sqlerr"),
        ):
            if port:
                create_database(flavor, port, sql)
        shutil.rmtree(OUT, ignore_errors=True)
        clean = sanitiser(ctx)
        manifest: list[dict[str, Any]] = []
        for d in DRIVERS:
            if not ctx.available(d):
                print(f"skip {d.name}: no {d.flavor} server given")
                continue
            versions = {"driver": driver_version(d), "server": server_version(d, ctx)}
            for c in cases(d):
                if c.only not in (None, d.flavor):
                    continue
                bound = c.params.get("n") if isinstance(c.params, dict) else None
                seed(d, ctx, c.seed_name or bound or c.marker)
                exc, records = fail_sqlalchemy(d, ctx, c)
                manifest.append(write_case(d, c, exc, records, clean, versions))
            for c in raw_cases(d):
                seed(d, ctx, mk(d, "raw_unique"))
                raw_params = (mk(d, "raw_unique"), "s1") if c.name == "raw_unique" else ()
                manifest.append(write_case(d, c, raw_run(d, ctx, c.sql, raw_params), [], clean, versions))
            print(f"ok {d.name}: {sum(1 for m in manifest if m['driver'] == d.name)} cases")
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def create_database(flavor: str, port: int, sql: str) -> None:
    if flavor == "postgresql":
        import psycopg2  # noqa: PLC0415 - test-only driver

        conn = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname="postgres")
        conn.autocommit = True
        try:
            conn.cursor().execute("DROP DATABASE IF EXISTS sqlerr")
            conn.cursor().execute(sql)
        finally:
            conn.close()
    else:
        import pymysql  # noqa: PLC0415 - test-only driver

        conn = pymysql.connect(host="127.0.0.1", port=port, user="root")
        try:
            conn.cursor().execute(sql)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
