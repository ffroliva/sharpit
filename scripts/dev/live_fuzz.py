"""The live fuzz: random token runs through a real server, and what sharpit shows of a value the server returned.

    uv run python scripts/dev/live_fuzz.py --server mysql84 --strings 100000 --seed 1 [--session NO_BACKSLASH_ESCAPES]

Ported from spike 2's ``fuzz2.py`` (itself ``fuzz4.py`` patched): the same tokens, prefixes and twin check. The server
comes from the live profile (``tests/live/conftest.py``): ``SHARPIT_LIVE_<KEY>_URL``, else a Testcontainers image,
``SHARPIT_LIVE_IMAGE_<KEY>`` to pick its version; ``sqlite`` runs in process.

A **hit**: the server returned a marker, an output shows it, and swapping that occurrence for its twin puts the twin in
both the rows and the output, outside a ``"`` run. Two builds read every string the server took:

* ``build``: sharpit, with the dialect the server's family names, on ``statement_text`` and ``normalize``.
* ``control``: a reading that knows only ``'...'`` with doubled quotes. It is no code of sharpit's, so it cannot agree
  with the build by sharing it. A run whose control finds nothing proves nothing (spike 2: PostgreSQL's 0 was weak
  because its control also found 0).

Hits are written to ``--out`` as they arrive, one JSON object a line. Exit 0: the build 0 and the control above 0. Exit
1: a build hit. Exit 2: the control found nothing, so no verdict.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # ``tests.live`` holds the server start

TWIN = {"SECRET": "ZQXJKV", "1234567": "7654329"}
COMMON = [
    " ", " ", " ", "\n", ",", ",", "1", "a", "(", ")", "'", "'", "''", '"', "`", "`", "[", "]", "]", "$$", "$$", "$a$",
    "$", "--", "-- ", "#", "/*", "*/", "*/", "\\", "@", ".", "=", "+", "-", ":", "q'", "'x'", "`x`", "[x]", "[a b]",
    "'SECRET'", "'SECRET'", "'SECRET'", "$$SECRET$$", "1234567", "1234567", "\r", "e", "0x1", "1e1", ".5", "5--",
    "5--/*", "['", "']", "[$$]", "[--", "[/*", "[`", "a[", "1[", ")[", "::text", " AS ",
    "/* /* */", "/* /*", "/*/**/", "-- x\r", "--\r", "$1$", "$js$", " SECRET ", " $$", "$$ ", " [",
    " [CASE WHEN FALSE THEN 1234567 ELSE 1 END]", "[a 1234567]", "CASE WHEN TRUE THEN ", " END]", "`\n'a`b,'", "5--`\n",
    "'a`", "t. ", "@ ", "$a$x$$a$", "$ab$$a$ab$", "[a 1", "[a b]", " THEN.1234567", "`", "``",
    # fuzz2's additions: escape prefixes, Unicode spaces, a dollar quote beside a string
    "e'", "E'", "\\'", "'\\", "U&'", "/*", "*/", "\r", "\\", "x ", " ", "　", "x $$", "'a $$ ",
    "'a $a$ ", "@$$ := ", "@$a$ := ",
]  # fmt: skip
_MYSQL = ["@a", "@`a`", "t.", "t.$$", "@$$", "/*!", "/*!50000", "/*! ", "1$$", "1$a$", ":=", "_utf8mb4'",
          "$1$SECRET$1$", "$js$ SECRET $js$", "/*! AS ", "AS "]  # fmt: skip
EXTRA = {
    "sqlite": ["?", ":a", "@a", "$a", "$a(", ":a(", "@a(", "#a(", "$a::b(", "$1(", ":a(`)", "$a(it's)", "[a[b",
               "[it's]", "a[it's[b]"],
    "postgresql": ["ARRAY[", "ARRAY[[", "$1", "E'", "$a$SECRET$a$", "::int", "ARRAY[$$", "]::text[]", "(ARRAY[1,2])",
                   "(ARRAY[1234567])"],
    "mysql": _MYSQL,
    "mariadb": [*_MYSQL, "/*M!", "/*M!100000 ", "/*!50700 ", "/*!!99999 ", "/*M! SELECT ", "'x $$ "],
}  # fmt: skip
ENDINGS = ("", "", " FROM (SELECT 1 AS a) t", ", 'SECRET'", ", 1234567", ", $$SECRET$$")
PREFIXES = ["SELECT ", "SELECT ", "SELECT ", "SELECT /* /* */ ", "SELECT /*/**/", "SELECT -- x\r ", "SELECT 1, -- x\r ",
            "SELECT 1 --\r"]  # fmt: skip
ROUTINE = "CREATE PROCEDURE zp() LANGUAGE JAVASCRIPT "
MYSQL_PREFIXES = [  # half the strings: a routine is the only place MySQL takes a dollar quote
    ROUTINE + "AS ", ROUTINE + "AS ", ROUTINE + "AS /* /* */ ", ROUTINE,
    "CREATE FUNCTION zf() RETURNS INT NO SQL LANGUAGE JAVASCRIPT AS ", ROUTINE + "AS # ", ROUTINE + "/*! AS ",
    ROUTINE + "AS -- x\r ",
]  # fmt: skip
MARIADB_ROUTINE = "CREATE PROCEDURE zp() "
MARIADB_PREFIXES = [
    MARIADB_ROUTINE + "SELECT ", MARIADB_ROUTINE + "BEGIN SELECT ", "/*M! SELECT ", "SELECT /*M! ", "SELECT /*!50700 ",
    MARIADB_ROUTINE + "SELECT /*M! ", "SELECT 1 AS $$, 'x $$ ", "SELECT 1 $a$, 'x $a$ ", "SELECT 'a' AS $$, 'b $$ ",
    MARIADB_ROUTINE + "SELECT 1 AS $$, 'x $$ ",
]  # fmt: skip
_SINGLE_QUOTED = re.compile(r"'(?:[^']|'')*'?")
Run = Callable[[str], str]


def control(text: str) -> str:
    """The control's reading: ``'...'`` runs hidden, everything else shown."""
    return _SINGLE_QUOTED.sub("?", text)


