"""Error text by region (spec §3): each region has one owner, every job reads raw text, and the output is emitted once.

Text is a driver line, frames, a ``[SQL: `` block, its parameters, a trailer and the docs link. Nothing rendered here is
read again, so what one region hides cannot change what another decides.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Iterator
from types import MappingProxyType, MemberDescriptorType
from typing import cast

from sharpit.engine import sqltext
from sharpit.engine.masking import MASK, Exposure, Masker, Tracked
from sharpit.engine.sqltext import Dialect, is_database_exception, statement_text
from sharpit.engine.sqltext.constants import UNSUPPORTED_STATEMENT
from sharpit.engine.sqltext.dialect import _class_value  # pyright: ignore[reportPrivateUsage]

_BREAKS = r"\n\r\x0b\x0c\x1c\x1d\x1e\x85  "  # every separator ``str.splitlines`` knows
_LINE_START = rf"(?<![^{_BREAKS}])"
_LINE_BREAK = re.compile(rf"\r\n|[{_BREAKS}]")
_BLOCK = "[SQL: "
_BLOCK_LINE = re.compile(_LINE_START + re.escape(_BLOCK))
_BLOCK_HIDDEN = f"{_BLOCK}{MASK}]"
_PARAMETERS = re.compile(r"\s*+\[parameters: ")
_PARAMETERS_LINE = "\n[parameters: "
_PARAMETERS_HIDDEN = f"[parameters: {MASK}]"
# SQLAlchemy's own text and a URL of its own shape, so a line a value planted shows nothing even if it is taken for this
_LINK = re.compile(_LINE_START + r"\(Background on this error at: https://sqlalche\.me/e/\w+/\w+\)")
_DRIVERS = (
    r"sqlalchemy\.(?:exc|engine|dialects)|psycopg2?|sqlite3|aiosqlite|asyncpg|asyncmy|aiomysql|pymysql|MySQLdb|mariadb"
    r"|mysql(?:\.connector)?"
)
# the lookbehind and the possessive run: ``sqlite3.sqlite3.`` starts once, a restart at each name would be quadratic
_AN_ERROR = re.compile(
    rf"\[SQL: |{_LINE_START}(?:DETAIL|Detail|HINT|CONTEXT|LINE \d+):|(?<![\w.])(?:{_DRIVERS})\.[\w.]*+[):]"
    r"""|\A\(\d+, ["']"""
)
# a MySQL driver named on the driver line, with a proof that is not MySQL's, is a conflict: the block hides
_MYSQL_NAMED = re.compile(r"\b(?:pymysql|MySQLdb|asyncmy|mariadb|mysql\.connector)\.")
_DROPPED = ("DETAIL:", "Detail:")
_QUOTE = re.compile("['\"]")
_QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")  # the view 0.4.0 masked: what it hid stays hidden
_TUPLE_OPEN = re.compile(r"\(\d+, $")  # PyMySQL's ``(1062, "..."``: the message is what is quoted, its values inside
_TRUNCATED = re.compile(r" \.\.\. \(?\d+ characters truncated\)? \.\.\. ")
_TRACEBACK = "Traceback (most recent call last):"
_CHAINS = frozenset(
    {
        "The above exception was the direct cause of the following exception:",
        "During handling of the above exception, another exception occurred:",
    }
)
_FRAMES, _DRIVER, _TAIL, _TRAILER = range(4)  # where a walk stands: what the next line is
# BaseException's own descriptors, as ``dialect`` reads links: a subclass property of the same name never runs
_ARGS = BaseException.__dict__["args"]
_FIELDS = BaseException.__dict__["__dict__"]
# owner 2026-11-07, structured driver codes: after an int ``args[0]``, the first exact str of its code's shape is shown
_SQLSTATE = re.compile(r"[0-9A-Z]{5}")
_CODES = (("sqlstate", _SQLSTATE), ("pgcode", _SQLSTATE), ("sqlite_errorname", re.compile(r"SQLITE_[A-Z_]+")))
_UNSET = object()
# owner 2026-11-07, item 8: an ``UNSUPPORTED`` error shows a leading class, its block as the marker and the constant
# parameters region. Only a dotted name in parentheses is a class; a value can shape one, so the secret passes read
# it at ``MASKED`` whatever the exposure
_CLASS = re.compile(r"\A\(((?:[A-Za-z_]\w{0,99}\.){1,9}[A-Za-z_]\w{0,99})\)")
_HEAD_CHECK = Masker(Exposure.MASKED, True)
_BLOCK_UNSUPPORTED = f"{_BLOCK}{UNSUPPORTED_STATEMENT}]"


def _merged(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for low, high in sorted(spans):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


class _Hits:
    """The hidden raw spans of a text, merged and sorted once. Lines are read in order, so a span is passed once."""

    def __init__(self, text: str, spans: Iterable[tuple[int, int]]) -> None:
        self._text = text
        self._spans = _merged(spans)
        self._next = 0

    def shown(self, start: int, end: int) -> str:
        """``text[start:end]`` with each hit one mask."""
        spans = self._spans
        pieces: list[str] = []
        cursor = start
        while self._next < len(spans) and spans[self._next][0] < end:
            low, high = spans[self._next]
            if high > cursor:
                pieces += (self._text[cursor : max(low, cursor)], MASK)
                cursor = high
            if high > end:  # it goes on past this range
                break
            self._next += 1
        pieces.append(self._text[cursor:end])
        return "".join(pieces)

    def around(self, start: int, end: int, quoted: tuple[int, int] | None) -> str:
        """``shown``, with ``quoted``, relative to ``start``, as one ``?``."""
        if quoted is None:
            return self.shown(start, end)
        return f"{self.shown(start, start + quoted[0])}?{self.shown(start + quoted[1], end)}"


def _quoted(line: str) -> tuple[int, int] | None:
    """Where a line's quoted text runs, first quote to last: which quote closes which is a guess, and a value can hold
    one. An odd count of either runs to the end, because the last quote may open what follows it."""
    first = _QUOTE.search(line)
    if first is None:
        return None
    low, high = 0, len(line)
    closes = (
        line.endswith(f"{first[0]})") and line.find(first[0], first.end(), high - 2) < 0
    )  # a repr holds no bare quote
    if closes and _TUPLE_OPEN.search(line, 0, first.start()):
        inner = _QUOTE.search(line, first.end(), high - 2)
        if inner is not None:
            low, high, first = first.end(), high - 2, inner
    last = max(line.rfind("'", low, high), line.rfind('"', low, high))
    odd = line.count("'", low, high) % 2 or line.count('"', low, high) % 2
    return first.start(), high if odd else last + 1


def _views(line: str, quoted: tuple[int, int]) -> Iterator[Tracked]:
    """The two reads of a driver line beside the raw one: a key can sit on either side of a quote."""
    first_to_last = Tracked(line)
    first_to_last.apply([(*quoted, "?")])
    yield first_to_last
    released = Tracked(line)
    released.apply([(found.start(), found.end(), "?") for found in _QUOTED.finditer(line, *quoted)])
    yield released


def _driver_line(masker: Masker, line: str) -> str:
    quoted = _quoted(line)
    spans = list(masker.mask_spans(line) or ())
    for view in _views(line, quoted) if quoted else ():
        spans += masker.mask_spans(line, True, view) or ()
    return _Hits(line, spans).around(0, len(line), quoted)


class _Lines:
    """One walk over the lines of a region, on raw offsets: frames, a driver line, and what follows them."""

    def __init__(self, masker: Masker, region: str, state: int, keep_frames: bool) -> None:
        self._masker = masker
        self._region = region
        self._state = state
        self._keep_frames = keep_frames
        self.shown: list[str] = []
        self.named: Dialect | None = None  # the family the driver line names: a mark that can only hide

    @functools.cached_property
    def _hits(self) -> _Hits:
        """Strict passes over the whole region, so that a value across lines is one hit."""
        return _Hits(self._region, self._masker.mask_spans(self._region) or ())

    def walk(self) -> list[str]:
        start = 0
        for found in _LINE_BREAK.finditer(self._region):
            if not self._line(start, found.start()):
                return self.shown
            start = found.end()
        self._line(start, len(self._region))
        return self.shown

    def _line(self, start: int, end: int) -> bool:
        """Emit one line; false when nothing after it may be read."""
        line = self._region[start:end]
        if line.startswith(_BLOCK):  # the first block ends the head, so this is a second one
            self.shown.append(_BLOCK_HIDDEN)
            return False
        if line.strip() and not line.startswith(_DROPPED):
            self._dispatch(line, start, end)
        return True

    def _dispatch(self, line: str, start: int, end: int) -> None:
        if line == _TRACEBACK and self._state != _TAIL:
            self._state = _FRAMES if self._keep_frames else _TAIL  # the recorder keeps no frames, as at 0.4.0
            self.shown.append(line)
        elif self._state == _FRAMES and line.startswith("  "):
            self._kept(start, end, quotes=not line.startswith("  File "))
        elif self._state in (_FRAMES, _DRIVER):
            self._driver(line)
        elif self._state == _TRAILER:
            self._kept(start, end, quotes=True)
        elif line in _CHAINS and self._keep_frames:
            self._state = _TRAILER
            self.shown.append(line)

    def _driver(self, line: str) -> None:
        self._state = _TAIL
        cut = line.find(_BLOCK)
        text = line if cut < 0 else line[:cut]
        quote = _QUOTE.search(text)
        named = _MYSQL_NAMED.search(text, 0, quote.start() if quote else len(text))
        self.named = self.named or (Dialect.MYSQL_FAMILY if named else None)
        self.shown.append(_driver_line(self._masker, text) + ("" if cut < 0 else _BLOCK_HIDDEN))

    def _kept(self, start: int, end: int, quotes: bool) -> None:
        cut = self._region.find(_BLOCK, start, end)
        stop = end if cut < 0 else cut
        quoted = _quoted(self._region[start:stop]) if quotes else None
        self.shown.append(self._hits.around(start, stop, quoted) + ("" if cut < 0 else _BLOCK_HIDDEN))


def _final_link(text: str) -> re.Match[str] | None:
    """The last line that is SQLAlchemy's docs link: a parameters repr can hold one, and SQLAlchemy writes the last."""
    found = None
    for found in _LINK.finditer(text):  # noqa: B007
        pass
    return found


def _block(masker: Masker, text: str, body: int, end: int, dialect: Dialect, shown: list[str]) -> int:
    """Emit the block whose body starts at ``body``, and its parameters; where the text goes on."""
    statement = text[body:end]
    closer = sqltext.LEXER.block_closer(statement, dialect)
    later = _BLOCK_LINE.search(statement, 0, closer if closer >= 0 else len(statement))
    if later is not None and "]" not in statement[: later.start()]:
        shown.append(_BLOCK_HIDDEN)
        return end
    # no closer, or none to trust (the statement reads two ways): it runs on, to its parameters
    if closer < 0 or sqltext.LEXER.reads_two_ways(statement[:closer], dialect):
        parameters = statement.rfind(_PARAMETERS_LINE)
        read = statement if parameters < 0 else statement[:parameters]
        # a run-on that stops at a line SQLAlchemy writes, its parameters or its final docs link, ends the block there
        closed = parameters >= 0 or _LINK.match(text, end) is not None
        shown.append(f"{_BLOCK}{statement_text(masker, read, dialect)}{']' if closed else ''}")
        if parameters >= 0:
            shown.append(_PARAMETERS_HIDDEN)
        return end
    shown.append(f"{_BLOCK}{statement_text(masker, statement[:closer], dialect)}]")
    resume = body + closer + 1
    if _PARAMETERS.match(text, resume, end):
        shown.append(_PARAMETERS_HIDDEN)
        return end
    return resume


def _render(masker: Masker, text: str, dialect: Dialect, keep_frames: bool) -> str:
    link = _final_link(text)
    end = link.start() if link else len(text)
    block = _BLOCK_LINE.search(text, 0, end)
    head = _Lines(masker, text[: block.start() if block else end], _DRIVER, keep_frames)
    shown = head.walk()
    # a driver named in the text can be a value's word: it can reveal a conflict, which hides, and never reads
    conflict = block is not None and head.named is not None and head.named is not dialect
    if conflict:
        shown.append(_BLOCK_HIDDEN)
    resume = _block(masker, text, block.end(), end, dialect, shown) if block and not conflict else end
    shown += _Lines(masker, text[resume:end], _TRAILER, keep_frames).walk()
    if link:
        shown.append(link[0])
        shown += _Lines(masker, text[link.end() :], _TRAILER, keep_frames).walk()
    return "\n".join(shown)


def _plain_head(masker: Masker, head: str) -> bool:
    return masker.mask_text(head) == head and _HEAD_CHECK.mask_text(head) == head


def _unsupported(masker: Masker, text: str) -> str:
    """An error of a provider sharpit cannot read, as a classified one: never the driver's free text (item 8)."""
    shown: list[str] = []
    head = _CLASS.match(text)
    if head is not None and _plain_head(masker, head[0]):
        shown.append(head[0])
    block = text.find(_BLOCK)
    if block >= 0:
        shown.append(_BLOCK_UNSUPPORTED)
        if "[parameters: " in text[block:]:
            shown.append(_PARAMETERS_HIDDEN)
    return "\n".join(shown) or MASK


def render_error(masker: Masker, text: str, dialect: Dialect, keep_frames: bool = True) -> str:
    """``text`` by region; ``""`` under ``METADATA_ONLY``, ``******`` if the render fails.

    The block reads with ``dialect``. A driver named in the text marks a region and never picks the reading: a database
    can return a driver-shaped string as a value (architecture spec section 6). A MySQL driver on the driver line with
    another ``dialect`` is a conflict, and the block hides.
    """
    try:
        if masker.mask_spans("") is None:
            return ""
        if dialect is Dialect.UNSUPPORTED:
            return _unsupported(masker, text)
        return _render(masker, text, dialect, keep_frames)
    except Exception:
        return MASK


def mask_error(
    masker: Masker, text: str | None, dialect: Dialect, known: bool = False, keep_frames: bool = True
) -> str | None:
    """An error text for display: every path from an exception to output comes here.

    ``known`` is for text certain to come from a database. Free text pays one search and is ``mask_text``'s.
    """
    if text is None:
        return None
    if dialect is Dialect.UNSUPPORTED and (known or _AN_ERROR.search(text)):  # capture on does not lift the hide
        return render_error(masker, text, dialect, keep_frames) or None  # (owner, item 7); METADATA_ONLY gives ""
    if masker.capture_parameters or not (known or _AN_ERROR.search(text)):
        return masker.mask_text(text)
    return render_error(masker, text, dialect, keep_frames) or masker.mask_text("")


def log_statement(masker: Masker, text: str, dialect: Dialect) -> str | None:
    """A record from ``sqlalchemy.engine``: a statement, read with the application's family.

    SQLAlchemy's cut can take a quote and flip every quote after it, so nothing past it is read.
    """
    cut = _TRUNCATED.search(text)
    return statement_text(masker, text[: cut.start()] if cut else text, dialect)


def _plain_field(driver: BaseException, fields: dict[str, object], name: str) -> object:
    """``name`` as plain data, looked up as ``getattr`` would: a slot or C member is read through its own descriptor;
    any other descriptor (a property) never runs and stands for no value."""
    for cls in cast(tuple[type, ...], _class_value(type(driver), "__mro__")):
        found = cast(MappingProxyType[str, object], _class_value(cls, "__dict__")).get(name, _UNSET)
        if found is _UNSET:
            continue
        if type(found) is MemberDescriptorType:
            try:
                return found.__get__(driver)
            except AttributeError:  # an unset slot
                return None
        return fields.get(name, found) if found is None or type(found) is str else None
    return fields.get(name)


def _driver_code(driver: BaseException) -> int | str | None:
    args = cast(tuple[object, ...], _ARGS.__get__(driver))
    if args and type(args[0]) is int:
        return args[0]
    raw_fields = _FIELDS.__get__(driver)
    fields = cast(dict[str, object], raw_fields) if type(raw_fields) is dict else {}
    for name, shape in _CODES:
        value = _plain_field(driver, fields, name)
        if type(value) is str and shape.fullmatch(value):
            return value
    return None


def _classified_text(source: BaseException, fields: dict[str, object], dialect: Dialect) -> str | None:
    """A database exception's own facts: its driver class, a structured code and its statement. The driver's text is
    free text a value can shape, so it is never shown; with neither a code nor a statement there is nothing to show.
    An ``UNSUPPORTED`` statement is the marker: its text is never read (owner, item 8)."""
    original = fields.get("orig")
    driver = cast(BaseException, original) if issubclass(type(original), BaseException) else source
    code = _driver_code(driver)
    statement = fields.get("statement")
    if code is None and type(statement) is not str:
        return None
    module, name = _class_value(type(driver), "__module__"), _class_value(type(driver), "__qualname__")
    if type(module) is not str or type(name) is not str:
        return None
    text = f"({module}.{name})" if code is None else f"({module}.{name}) {code}"
    if type(statement) is not str:
        return text
    # owner 2026-11-07: the region stays as a constant, so the reader knows values were bound; none is ever read
    bound = fields.get("params")  # as SQLAlchemy prints it: no line for no values; only exact containers are sized
    empty = bound is None or (type(bound) in (tuple, list, dict) and not cast(tuple[object, ...], bound))
    params = "" if empty else f"\n{_PARAMETERS_HIDDEN}"
    if dialect is Dialect.UNSUPPORTED:
        return f"{text}\n{_BLOCK_UNSUPPORTED}{params}"
    return f"{text}\n[SQL: {statement}]{params}"


def error_text(
    masker: Masker, source: str | BaseException, dialect: Dialect, known: bool = False, keep_frames: bool = True
) -> str | None:
    """Render free text or a database exception through the same regions and exposure policy."""
    if type(source) is str:
        return mask_error(masker, source, dialect, known, keep_frames)
    exc = cast(BaseException, source)
    try:
        raw_fields = _FIELDS.__get__(exc)
        fields = cast(dict[str, object], raw_fields) if type(raw_fields) is dict else {}
        if is_database_exception(exc):
            classified = _classified_text(exc, fields, dialect)
            if classified is None or dialect is not Dialect.UNSUPPORTED:
                return None if classified is None else mask_error(masker, classified, dialect, True, keep_frames)
            return None if masker.mask_spans("") is None else classified
        statement = fields.get("statement")
        args = cast(tuple[object, ...], _ARGS.__get__(exc))
        if not args or sum(len(value) for value in args if type(value) is str) > 100_000:
            return None
        text = " ".join(value for value in args if type(value) is str)
    except Exception:  # noqa: BLE001 - unreadable exception objects fail closed
        return None
    if not text:
        return None
    return mask_error(masker, text, dialect, known or type(statement) is str, keep_frames)
