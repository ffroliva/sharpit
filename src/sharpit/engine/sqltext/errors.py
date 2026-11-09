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
_SPACES = re.compile(r"\s*+")
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
_CHAINED = re.compile(rf"\s*+(?:{'|'.join(map(re.escape, sorted(_CHAINS)))})\s*+{re.escape(_TRACEBACK)}")
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


def _left_open(line: str) -> bool:
    """Whether a quote the line opens is still open at its end; a PyMySQL tuple's own quotes close its message."""
    quoted = _quoted(line)
    if quoted is None or quoted[1] != len(line):
        return False
    return line.count("'", quoted[0]) % 2 == 1 or line.count('"', quoted[0]) % 2 == 1


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
        self.open_quote = False

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
        elif line in _CHAINS and self._keep_frames and not self.open_quote:
            self._state = _TRAILER
            self.shown.append(line)

    def _driver(self, line: str) -> None:
        self._state = _TAIL
        cut = line.find(_BLOCK)
        text = line if cut < 0 else line[:cut]
        quote = _QUOTE.search(text)
        named = _MYSQL_NAMED.search(text, 0, quote.start() if quote else len(text))
        self.named = self.named or (Dialect.MYSQL_FAMILY if named else None)
        # a quote the driver line leaves open runs on into the lines below it: a chain line there is the value's
        self.open_quote = _left_open(line)
        self.shown.append(_driver_line(self._masker, text) + ("" if cut < 0 else _BLOCK_HIDDEN))

    def _kept(self, start: int, end: int, quotes: bool) -> None:
        cut = self._region.find(_BLOCK, start, end)
        stop = end if cut < 0 else cut
        quoted = _quoted(self._region[start:stop]) if quotes else None
        self.shown.append(self._hits.around(start, stop, quoted) + ("" if cut < 0 else _BLOCK_HIDDEN))


def _final_link(text: str, start: int = 0) -> re.Match[str] | None:
    """The last line from ``start`` that is SQLAlchemy's docs link: a parameters repr can hold one, and SQLAlchemy
    writes the last."""
    found = None
    for found in _LINK.finditer(text, start):  # noqa: B007
        pass
    return found


def _ends_error(text: str, at: int) -> bool:
    """Whether a link ending at ``at`` is SQLAlchemy's last line: nothing follows, or a chained traceback as Python
    writes it (a chain sentence, then ``Traceback``). A statement's remainder after a planted link is neither."""
    return not text[at:].strip() or _CHAINED.match(text, at) is not None


def _closing_link(text: str, start: int) -> tuple[int, re.Match[str] | None]:
    """Where a block whose end is unknown stops, and its link: a link with text after it may be inside the block, so
    only one that ends the text is taken, and the block hides or reads to it."""
    link = _final_link(text, start)
    if link is None or not _ends_error(text, link.end()):
        return len(text), None
    return link.start(), link


def _inner_link(text: str, at: int) -> bool:
    """Whether a link line follows ``at`` with text after it: SQLAlchemy writes its link last."""
    spaces = _SPACES.match(text, at)  # ``\s*+`` always matches
    link = _LINK.match(text, spaces.end() if spaces else at)
    return link is not None and not _ends_error(text, link.end())


def _run_on(
    masker: Masker, text: str, body: int, dialect: Dialect, shown: list[str]
) -> tuple[int, re.Match[str] | None]:
    """A block with no closer to trust: it runs on to its parameters, or to a link that ends the text."""
    parameters = text.rfind(_PARAMETERS_LINE, body)
    if parameters < 0:
        stop, link = _closing_link(text, body)
        shown.append(f"{_BLOCK}{statement_text(masker, text[body:stop], dialect)}{']' if link else ''}")
        return stop, link
    link = _final_link(text, parameters)
    shown += (f"{_BLOCK}{statement_text(masker, text[body:parameters], dialect)}]", _PARAMETERS_HIDDEN)
    return (link.start() if link else len(text)), link


