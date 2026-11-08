"""Property tests of the statement output (design section 8): ``hypothesis`` finds a new shape and shrinks it.

# derived: BootUI has no property tests; the readings come from ``study.md`` section 1, not from the lexer under test.

Each server reading below is a token grammar: a literal token holds a marker, and no other token can hold one. Tokens
are whole under that reading, so the reading itself places every literal range: the expected output never comes from
the code under test. A dialect must hide a literal under each reading its servers can take, because session settings
(``standard_conforming_strings``, ``NO_BACKSLASH_ESCAPES``, ``ANSI_QUOTES``, ``sql_mode=MSSQL``) are state no text
reveals. SQLite needs no grammar of ours: ``sqlite3`` runs the statement in process, and what it returns is a value.

The profile (``tests/conftest.py``) is derandomized: every run tries the same examples.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

import pytest
from hypothesis import given, note, settings
from hypothesis import strategies as st
from tests.masking.test_gates_bite import (
    MUTANTS,
    Mutant,
    _mutate,  # pyright: ignore[reportPrivateUsage]
    _scratch_copy,  # pyright: ignore[reportPrivateUsage]
)

from sharpit.engine.capture.sqlscan import normalize_sql
from sharpit.engine.capture.statement import statement_text
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import LEXER, SPACE_CHARS, Dialect

ROOT = Path(__file__).resolve().parents[2]
LEAK, PAST_THE_CUT, INSIDE_A_NAME = "reaches the output", "the cut shows more than its head", "a mask inside a name"
MASKER = Masker(Exposure.MASKED, True)
SLOT = "\0"  # where a literal's marker goes; no other token holds one
EXAMPLES = 200

Strategy = st.SearchStrategy[str]


def _run(pieces: Sequence[str], least: int = 0, critical: Sequence[str] = ()) -> Strategy:
    """Joined pieces; half of them ``critical`` when given: the pieces where the readings of a family part."""
    piece = st.one_of(st.sampled_from(critical), st.sampled_from(pieces)) if critical else st.sampled_from(pieces)
    return st.lists(piece, min_size=least, max_size=4).map("".join)


def _quoted(opener: str, pieces: Sequence[str], closer: str, critical: Sequence[str] = ()) -> Strategy:
    """A literal: ``pieces`` around the marker's slot. Each piece is whole, so no join of them closes the quote."""
    body = _run(pieces, critical=critical)
    return st.tuples(body, body).map(lambda part: f"{opener}{part[0]}{SLOT}{part[1]}{closer}")


def _wrapped(opener: str, pieces: Sequence[str], closer: str) -> Strategy:
    """A token holding no marker: a quoted name or a comment."""
    return _run(pieces, 1).map(lambda body: f"{opener}{body}{closer}")


def _nested(pieces: Sequence[str]) -> Strategy:
    """A PostgreSQL block comment, which nests (scan.l:447-485)."""
    leaf = _run(pieces)
    return st.recursive(
        leaf.map(lambda body: f"/* {body} */"),
        lambda inner: st.tuples(leaf, inner, leaf).map(lambda part: f"/* {part[0]} {part[1]} {part[2]} */"),
        max_leaves=3,
    )


class Reading(NamedTuple):
    """One server reading: the tokens that hold a marker, and every other token."""

    name: str
    literals: tuple[Strategy, ...]
    others: tuple[Strategy, ...]


_RISKY = (" ", "a", "--", "/*", "*/", "#", "`", "[", "]", "\n", "\r", " ", ";", "?")
_SEPARATORS = (" ", "\n", "\t", "  ", "   ", " 　 ")  # a Unicode space only between ASCII ones: a name char


def _code(words: Sequence[str]) -> Strategy:
    return st.sampled_from(words)


# --- PostgreSQL 18 (scan.l): ``standard_conforming_strings`` on and off --------------------------------------------

_PG_PLAIN = (*_RISKY, "''", "\\", '"', "$$", "$a$")  # on: ``\`` is a character (scan.l:545-552)
_PG_ESCAPED = (*_RISKY, "''", "\\'", "\\\\", "\\a", '"', "$$", "$a$")  # ``E'``, and ``'`` when off: ``\`` pairs
_PG_DOLLAR = (*_RISKY, "'", "''", "\\", '"')  # no ``$``: no join of them closes a tag
_PG_TAGGED = (*_PG_DOLLAR, "$$", "$a$")  # a ``$q$`` body: only ``$q$`` closes it (scan.l:757-776)
_PG_NAME = ("a", " ", "'", '""', "\\", "$$", "--", "/*", "#", "`")
_PG_LINE = ("a", " ", "'", '"', "$$", "/*", "*/", "\\", "`")  # ``--`` ends at LF or CR (scan.l:210-213)
_PG_BLOCK = ("a", " ", "'", '"', "$$", "--", "\\", "\n", "\r", "`")
_PG_CODE = ("SELECT", "a", "t.c", "1", ",", "(", ")", "=", "||", "::text", "$1", "#>>", "`", "@", "[", "]", "a[1]",
            "-", "/", "*", "ARRAY[", "1.5", "E")  # fmt: skip
