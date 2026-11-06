"""Error text by region (spec §3): each region has one owner, every job reads raw text, and the output is emitted once.

Text is a driver line, frames, a ``[SQL: `` block, its parameters, a trailer and the docs link. Nothing rendered here is
read again, so what one region hides cannot change what another decides.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Iterator

from sharpit.engine.capture.sqlscan import block_closer, reads_two_ways
from sharpit.engine.capture.statement import statement_text
from sharpit.engine.masking import MASK, Masker, Tracked
from sharpit.engine.sqltext import Dialect

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
_MYSQL_DRIVER = re.compile(r"\b(?:pymysql|MySQLdb|asyncmy|mariadb|mysql\.connector)\.")
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
        low, high = first.end(), high - 2
        first = _QUOTE.search(line, low, high)
        if first is None:
            return None
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
        self.driver: Dialect | None = None  # what the driver line names, until Task 28

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
        named = _MYSQL_DRIVER.search(text, 0, quote.start() if quote else len(text))
        self.driver = self.driver or (Dialect.MYSQL_FAMILY if named else None)
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
    closer = block_closer(statement, dialect)
    if closer < 0 or reads_two_ways(statement[:closer], dialect):  # no closer to trust: it runs on, to its parameters
        parameters = statement.rfind(_PARAMETERS_LINE)
        read = statement if parameters < 0 else statement[:parameters]
        shown.append(f"{_BLOCK}{statement_text(masker, read, dialect)}")
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
    read_as = dialect if head.driver is None else head.driver
    resume = _block(masker, text, block.end(), end, read_as, shown) if block else end
    shown += _Lines(masker, text[resume:end], _TRAILER, keep_frames).walk()
    if link:
        shown.append(link[0])
        shown += _Lines(masker, text[link.end() :], _TRAILER, keep_frames).walk()
    return "\n".join(shown)


def render_error(masker: Masker, text: str, dialect: Dialect, keep_frames: bool = True) -> str:
    """``text`` by region; ``""`` under ``METADATA_ONLY``, ``******`` if the render fails.

    A MySQL driver named on the driver line counts as ``Dialect.MYSQL_FAMILY``, whatever ``dialect`` says: a literal
    cannot switch it.
    """
    try:
        if masker.mask_spans("") is None:
            return ""
        return _render(masker, text, dialect, keep_frames)
    except Exception:
        return MASK


def mask_error(masker: Masker, text: str | None, dialect: Dialect, known: bool = False) -> str | None:
    """An error text for display: every path from an exception to output comes here.

    ``known`` is for text certain to come from a database. Free text pays one search and is ``mask_text``'s.
    """
    if text is None:
        return None
    if masker.capture_parameters or not (known or _AN_ERROR.search(text)):
        return masker.mask_text(text)
    return render_error(masker, text, dialect) or masker.mask_text("")


def log_statement(masker: Masker, text: str, dialect: Dialect) -> str | None:
    """A record from ``sqlalchemy.engine``: a statement, read with the application's family.

    SQLAlchemy's cut can take a quote and flip every quote after it, so nothing past it is read.
    """
    cut = _TRUNCATED.search(text)
    return statement_text(masker, text[: cut.start()] if cut else text, dialect)
