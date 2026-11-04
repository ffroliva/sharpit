"""A seeded SQL corpus for the masking gates: each row is a statement, what must stay hidden and what must be shown.

Ported from ``probe8/sqlgen2.py``, which gained ``expected``, the dialects and statements over the scan limit. No I/O
and no import of sharpit: ``expected`` is written from the template beside the raw text, so it cannot agree with a lexer
by sharing its code (spec A3, revision 2's oracle compared ``normalize`` with itself and passed three blanking builds).

Statement conventions for ``generic`` and ``mysql``: a literal is ``?``, a comment and a whitespace run are one space,
an ``IN`` list of bare literals is ``IN (?)``, the ends are stripped. An ambiguous statement is its text up to the first
quote, under the same conventions, followed by `` ?``. ``postgresql`` is ``postgresql/querytext.py``'s shape:
``'******'``, ``$$******$$`` and ``******``, which drops comments, collapses whitespace, keeps ``IN`` lists and reads
every run to its end.

Ambiguous classes: ``trailing_backslash``, ``nested_comment``, ``oracle_quote``, ``hash`` and ``odd_bracket`` in
``generic``; ``trailing_backslash`` in ``postgresql``, where the scan has no PostgreSQL mode, so the statement takes the
generic cut and loses its tail (spec A3 allows that on a row marked ambiguous); ``mysql_escaped`` in ``mysql`` (D7).
``quiet_trigger`` rows read one way and are never marked: a statement that loses its tail there fails A3.

``expected`` is exact on ``plain`` rows. Elsewhere a hit may render ``******``, so ``tail`` carries the part of the
statement that must survive it (spec A3: a statement on a sensitive column keeps its other clauses).
"""

from __future__ import annotations

import random
import string
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

GENERIC = "generic"
MYSQL = "mysql"
POSTGRESQL = "postgresql"
SCAN_LIMIT = 20_000  # the scanner's limit, restated: past it nothing is scanned or shown
LONG_EVERY = 100  # one row in this many is a statement over the limit
MASKED = "******"

_COLUMNS = ("name", "note", "title", "bio", "label", "descr", "status", "city", "col1", "x2", "is_True", "not_False")
_SENSITIVE_NAMES = ("basic", "bearer", "token", "password", "pwd", "api_key", "secret", "auth")
# the separator beside a sensitive name, as written and as shown
_SEPARATORS = ((" = ", " = "), ("=", "="), ("=\n", "= "), (" =\n  ", " = "))
_PLAIN_OPENERS = ("", "plan", "note: x", "x;y", "x, y", "[1", "(a", "{b", "it''s", "o''clock", "a''b", "100%", "#tag",
                  "-- not a comment", "/* nope", "$1", "a]", "]\n(Background on x", "tail\\")  # fmt: skip
_SENSITIVE_OPENERS = ("Basic plan", "Bearer of bad news", "Token ring", "password: x", "key=value", "secret sauce",
                      "http://a:b@c/d", "see http://x.io/?token=1", "Authorization: x", "Cookie: a=b")  # fmt: skip
_OPENERS = _PLAIN_OPENERS + _SENSITIVE_OPENERS


@dataclass(frozen=True)
class Row:
    text: str  # the statement
    markers: tuple[str, ...]  # must stay hidden
    shape: str  # the class of statement
    plain: bool  # no name or literal opener in it is sensitive: the output must equal ``expected``
    expected: str  # what the statement surface shows, from the template
    quoted_identifier: tuple[str, ...] = ()  # decision D6, issue #59: shown as identifiers, counted and not failed
    ambiguous: bool = False  # reads two ways: stops at its first quote
    tail: str = ""  # what follows the literals in the statement: a row that is not ambiguous keeps it


class _Literal(NamedTuple):
    marker: str
    raw: str
    scan: str  # as ``generic`` and ``mysql`` show it
    pg: str  # as ``postgresql`` shows it
    sensitive: bool = False
    identifier: bool = False  # ``"word"``, a name outside a value position
    before: str = ""  # a marker ahead of the opener: a masker that keeps the opener shows it


class _Shown(NamedTuple):
    text: str
    scan: str
    pg: str