_PG_OTHERS = (
    _code(_PG_CODE),
    _wrapped('"', _PG_NAME, '"'),
    _wrapped("-- ", _PG_LINE, "\n"),
    _wrapped("--", _PG_LINE, "\r"),
    _nested(_PG_BLOCK),
)
_PAIRS = ("\\'", "\\\\")  # an escape pair: where a reading without escapes ends the string early
_PG_DOLLARS = (
    _quoted("$$", _PG_DOLLAR, "$$", ("'", "\\")),
    _quoted("$q$", _PG_TAGGED, "$q$", ("$$", "$a$", "'")),
    _quoted("E'", _PG_ESCAPED, "'", _PAIRS),
)
POSTGRESQL = (
    Reading("pg-on", (_quoted("'", _PG_PLAIN, "'", ("\\",)), *_PG_DOLLARS), _PG_OTHERS),
    Reading("pg-off", (_quoted("'", _PG_ESCAPED, "'", _PAIRS), *_PG_DOLLARS), _PG_OTHERS),
)

# --- the MySQL family (sql_lex.cc): MySQL 8.4 and MariaDB, by session mode ------------------------------------------

_MY_SINGLE = (*_RISKY, "''", '"', "\\'", '\\"', "\\\\", "\\a", "$$")  # get_text: ``\`` takes one byte (:1043-1054)
_MY_DOUBLE = (*_RISKY, '""', "'", "\\'", '\\"', "\\\\", "\\a", "$$")
_MY_SINGLE_NBE = (*_RISKY, "''", '"', "\\", "$$")  # NO_BACKSLASH_ESCAPES: ``\`` is a character
_MY_DOUBLE_NBE = (*_RISKY, '""', "'", "\\", "$$")
_MY_DOLLAR = (*_RISKY, "'", '"', "\\")  # no ``$``: the closer does not step back (:1159-1188)
_MY_NAME = ("a", " ", "'", '"', "``", "\\", "$$", "--", "#", "/*")
_MY_ANSI_NAME = ("a", " ", "'", '""', "\\", "`", "$$", "--", "#", "/*")  # ANSI_QUOTES: the backtick path (:1889)
_MY_BRACKET = ("a", " ", "'", '"', "`", "\\", "$$", "--", "#", "/*")  # MariaDB sql_mode=MSSQL (:2105, :3026)
_MY_LINE = ("a", " ", "'", '"', "`", "$$", "/*", "*/", "\\", "\r")  # ``--`` and ``#`` end at LF only (:1916)
# no nesting (:1315-1351); ``/* `` keeps its space, or two of them join into ``*/``
_MY_BLOCK = ("a", " ", "'", '"', "`", "$$", "--", "#", "\\", "\n", "\r", "/* ")
_MY_CODE = ("SELECT", "a", "t.c", "1", ",", "(", ")", "=", "@v", "@@x", "--1", "-", "$a", "t.1c", "1e5", ":=",
            "@`v`")  # fmt: skip