def _block(
    masker: Masker, text: str, body: int, dialect: Dialect, shown: list[str]
) -> tuple[int, re.Match[str] | None]:
    """Emit the block whose body starts at ``body``, and its parameters; where the text goes on, and the docs link,
    which is taken only after the block ends: a statement's comment or dollar quote can hold a line of its shape."""
    # the lexer reads through the last link and no further: what follows it is no text of SQLAlchemy's error
    last = _final_link(text, body)
    statement = text[body : last.end() if last else len(text)]
    closer = sqltext.LEXER.block_closer(statement, dialect)
    later = _BLOCK_LINE.search(statement, 0, closer if closer >= 0 else len(statement))
    if later is not None and "]" not in statement[: later.start()]:
        shown.append(_BLOCK_HIDDEN)
        return _closing_link(text, body)
    # no closer, or none to trust (the statement reads two ways, or a link line follows it with text after: a line
    # comment's ``]`` then a planted link): it runs on, to its parameters
    if closer < 0 or sqltext.LEXER.reads_two_ways(statement[:closer], dialect) or _inner_link(text, body + closer + 1):
        return _run_on(masker, text, body, dialect, shown)
    shown.append(f"{_BLOCK}{statement_text(masker, statement[:closer], dialect)}]")
    resume = body + closer + 1
    link = _final_link(text, resume)
    end = link.start() if link else len(text)
    if _PARAMETERS.match(text, resume, end):
        shown.append(_PARAMETERS_HIDDEN)
        return end, link
    return resume, link


def _value_holds_block(text: str, block: re.Match[str], end: int) -> bool:
    """Whether a block line follows ``block`` before ``end``. After a driver line whose quote is left open, either can
    be the value's, and which one is SQLAlchemy's cannot be read (council M4, Task 35)."""
    return _BLOCK_LINE.search(text, block.end(), end) is not None


def _render(masker: Masker, text: str, dialect: Dialect, keep_frames: bool) -> str:
    link = _final_link(text)
    end = link.start() if link else len(text)
    block = _BLOCK_LINE.search(text, 0, end)
    head = _Lines(masker, text[: block.start() if block else end], _DRIVER, keep_frames)
    shown = head.walk()
    resume = end
    # text that cannot be read is not shown: a driver named with another family, or a quote left open with two
    # block lines after it, hides the block and everything to the link
    ambiguous = block is not None and head.open_quote and _value_holds_block(text, block, end)
    if block is not None and (ambiguous or (head.named is not None and head.named is not dialect)):
        shown.append(_BLOCK_HIDDEN)
        resume, link = _closing_link(text, block.end())
    elif block is not None:
        resume, link = _block(masker, text, block.end(), dialect, shown)
    end = link.start() if link else len(text)
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


def _classified_parts(source: BaseException, fields: dict[str, object]) -> tuple[str, str | None, str] | None:
    """A database exception's own facts: its driver class with a structured code, its statement and its parameters
    line. The driver's text is free text a value can shape, so it is never shown; with neither a code nor a statement
    there is nothing to show."""
    original = fields.get("orig")
    driver = cast(BaseException, original) if issubclass(type(original), BaseException) else source
    code = _driver_code(driver)
    statement = fields.get("statement")
    if code is None and type(statement) is not str:
        return None
    module, name = _class_value(type(driver), "__module__"), _class_value(type(driver), "__qualname__")
    if type(module) is not str or type(name) is not str:
        return None
    head = f"({module}.{name})" if code is None else f"({module}.{name}) {code}"
    # owner 2026-11-07: the region stays as a constant, so the reader knows values were bound; none is ever read
    bound = fields.get("params")  # as SQLAlchemy prints it: no line for no values; only exact containers are sized
    empty = bound is None or (type(bound) in (tuple, list, dict) and not cast(tuple[object, ...], bound))
    return head, statement if type(statement) is str else None, "" if empty else f"\n{_PARAMETERS_HIDDEN}"


def _classified_text(
    masker: Masker, parts: tuple[str, str | None, str], dialect: Dialect, keep_frames: bool
) -> str | None:
    """The facts as shown. The statement is rendered from the field it came in, never written out and read back: a
    line of the docs link's shape in its comment or literal would end a block read from text (council H1, Task 35).
    An ``UNSUPPORTED`` statement is the marker: its text is never read (owner, item 8)."""
    head, statement, params = parts
    if dialect is Dialect.UNSUPPORTED:
        block = "" if statement is None else f"\n{_BLOCK_UNSUPPORTED}{params}"
        return None if masker.mask_spans("") is None else head + block
    if masker.capture_parameters:  # capture on shows the statement as ``mask_text`` does free text
        block = "" if statement is None else f"\n[SQL: {statement}]{params}"
        return mask_error(masker, head + block, dialect, True, keep_frames)
    shown = render_error(masker, head, dialect, keep_frames)
    if not shown or statement is None:
        return shown or masker.mask_text("")
    # a MySQL driver named with another family is a conflict, as on the text path: the block hides
    named = _MYSQL_NAMED.search(head) is not None
    block = (
        _BLOCK_HIDDEN
        if named and dialect is not Dialect.MYSQL_FAMILY
        else f"{_BLOCK}{statement_text(masker, statement, dialect)}]"
    )
    return f"{shown}\n{block}{params}"


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
            parts = _classified_parts(exc, fields)
            return None if parts is None else _classified_text(masker, parts, dialect, keep_frames)
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