def _mark(rng: random.Random) -> str:
    return "MK" + "".join(rng.choices(string.ascii_lowercase + string.digits, k=12))


def _digits(rng: random.Random) -> str:
    return str(rng.randint(10**9, 10**10 - 1))


def _double_word(rng: random.Random) -> _Literal:
    m = _mark(rng)
    return _Literal(m, f'"{m}"', "?", "", identifier=True)


def _double_spaced(rng: random.Random) -> _Literal:
    m = _mark(rng)
    return _Literal(m, f'"a b {m}"', "?", "")


def _dollar(rng: random.Random) -> _Literal:
    m = _mark(rng)
    return _Literal(m, f"$${m}$$", "?", f"$${MASKED}$$")


def _dollar_tag(rng: random.Random) -> _Literal:
    m = _mark(rng)
    return _Literal(m, f"$tag${m} it's$tag$", "?", f"$${MASKED}$$")


def _hex(rng: random.Random) -> _Literal:
    d = _digits(rng)
    return _Literal(d, f"0x{d}", "?", MASKED)


def _leading_dot(rng: random.Random) -> _Literal:
    d = _digits(rng)
    return _Literal(d, f".{d}", "?", MASKED)


def _exponent(rng: random.Random) -> _Literal:
    d = _digits(rng)
    return _Literal(d, f"{d}{rng.choice(('e5', 'E3', 'e+5', 'E-12'))}", "?", MASKED)  # a sign is part of the number


def _boolean(rng: random.Random) -> _Literal:  # PostgreSQL's text keeps ``true`` readable, so it has no such literal
    word = rng.choice(("true", "FALSE"))  # not a spelling a column below carries: its marker must not match a name
    return _Literal(word, word, "?", "")


def _double_secret(rng: random.Random) -> _Literal:
    """A name-shaped ``"..."`` that is a secret: a vendor token, assembled here so no scanner reads it in the source."""
    secret = "sk_" + "live_" + "".join(rng.choices(string.ascii_letters + string.digits, k=24))
    return _Literal(secret, f'"{secret}"', "?", "")


def _underscored(rng: random.Random) -> _Literal:
    d = _digits(rng)
    return _Literal(d[3:], f"{d[:3]}_{d[3:]}", "?", MASKED)


def _escape_string(rng: random.Random) -> _Literal:
    m = _mark(rng)
    return _Literal(m, f"E'{m}'", "E?", f"'{MASKED}'")


def _multi_line(rng: random.Random) -> _Literal:
    m = _mark(rng)
    return _Literal(m, f"'line one\n{m}\nline three'", "?", f"'{MASKED}'")


def _string(rng: random.Random) -> _Literal:
    m = _mark(rng)
    opener = rng.choice(_OPENERS)
    sensitive = opener in _SENSITIVE_OPENERS
    before = _mark(rng) if sensitive and rng.random() < 0.5 else ""
    head = f"{before} " if before else ""
    return _Literal(m, f"'{head}{opener} {m}'", "?", f"'{MASKED}'", sensitive, before=before)


_DOUBLE_QUOTED = (_double_word, _double_spaced, _double_secret, _boolean)  # not PostgreSQL's: no literal there
_NOT_MYSQL = (_dollar, _dollar_tag, _escape_string)  # text a MySQL server reads differently or refuses
_COMMON = (_hex, _leading_dot, _exponent, _underscored, _multi_line, _string, _string, _string)
_LITERALS = {
    GENERIC: (*_DOUBLE_QUOTED, *_NOT_MYSQL, *_COMMON),
    MYSQL: (*_DOUBLE_QUOTED, *_COMMON),
    POSTGRESQL: (*_NOT_MYSQL, *_COMMON),  # PostgreSQL reads ``"..."`` as an identifier, so it holds no literal
}


def _hidden(literals: tuple[_Literal, ...]) -> tuple[str, ...]:
    return tuple(marker for literal in literals for marker in (literal.before, literal.marker) if marker)