def strings(family: str, seed: int, count: int) -> Iterator[str]:
    """fuzz4's generator: two to nine tokens after a prefix, with a marker somewhere in the text."""
    tokens = COMMON + EXTRA[family]
    prefixes = PREFIXES + {"mysql": MYSQL_PREFIXES, "mariadb": MYSQL_PREFIXES + MARIADB_PREFIXES}.get(family, [])
    rng = random.Random(seed)
    for _ in range(count):
        body = "".join(rng.choice(tokens) for _ in range(rng.randint(2, 9)))
        text = rng.choice(prefixes) + body + rng.choice(ENDINGS)
        if any(marker in text for marker in TWIN) and "\x00" not in text:
            yield text


class _Null(dict[str, Any]):
    def __missing__(self, _key: str) -> None:
        return None


def _mysql_runner(raw: Any) -> Run:
    cursor = raw.cursor()

    def run(text: str) -> str:
        cursor.execute(text)
        if not text.startswith("CREATE"):
            return repr(cursor.fetchall())
        kind, name = ("FUNCTION", "zf") if text.startswith("CREATE FUNCTION") else ("PROCEDURE", "zp")
        where = "FROM information_schema.routines WHERE routine_schema = DATABASE() AND routine_name = %s"
        cursor.execute(f"SELECT routine_definition {where}", (name,))  # noqa: S608 - a constant
        body = repr(cursor.fetchall())
        cursor.execute(f"DROP {kind} {name}")
        return body

    return run