_MY_COMMON = (
    _wrapped("`", _MY_NAME, "`"),
    _wrapped("-- ", _MY_LINE, "\n"),
    _wrapped("#", _MY_LINE, "\n"),
    _wrapped("/* ", _MY_BLOCK, " */"),
)
_MY_DOLLARS = (  # 8.4 only (:2160-2193)
    _quoted("$$", _MY_DOLLAR, "$$", ("'", '"', "\\")),
    _quoted("$q$", _MY_DOLLAR, "$q$", ("'", '"', "\\")),
)
_MY_ESCAPES = ("\\'", '\\"', "\\\\")
_MY_STRINGS = (_quoted("'", _MY_SINGLE, "'", _MY_ESCAPES), _quoted('"', _MY_DOUBLE, '"', _MY_ESCAPES))
_MY_STRINGS_NBE = (_quoted("'", _MY_SINGLE_NBE, "'", ("\\",)), _quoted('"', _MY_DOUBLE_NBE, '"', ("\\",)))
_MARIADB_CODE = _code((*_MY_CODE, "[", "]", "$$", "$a$"))  # no dollar quote: ``$`` is a name character (charset.c:85)
MYSQL_FAMILY = (
    Reading("mysql84", (*_MY_STRINGS, *_MY_DOLLARS), (_code((*_MY_CODE, "[", "]")), *_MY_COMMON)),
    Reading("mysql84-nbe", (*_MY_STRINGS_NBE, *_MY_DOLLARS), (_code((*_MY_CODE, "[", "]")), *_MY_COMMON)),
    Reading(
        "mysql84-ansi",
        (_quoted("'", _MY_SINGLE, "'", _MY_ESCAPES), *_MY_DOLLARS),
        (_code((*_MY_CODE, "[", "]")), _wrapped('"', _MY_ANSI_NAME, '"'), *_MY_COMMON),
    ),
    Reading("mariadb", _MY_STRINGS, (_MARIADB_CODE, *_MY_COMMON)),
    Reading("mariadb-nbe", _MY_STRINGS_NBE, (_MARIADB_CODE, *_MY_COMMON)),
    Reading(  # MSSQL implies ANSI_QUOTES
        "mariadb-mssql",
        (_quoted("'", _MY_SINGLE, "'", _MY_ESCAPES),),
        (_code((*_MY_CODE, "$$")), _wrapped('"', _MY_ANSI_NAME, '"'), _wrapped("[", _MY_BRACKET, "]"), *_MY_COMMON),
    ),
)

READINGS = {Dialect.POSTGRESQL: POSTGRESQL, Dialect.MYSQL_FAMILY: MYSQL_FAMILY}


@st.composite
def _statement(draw: st.DrawFn, readings: Sequence[Reading]) -> tuple[str, str, list[str]]:
    """``SELECT`` and a token stream holding at least one literal; each literal's slot gets its own marker."""
    reading = draw(st.sampled_from(readings))
    token = st.one_of(st.one_of(*reading.literals), st.one_of(*reading.others))  # half the tokens a literal
    tokens = [
        *draw(st.lists(token, max_size=6)),
        draw(st.one_of(*reading.literals)),
        *draw(st.lists(token, max_size=6)),
    ]
    separators = draw(st.lists(st.sampled_from(_SEPARATORS), min_size=len(tokens), max_size=len(tokens)))
    text = "SELECT" + "".join(separator + piece for separator, piece in zip(separators, tokens, strict=True))
    markers: list[str] = []
    while SLOT in text:
        markers.append(f"ZQ{len(markers)}X")
        text = text.replace(SLOT, markers[-1], 1)
    return reading.name, text, markers


# --- SQLite, against ``sqlite3`` itself ----------------------------------------------------------------------------

_LITE_SINGLE = (*_RISKY, "''", "\\", '"', "$a", ":a", "@a", "$$")  # no backslash at all (tokenize.c:396-420)
_LITE_DOUBLE = (*_RISKY, '""', "'", "\\", "$a")  # a name, or a string when no column has it: the server decides
_LITE_LINE = ("a", " ", "'", '"', "`", "[", "$$", "/*", "*/", "\\", "\r")  # ``--`` ends at LF only (:289-293)
_LITE_BLOCK = ("a", " ", "'", '"', "`", "[", "]", "$$", "--", "\\", "\n", "\r", "/* ")  # first ``*/`` (:321-330)
_LITE_COLUMNS = ("a", "a'b", 'c"d', "e`f", "x$y")
_LITE_NAMES = ("a", "t.a", "[a'b]", "`a'b`", '"a\'b"', '[c"d]', '"c""d"', '`c"d`', "`e``f`", "[e`f]", '"e`f"',
               "[x$y]", "x$y", "`x$y`")  # fmt: skip
_LITE_CODE = ("1", "(1)", "-1", "1 + 1", "a + 1", "1.5", "x'0a'", "NULL", "CASE WHEN 1 THEN 2 END")
_LITE_COMMENTS = st.one_of(_wrapped("/* ", _LITE_BLOCK, " */"), _wrapped("-- ", _LITE_LINE, "\n"))
_LITE_LITERALS = st.one_of(_quoted("'", _LITE_SINGLE, "'", ("\\", '"')), _quoted('"', _LITE_DOUBLE, '"', ("\\", "'")))
_LITE_ITEMS = st.one_of(_LITE_LITERALS, st.sampled_from(_LITE_NAMES), st.sampled_from(_LITE_CODE))