class _Statements:
    """The templates of one dialect. Each returns a ``Row``: raw text and shown text are written side by side."""

    def __init__(self, rng: random.Random, dialect: str) -> None:
        self.rng = rng
        self.dialect = dialect
        self.pg = dialect == POSTGRESQL
        self.number = MASKED if self.pg else "?"
        self.string = f"'{MASKED}'" if self.pg else "?"

    def _literal(self) -> _Literal:
        return self.rng.choice(_LITERALS[self.dialect])(self.rng)

    def _row(self, shape: str, shown: _Shown, literals: tuple[_Literal, ...], tail: str, *, plain: bool = True) -> Row:
        return Row(
            shown.text,
            _hidden(literals),
            shape,
            plain and not any(literal.sensitive for literal in literals),
            shown.pg if self.pg else shown.scan,
            tail=tail,
        )

    def _single(self, shape: str, shown: _Shown, marker: str, *, ambiguous: bool = False) -> Row:
        return Row(shown.text, (marker,), shape, True, shown.pg if self.pg else shown.scan, ambiguous=ambiguous)

    def _pair(self) -> tuple[_Literal, _Literal, str, str, str, str]:
        a, b = self._literal(), self._literal()
        first, second = self.rng.sample(_COLUMNS, 2)
        return a, b, first, second, a.pg if self.pg else a.scan, b.pg if self.pg else b.scan

    def update(self) -> Row:
        a, b, c1, c2, sa, sb = self._pair()
        text = f"UPDATE t SET {c1}={a.raw}, {c2}={b.raw} WHERE id=1"
        shown = f"UPDATE t SET {c1}={sa}, {c2}={sb} WHERE id={self.number}"
        return self._row("shapes", _Shown(text, shown, shown), (a, b), f"WHERE id={self.number}")

    def insert(self) -> Row:
        a, b, c1, c2, sa, sb = self._pair()
        text = f"INSERT INTO t ({c1}, {c2}) VALUES ({a.raw}, {b.raw})"
        tail = f"VALUES ({sa}, {sb})"
        shown = f"INSERT INTO t ({c1}, {c2}) {tail}"
        return self._row("shapes", _Shown(text, shown, shown), (a, b), tail)

    def select(self) -> Row:
        a, b, c1, c2, sa, sb = self._pair()
        text = f"SELECT id FROM t WHERE {c1} = {a.raw} AND {c2} IN ({b.raw}, 'z')"
        head = f"SELECT id FROM t WHERE {c1} = {sa} AND {c2} IN "
        collapsed = "(?)" if sb == "?" else f"({sb}, ?)"  # ``E?`` is not a bare placeholder, so the list stays
        shown = _Shown(text, f"{head}{collapsed}", f"{head}({sb}, {self.string})")
        return self._row("shapes", shown, (a, b), f"AND {c2} IN")

    def sensitive_name(self) -> Row:  # the scheme and key names beside a value: finding 1 and predict's newline pair
        a, b, _, c2, sa, sb = self._pair()
        name = self.rng.choice(_SENSITIVE_NAMES)
        written, collapsed = self.rng.choice(_SEPARATORS)
        text = f"UPDATE t SET {name}{written}{a.raw}, {c2} = {b.raw} WHERE id=1"
        shown = f"UPDATE t SET {name}{collapsed}{sa}, {c2} = {sb} WHERE id={self.number}"
        return self._row("sensitive_name", _Shown(text, shown, shown), (a, b), f"WHERE id={self.number}", plain=False)

    def sensitive_table(self) -> Row:
        a, b, _, _, sa, sb = self._pair()
        name = self.rng.choice(_SENSITIVE_NAMES)
        text = f"INSERT INTO {name} VALUES (1, {a.raw}, {b.raw})"
        tail = f"({self.number}, {sa}, {sb})"
        shown = f"INSERT INTO {name} VALUES {tail}"
        return self._row("sensitive_table", _Shown(text, shown, shown), (a, b), tail, plain=False)

    def comments(self) -> Row:  # comments holding a quote
        a, b, _, _, sa, sb = self._pair()
        names = ()
        if self.dialect == GENERIC:  # nothing here is a value position: ``"word"`` is a name, shown as at 0.4.0
            while a.identifier and b.identifier:  # a row with no marker could never fail A1
                b = self._literal()
                sb = b.scan
            names = tuple(literal.marker for literal in (a, b) if literal.identifier)
            sa, sb = a.raw if a.identifier else sa, b.raw if b.identifier else sb
        text = f"SELECT /* it's */ {a.raw} -- don't\n , {b.raw} FROM t"
        hidden = _hidden(tuple(literal for literal in (a, b) if not (names and literal.identifier)))
        plain = not (a.sensitive or b.sensitive)
        return Row(text, hidden, "comments", plain, f"SELECT {sa} , {sb} FROM t", names, tail="FROM t")

    def trailing_backslash(self) -> Row:  # finding 2: a literal reads to here, or on through the rest of the statement
        m = _mark(self.rng)
        column = self.rng.choice(_COLUMNS)
        text = f"UPDATE t SET path='C:\\', {column}='{m} x' WHERE id=1"
        shown = _Shown(text, "UPDATE t SET path= ?", f"UPDATE t SET path='{MASKED}'")
        return self._single("trailing_backslash", shown, m, ambiguous=True)

    def nested_comment(self) -> Row:  # PostgreSQL nests comments, so there it reads one way
        m = _mark(self.rng)
        shown = _Shown(f"/* /* nested */ it's */ SELECT '{m}'", "it ?", f"SELECT '{MASKED}'")
        return self._single("nested_comment", shown, m, ambiguous=not self.pg)

    def oracle_quote(self) -> Row:
        m = _mark(self.rng)
        shown = _Shown(f"SELECT q'[it's {m}]' FROM dual", "SELECT q ?", "")
        return self._single("oracle_quote", shown, m, ambiguous=True)

    def hash_comment(self) -> Row:
        m = _mark(self.rng)
        text = f"SELECT # it's\n '{m}'"
        if self.dialect == MYSQL:  # a comment there, and the statement reads one way
            return self._single("hash", _Shown(text, "SELECT ?", ""), m)
        return self._single("hash", _Shown(text, "SELECT # it ?", ""), m, ambiguous=True)

    def mysql_escaped(self) -> Row:  # D7: under NO_BACKSLASH_ESCAPES the run ends at the backslash
        m = _mark(self.rng)
        column = self.rng.choice(_COLUMNS)
        quote = self.rng.choice("'\"")
        text = f"UPDATE t SET {column}={quote}a\\{quote}{m}{quote} WHERE id=1"
        return self._single("mysql_escaped", _Shown(text, f"UPDATE t SET {column}= ?", ""), m, ambiguous=True)

    def quiet_trigger(self) -> Row:  # reads one way: a comment or a closed name holds a trigger as text (spec A3)
        m = _mark(self.rng)
        text, scan = self.rng.choice(
            (
                (f"-- ticket #12\nSELECT '{m}', 'y'", "SELECT ?, ?"),
                (f"SELECT 1 /* # q' */, '{m}'", "SELECT ? , ?"),
                (f"SELECT `a#b`, '{m}', 'y'", "SELECT `a#b`, ?, ?"),
                (f"SELECT `q'a`, '{m}', 'y'", "SELECT `q'a`, ?, ?"),
                (f"SELECT `a\\b`, '{m}', 'y'", "SELECT `a\\b`, ?, ?"),
                (f"SELECT \"C:\\dir\", '{m}'", "SELECT ?, ?"),
            )
        )
        return self._single("quiet_trigger", _Shown(text, scan, ""), m)

    def names(self) -> Row:  # quoted names and arrays beside a literal
        m = _mark(self.rng)
        if self.pg:
            shown = _Shown(f"SELECT ARRAY['{m}', 'z'] FROM t", "", f"SELECT ARRAY['{MASKED}', '{MASKED}'] FROM t")
            return self._single("names", shown, m)
        if self.dialect == MYSQL:
            name = self.rng.choice(("a b", "it's"))  # a quote inside a name is not a string
            return self._single("names", _Shown(f"SELECT `{name}`, '{m}' FROM t", f"SELECT `{name}`, ? FROM t", ""), m)
        if self.rng.random() < 0.2:  # a name-shaped secret outside a value position: only a secret check hides it
            secret = _double_secret(self.rng).marker
            return Row(f"SELECT \"{secret}\", '{m}' FROM t", (secret, m), "names", True, "SELECT ?, ? FROM t")
        if self.rng.random() < 0.25:  # (r5) a name or a string in brackets: nothing here can tell, so it stops
            return self._single(
                "odd_bracket", _Shown(f"SELECT [it's], '{m}' FROM t", "SELECT [it ?", ""), m, ambiguous=True
            )
        if self.rng.random() < 0.25:  # a subscript past the space: the string may hold the ``]``
            text = f"SELECT ARRAY ['a]', '{m}'] FROM t"
            return self._single("names", _Shown(text, "SELECT ARRAY [?, ?] FROM t", ""), m)
        text, scan = self.rng.choice(
            (
                (f"SELECT `a b`, '{m}' FROM t", "SELECT `a b`, ? FROM t"),
                (f"SELECT `it's`, '{m}' FROM t", "SELECT `it's`, ? FROM t"),
                (f"SELECT [a b], '{m}' FROM t", "SELECT [a b], ? FROM t"),
                (f"SELECT [a 1], '{m}' FROM t", "SELECT [a 1], ? FROM t"),  # a digit in a name is not a number
                (f"SELECT ARRAY['{m}', 'z'] FROM t", "SELECT ARRAY[?, ?] FROM t"),
            )
        )
        return self._single("names", _Shown(text, scan, ""), m)

    def unclosed_dollar(self) -> Row:  # the run goes to the end, as BootUI's does
        m = _mark(self.rng)
        return self._single(
            "unclosed_dollar", _Shown(f"SELECT note, $${m} it's", "SELECT note, ?", f"SELECT note, $${MASKED}$$"), m
        )

    def long_literal(self) -> Row:
        """A literal opens before the scan limit and closes after it: a marker on each side, and one at the start."""
        early, before, after = _mark(self.rng), _mark(self.rng), _mark(self.rng)
        count = (SCAN_LIMIT - 200) // len("name='x', ")
        filler = "name='x', " * count
        text = f"UPDATE t SET note='{early}', {filler}note='{before} {'pad ' * 100}{after} tail' WHERE id=1"
        scan = f"UPDATE t SET note=?, {'name=?, ' * count}note=?"
        pg = f"UPDATE t SET note='{MASKED}', {f"name='{MASKED}', " * count}note='{MASKED}' WHERE id={MASKED}"
        return Row(text, (early, before, after), "long_literal", True, pg if self.pg else scan)

    def long_identifier(self) -> Row:
        """A ``"`` run cut open by the limit is a literal, whatever it looks like (Antigravity on revision 2)."""
        m = _mark(self.rng)
        count = (SCAN_LIMIT - 100) // len("name, ")
        text = f'SELECT {"name, " * count}"{m}{"y" * 300}" FROM t'
        return Row(text, (m,), "long_identifier", True, f"SELECT {'name, ' * count}?")

    def templates(self) -> tuple[Callable[[], Row], ...]:
        common = (self.update, self.insert, self.select, self.sensitive_name, self.sensitive_table, self.comments,
                  self.names)  # fmt: skip
        if self.dialect == MYSQL:
            return (*common, self.hash_comment, self.mysql_escaped, self.quiet_trigger)
        if self.pg:
            return (*common, self.trailing_backslash, self.nested_comment, self.unclosed_dollar)
        return (*common, self.trailing_backslash, self.nested_comment, self.oracle_quote, self.hash_comment,
                self.unclosed_dollar, self.quiet_trigger)  # fmt: skip

    def long_templates(self) -> tuple[Callable[[], Row], ...]:
        return (self.long_literal,) if self.pg else (self.long_literal, self.long_identifier)


def rows(seed: int, n: int, dialect: str = GENERIC) -> list[Row]:
    """``n`` statements for ``dialect``: the same seed gives the same rows."""
    if dialect not in _LITERALS:
        raise ValueError(dialect)
    rng = random.Random(seed)
    statements = _Statements(rng, dialect)
    templates, long_templates = statements.templates(), statements.long_templates()
    return [rng.choice(long_templates if index % LONG_EVERY == LONG_EVERY - 1 else templates)() for index in range(n)]