@contextmanager
def server_runner(key: str, session: str) -> Iterator[tuple[str, Run]]:
    """The family and a ``run(text) -> repr(rows)`` for the server ``key``; a refusal raises."""
    if key == "sqlite":
        db = sqlite3.connect(":memory:")
        yield "sqlite", lambda text: repr(db.execute(text, _Null()).fetchall())
        db.close()
        return
    import sqlalchemy as sa  # noqa: PLC0415 - the live profile's stack, not needed for sqlite
    from tests.live.conftest import _boot  # noqa: PLC0415  # pyright: ignore[reportPrivateUsage]

    with _boot(key) as server:
        engine = sa.create_engine(server.url)
        raw: Any = engine.raw_connection()
        try:
            if server.family == "postgresql":
                raw.autocommit = True
                cursor = raw.cursor()
                if session:
                    cursor.execute(f"SET standard_conforming_strings = {session}")

                def run(text: str) -> str:
                    cursor.execute(text.encode())  # bytes: psycopg sends them as they stand, no placeholder parsing
                    return repr(cursor.fetchall()) if cursor.description else ""

                yield server.family, run
            else:
                raw.autocommit(True)
                setup = raw.cursor()
                try:  # as the oracle: a binary log refuses CREATE FUNCTION without it
                    setup.execute("SET GLOBAL log_bin_trust_function_creators = 1")
                except Exception as refused:  # noqa: BLE001 - those rows only stop counting
                    print(f"live_fuzz: {key}: {refused}", file=sys.stderr)
                if session:
                    setup.execute(f"SET SESSION sql_mode = '{session}'")
                yield server.family, _mysql_runner(raw)
        finally:
            raw.close()
            engine.dispose()


def _builds(family: str) -> dict[str, Callable[[str], str]]:
    from sharpit.engine.capture.sqlscan import normalize_sql  # noqa: PLC0415
    from sharpit.engine.capture.statement import statement_text  # noqa: PLC0415
    from sharpit.engine.masking import Exposure, Masker  # noqa: PLC0415
    from sharpit.engine.sqltext import Dialect, dialect_of_name  # noqa: PLC0415

    dialect = dialect_of_name(family) or Dialect.UNSUPPORTED
    masker = Masker(Exposure.MASKED, True)
    return {
        "build": lambda text: f"{statement_text(masker, text, dialect)}\n{normalize_sql(text, dialect)}",
        "control": control,
    }


def _twin_holds(text: str, run: Run, read: Callable[[str], str]) -> dict[str, str] | None:
    """The hit is that occurrence's: with the twin in its place, the server returns it and the output shows it."""
    for marker, twin in TWIN.items():
        for found in re.finditer(marker, text):
            swapped = text[: found.start()] + twin + text[found.end() :]
            try:
                rows = run(swapped)
            except Exception:  # noqa: BLE001, S112 - a refused twin proves nothing either way
                continue
            out = read(swapped)
            if twin in rows and twin in out and not re.search(rf'"[^"]*{twin}[^"]*"', out):
                return {"out": out, "rows": rows[:200]}
    return None


def fuzz(key: str, session: str, seed: int, count: int, out: Path) -> dict[str, Any]:
    with server_runner(key, session) as (family, run):
        builds = _builds(family)
        hits = dict.fromkeys(builds, 0)
        parsed = 0
        seen: set[tuple[str, str]] = set()
        out.write_text("", encoding="utf-8")
        with out.open("a", encoding="utf-8") as sink:
            for index, text in enumerate(strings(family, seed, count)):
                try:
                    rows = run(text)
                except Exception:  # noqa: BLE001, S112 - the server refused it: no value came back
                    continue
                parsed += 1
                for name, read in builds.items():
                    shown = read(text)
                    if (name, text) in seen or not any(m in rows and m in shown for m in TWIN):
                        continue
                    held = _twin_holds(text, run, read)
                    if held:
                        seen.add((name, text))
                        hits[name] += 1
                        sink.write(json.dumps({"build": name, "server": key, "session": session, "q": text, **held}))
                        sink.write("\n")
                        sink.flush()
                if index and index % 20000 == 0:
                    print(key, session, index, "parsed", parsed, "hits", hits, flush=True)
    return {"server": key, "session": session, "seed": seed, "strings": count, "parsed": parsed, "hits": hits}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", required=True, help="a live profile key, or sqlite")
    parser.add_argument("--strings", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--session", default="", help="sql_mode, or standard_conforming_strings on PostgreSQL")
    parser.add_argument("--out", type=Path, help="the hits file; default live-fuzz-<server>-<seed>.jsonl")
    arguments = parser.parse_args(argv)
    out = arguments.out or Path(f"live-fuzz-{arguments.server}-{arguments.seed}.jsonl")
    summary = fuzz(arguments.server, arguments.session, arguments.seed, arguments.strings, out)
    print(json.dumps(summary))
    if summary["hits"]["build"]:
        return 1
    return 0 if summary["hits"]["control"] else 2


if __name__ == "__main__":
    sys.exit(main())