@st.composite
def _sqlite_statement(draw: st.DrawFn) -> tuple[str, list[str]]:
    """A query ``sqlite3`` runs: items, comments between them, and an unclosed ``/*`` at the end, valid there."""
    items = [*draw(st.lists(_LITE_ITEMS, max_size=4)), draw(_LITE_LITERALS), *draw(st.lists(_LITE_ITEMS, max_size=4))]
    gaps = draw(st.lists(st.one_of(st.just(""), _LITE_COMMENTS), min_size=len(items), max_size=len(items)))
    tail = draw(st.one_of(st.just(""), _run(_LITE_BLOCK).map(lambda body: f" /* {body}")))
    text = "SELECT " + ", ".join(f"{gap}{item}" for gap, item in zip(gaps, items, strict=True)) + " FROM t" + tail
    markers: list[str] = []
    while SLOT in text:
        markers.append(f"ZQ{len(markers)}X")
        text = text.replace(SLOT, markers[-1], 1)
    return text, markers


def _sqlite() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE t (" + ", ".join('"' + c.replace('"', '""') + '"' for c in _LITE_COLUMNS) + ")")
    db.execute("INSERT INTO t VALUES (1, 2, 3, 4, 5)")
    return db


_DB = _sqlite()


def _takes_double_quoted_strings() -> bool:
    try:
        _DB.execute('SELECT "no such column"')
    except sqlite3.OperationalError:
        return False
    return True


_DQS = _takes_double_quoted_strings()  # ``SQLITE_DQS``: a build compiled without it reads ``"x"`` only as a name


def _returned(text: str) -> str:
    """What ``sqlite3`` gives back. The generator writes only valid queries: a refusal is a fault in it, not a pass."""
    try:
        return repr(_DB.execute(text).fetchall())
    except sqlite3.OperationalError:
        if _DQS:
            raise
        return ""  # the build refuses a double-quoted string: no acceptance check, and no value to look for


# --- the properties ------------------------------------------------------------------------------------------------


def _outputs(text: str, dialect: Dialect) -> dict[str, str]:
    """Every text a statement reaches the console as: the statement surface and the scan's shape."""
    return {"statement_text": statement_text(MASKER, text, dialect) or "", "normalize": normalize_sql(text, dialect)}


def _shown(markers: Sequence[str], text: str, dialect: Dialect) -> dict[str, list[str]]:
    outputs = _outputs(text, dialect)
    note(f"outputs: {outputs!r}")
    found = {name: [m for m in markers if m.lower() in out.lower()] for name, out in outputs.items()}
    return {name: hits for name, hits in found.items() if hits}


@settings(max_examples=EXAMPLES)
@given(case=_statement(POSTGRESQL))
def _never_survives_postgresql(case: tuple[str, str, list[str]]) -> None:
    reading, text, markers = case
    note(f"{reading}: {text!r}")
    assert not _shown(markers, text, Dialect.POSTGRESQL), f"a {reading} literal reaches the output"


@settings(max_examples=EXAMPLES)
@given(case=_statement(MYSQL_FAMILY))
def _never_survives_mysql_family(case: tuple[str, str, list[str]]) -> None:
    reading, text, markers = case
    note(f"{reading}: {text!r}")
    assert not _shown(markers, text, Dialect.MYSQL_FAMILY), f"a {reading} literal reaches the output"


@settings(max_examples=EXAMPLES)
@given(case=_sqlite_statement())
def _never_survives_sqlite(case: tuple[str, list[str]]) -> None:
    text, markers = case
    returned = _returned(text)
    values = [m for m in markers if m in returned]
    note(f"sqlite: {text!r} returned {returned!r}")
    assert not _shown(values, text, Dialect.SQLITE), "a value sqlite3 returned reaches the output"


NEVER_SURVIVES: dict[Dialect, Callable[[], None]] = {
    Dialect.POSTGRESQL: _never_survives_postgresql,
    Dialect.MYSQL_FAMILY: _never_survives_mysql_family,
    Dialect.SQLITE: _never_survives_sqlite,
}
IDS = {Dialect.POSTGRESQL: "postgresql", Dialect.MYSQL_FAMILY: "mysql_family", Dialect.SQLITE: "sqlite"}


@pytest.mark.parametrize("dialect", NEVER_SURVIVES, ids=IDS.get)
def test_a_literal_never_survives(dialect: Dialect) -> None:
    NEVER_SURVIVES[dialect]()


def _any_statement(dialect: Dialect) -> st.SearchStrategy[str]:
    if dialect is Dialect.SQLITE:
        return _sqlite_statement().map(lambda case: case[0])
    return _statement(READINGS[dialect]).map(lambda case: case[1])


def _bare(text: str) -> str:
    return "".join(c for c in text if c not in SPACE_CHARS)


def _shows_no_more(out: str, most: str) -> bool:
    """``out`` is ``most`` with some runs hidden: each ``?`` of ``out`` stands for any run of ``most``, even an empty
    one, and every other character is copied in place. Spaces are ignored: a hidden run takes its space with it."""
    pattern = ".*".join(re.escape(part) for part in _bare(out).split("?"))
    return re.fullmatch(pattern, _bare(most), re.DOTALL) is not None


@pytest.mark.parametrize("dialect", NEVER_SURVIVES, ids=IDS.get)
def test_a_cut_only_shortens(dialect: Dialect) -> None:
    """A statement that reads two ways shows at most its head's own output and one ``?``: nothing past the cut, and
    nothing of the head its own read would hide. It may hide more (``SELECT [ -- '...`` shows ``SELECT ? ?``): that
    over-cut is the corpus gates' count, not a leak."""

    @settings(max_examples=EXAMPLES)
    @given(text=_any_statement(dialect))
    def only_shortens(text: str) -> None:
        cut = LEXER.scan(text, dialect).cut
        if cut < 0:
            return
        out, most = normalize_sql(text, dialect), normalize_sql(text[:cut], dialect) + "?"
        note(f"cut at {cut}: head {text[:cut]!r}, shown {out!r}, at most {most!r}")
        assert out.endswith("?"), PAST_THE_CUT
        assert _shows_no_more(out, most), PAST_THE_CUT

    only_shortens()


def test_the_cut_check_hides_no_head_literal() -> None:
    """The check itself, on the case a subsequence check let through: a head that keeps its raw literal."""
    head = normalize_sql("SELECT 'abc', ", Dialect.MYSQL_FAMILY) + "?"
    assert _shows_no_more("SELECT ?, ?", head)
    assert _shows_no_more("SELECT ? ?", head)  # hides more: allowed
    assert not _shows_no_more("SELECT 'abc', ?", head)


# --- a name never holds a mask -------------------------------------------------------------------------------------

_NAMES: dict[Dialect, tuple[str, ...]] = {
    Dialect.POSTGRESQL: ('"Mixed Name"', '"a1"', "t1.c$2"),
    Dialect.MYSQL_FAMILY: ("`Mixed Name`", "`a1`", "t.1col", "$a", "t1.c$2"),
    Dialect.SQLITE: ("[Mixed Name]", "`a1`", "t1.c$2"),
}
_PLAIN_NAMES = ("a", "col1", "x_2", "t.col1", "a$b", "café2", "token_count", "api_key_id", "auth_level",
                "secret_santa", "password_hash", "user2id")  # fmt: skip
_VALUES = ("'abc'", "42", "1.5", "'it''s'", "-7")
_MASK_TOKEN = re.compile(rf"\S*(?:\?|{re.escape(MASK)})\S*")


@st.composite
def _named(draw: st.DrawFn, dialect: Dialect) -> tuple[str, list[str]]:
    """Names where no ``"`` run is a value: the select list, ``FROM``, and the left of a comparison."""
    name = st.sampled_from((*_PLAIN_NAMES, *_NAMES[dialect]))
    value = st.sampled_from(_VALUES)
    picked = draw(st.lists(name, min_size=1, max_size=3))
    table = draw(name)
    tests = draw(st.lists(st.tuples(name, value, st.lists(value, min_size=1, max_size=3)), max_size=2))
    text = f"SELECT {', '.join(picked)} FROM {table}"
    if tests:
        text += " WHERE " + " AND ".join(f"{n} = {v} OR {n} IN ({', '.join(vs)})" for n, v, vs in tests)
    return text, [*picked, table, *(n for n, _, _ in tests)]


@pytest.mark.parametrize("dialect", NEVER_SURVIVES, ids=IDS.get)
def test_the_output_never_grows_a_mask_inside_a_name(dialect: Dialect) -> None:
    """A mask stands alone: no ``?`` or mask is glued to a character of a name. A name hidden whole is an over-cut,
    which the corpus gates count, not a mask inside it."""

    @settings(max_examples=EXAMPLES)
    @given(case=_named(dialect))
    def stands_alone(case: tuple[str, list[str]]) -> None:
        text, names = case
        out = statement_text(MASKER, text, dialect) or ""
        note(f"{text!r} shows {out!r}, names {names!r}")
        glued = [token for token in _MASK_TOKEN.findall(out) if token.strip("(),=-") not in ("?", MASK)]
        assert not glued, INSIDE_A_NAME

    stands_alone()


# --- the planted builds: each removes one cut, and a property must fail on it, shrunk -------------------------------

# The MariaDB `sql_mode=MSSQL` state is session-only; this template holds its one rule set.
MYSQL_84_CUTS = (
    "    cut_backslash={},\n"
    + "    cut_bracket=True,  # MariaDB `sql_mode=MSSQL` is session state no text reveals"
)  # fmt: skip
NO_BACKSLASH_CUT = Mutant(MYSQL_84_CUTS.format(True), MYSQL_84_CUTS.format(False), "", "", "engine/sqltext/rules.py")
# the session readings cut most of the same text: the plant takes both, or the field's removal hides behind them
NO_SESSION_READINGS = Mutant(
    "    return rule_sets[1:] + session\n", "    return rule_sets[1:]\n", "", "", "engine/sqltext/family.py"
)
# Task 18's ``hide_double_quoted`` in rules.py: SQLite hides every ``"`` run; a moved anchor fails as a stale plant
SHOWS_DOUBLE_QUOTED = Mutant("hide_double_quoted=True", "hide_double_quoted=False", "", "", "engine/sqltext/rules.py")
# the other two properties' controls: a cut that reads on past itself, and a digit that leaves its name (``col1``)
TAIL_AFTER_CUT = Mutant("    head = _read(source[:cut], rules)\n", "    head = _read(source, rules)\n", "", "")
_CUT_SCAN = "        out.text(),\n"
# a cut that shows its head raw: a literal before the cut stays visible, and every character still comes from the head
RAW_HEAD = Mutant(_CUT_SCAN, '        source[:cut] + " ?",\n', "", "")
DIGIT_LEAVES_NAME = MUTANTS["digit_in_name"]
LITERAL, CUT = "test_a_literal_never_survives", "test_a_cut_only_shortens"
PLANTS: dict[str, tuple[str, Dialect, tuple[Mutant, ...], str]] = {
    "mysql_family-cut_backslash": (LITERAL, Dialect.MYSQL_FAMILY, (NO_BACKSLASH_CUT, NO_SESSION_READINGS), LEAK),
    "sqlite-hide_double_quoted": (LITERAL, Dialect.SQLITE, (SHOWS_DOUBLE_QUOTED,), LEAK),
    "postgresql-tail_after_cut": (CUT, Dialect.POSTGRESQL, (TAIL_AFTER_CUT,), PAST_THE_CUT),
    "mysql_family-raw_head": (CUT, Dialect.MYSQL_FAMILY, (RAW_HEAD,), PAST_THE_CUT),
    "postgresql-digit_leaves_name": (
        "test_the_output_never_grows_a_mask_inside_a_name",
        Dialect.POSTGRESQL,
        (DIGIT_LEAVES_NAME,),
        INSIDE_A_NAME,
    ),
}
PLANT_SECONDS = 50


def _property_run(src: Path, test: str, dialect: Dialect) -> subprocess.CompletedProcess[str]:
    node = f"tests/masking/test_properties.py::{test}[{IDS[dialect]}]"
    env = {**os.environ, "PYTHONPATH": str(src), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider", "-p", "no:xdist", "--tb=short"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=PLANT_SECONDS,
    )  # fmt: skip


@pytest.mark.timeout(2 * PLANT_SECONDS)
@pytest.mark.parametrize("plant", PLANTS)
def test_a_property_catches_a_removed_cut(plant: str, tmp_path: Path) -> None:
    test, dialect, mutants, message = PLANTS[plant]
    copy = _scratch_copy(tmp_path)
    for mutant in mutants:
        _mutate(copy, mutant)  # a stale anchor fails here, naming the anchor and its file
    done = _property_run(tmp_path / "src", test, dialect)
    assert done.returncode == 1, f"{plant} survives the property: {done.stdout[-1500:]}"
    shrunk = "Failing test case" in done.stdout or "Falsifying example" in done.stdout  # hypothesis 6.1xx says either
    assert shrunk, done.stdout[-1500:]
    assert message in done.stdout, done.stdout[-1500:]  # the property's own assertion, not a crash
