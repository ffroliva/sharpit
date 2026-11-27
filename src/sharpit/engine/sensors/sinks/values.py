"""The request value holder of the security-sinks sensor: the query and path values of the requests running now.

A request's values are read from its ASGI scope at its first sink check, held only so that a command or a file path
the request reaches can be checked for one of them appearing verbatim, and dropped when the request ends. Only
parameter names, span offsets and redacted texts leave this module: never a value. Nothing here has a ``repr`` that
shows a value, logs, or waits for a lock.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import os
import re
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from urllib.parse import unquote_plus

from sharpit.engine.capture.correlation import RequestInfo

# ported: RequestValues.java:62-98,166 (limits) and AgentRequestValues.java:55-59 (query limits)
MIN_LENGTH = 4
MAX_LENGTH = 256
MAX_VALUES = 32
ENTRIES = 128
MAX_CHECKS = 256
MAX_SCAN = 16 * 1024
MAX_COMPARISONS = 4 * 1024 * 1024
HASHES = 32
MATCHED_HASHES = 8
MAX_SPANS = 8
MAX_NAME = 64
DEADLINE_SECONDS = 60
MAX_ARGUMENTS = 32
MAX_QUERY = 8 * 1024
MAX_PAIRS = 64

# ported: RequestValues.java:109-129
F_PARTIAL = 1
F_OVERFLOW = 2
F_STOPPED = 4
F_REPEATED = 8
F_BUSY = 16
F_SEEN = 32

# ported: RequestValues.java:157,163
FROM_REQUEST_INPUT = "(not kept: it held request input)"
NOT_CHECKED = "(not kept: not checked for request input)"

Kind = Literal["command", "file"]

_HASH_KEY = os.urandom(32)
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_NAME = re.compile(rf"[A-Za-z0-9_.\-\[\]]{{1,{MAX_NAME}}}")
_PATH_TYPES = (str, int, float, uuid.UUID)
_compile_uncached: Callable[[Any, int], re.Pattern[str]] | None
_sub_pattern: Any = None
_parser_state: Any = None
_literal_op: Any = None
_branch_op: Any = None
try:  # shortcut: private to ``re``, used for its cache-free compile; upgrade if a release drops it (no prefilter then)
    _compiler = importlib.import_module("re._compiler")
    _compile_uncached = cast("Callable[[Any, int], re.Pattern[str]]", _compiler.compile)
    _sub_pattern, _parser_state = _compiler._parser.SubPattern, _compiler._parser.State()
    _literal_op, _branch_op = _compiler.LITERAL, _compiler.BRANCH
except (ImportError, AttributeError):  # pragma: no cover
    _compile_uncached = None

type _Pair = tuple[str | None, str]


@dataclass(frozen=True, slots=True, repr=False)
class Match:
    names: tuple[str, ...]  # matched parameters, in the order held
    spans: tuple[tuple[int, int, int], ...]  # (index into the held values, start, end)
    flags: int
    redacted: str | None  # None when it may not cover every occurrence
    numeric: frozenset[str]  # names whose first span is a number
    text_hash: int = field(default=0)  # the text's repeat key, for mark_seen
    unreported: frozenset[str] = field(default=frozenset())  # names none of whose spans is among the reported ones


_EMPTY = Match((), (), 0, None, frozenset())
_PARTIAL = Match((), (), F_PARTIAL, None, frozenset())
_BUSY = Match((), (), F_BUSY, None, frozenset())
_STOPPED = Match((), (), F_STOPPED, None, frozenset())
_REPEATED = Match((), (), F_REPEATED, None, frozenset())
_EMPTY_MISSES: tuple[None, ...] = (None,) * HASHES


class _Entry:
    """One request's values; written under ``lock`` except ``lock`` itself and a retiring ``generation = -1``."""

    __slots__ = (
        "begun",
        "checks",
        "comparisons",
        "generation",
        "lock",
        "misses",
        "misses_order",
        "names",
        "path_pending",
        "pattern",
        "prefix",
        "seen",
        "stopped",
        "value_chars",
        "values",
    )

    def __init__(self, generation: int, begun: float, path_pending: bool) -> None:
        self.lock = threading.Lock()
        self.generation = generation
        self.begun = begun
        self.path_pending = path_pending
        self.values: list[str] = []
        self.names: list[str] = []
        self.prefix = ""
        self.pattern: re.Pattern[str] | None = None
        self.value_chars = 0
        self.misses: set[object] = set()
        self.misses_order: deque[object] = deque(_EMPTY_MISSES, maxlen=HASHES)
        self.seen: dict[int, None] = {}
        self.checks = 0
        self.comparisons = 0
        self.stopped = False

    def add(self, name: str | None, value: str) -> str | None:
        # ported: RequestValues.add (:523-551)
        vlen = len(value)
        if vlen > MAX_LENGTH:
            return "valuesTooLong"
        if vlen < MIN_LENGTH or value in self.values:
            return None
        if len(self.values) >= MAX_VALUES:
            return "valuesOverCount"
        self.values.append(value)
        self.names.append(name if name is not None and valid_name(name) else fallback_name(name))
        self.value_chars += vlen
        return None


def _remember(ring: dict[int, None], size: int, key: int) -> None:
    """Keeps the last ``size`` keys, as BootUI's rings (RequestValues.java:1030-1034)."""
    if len(ring) >= size:
        del ring[next(iter(ring))]
    ring[key] = None


def _path_pairs(path_params: object, room: int) -> list[_Pair] | None:
    """A plain dict's values of exact str, int, float or UUID type, never another type converted (D7)."""
    if type(path_params) is not dict:
        return None
    if not path_params:
        return []
    pairs: list[_Pair] = []
    for key, value in path_params.items():  # pyright: ignore[reportUnknownVariableType]
        if len(pairs) >= room:
            break
        if type(key) is str and type(value) in _PATH_TYPES:  # pyright: ignore[reportUnknownArgumentType]
            pairs.append((key, value if type(value) is str else str(value)))  # pyright: ignore[reportUnknownArgumentType]
    return pairs


def _compile_pattern(values: list[str], prefix: str) -> re.Pattern[str] | None:
    """An alternation prefilter, built outside the ``re`` module cache, which would keep the request's values alive."""
    if len(values) <= 1 or _compile_uncached is None or len(prefix) >= MIN_LENGTH:
        return None
    try:
        plen = len(prefix)
        data: list[Any] = [(_literal_op, c) for c in map(ord, prefix)]
        data.append((_branch_op, (None, [[(_literal_op, c) for c in map(ord, v[plen:])] for v in values])))
        sub = _sub_pattern(_parser_state, data)
        lengths = [len(v) for v in values]
        sub.width = (min(lengths), max(lengths))
        return _compile_uncached(sub, 0)
    except Exception:  # private API moved: no prefilter, ``_scan`` then finds each value itself
        return None


def _decode(text: str) -> str | None:
    # ported: AgentRequestValues.Values.decode (:312-318); invalid UTF-8 becomes U+FFFD, as URLDecoder does (D6)
    if "%" not in text:
        return text.replace("+", " ") if "+" in text else text
    return None if _BAD_ESCAPE.search(text) else unquote_plus(text, errors="replace")


def _decoded_query_pairs(raw: str, room: int) -> list[_Pair]:
    pairs: list[_Pair] = []
    for part in raw.split("&"):
        if len(pairs) >= room:
            break
        name, equals, value = part.partition("=")
        decoded = _decode(value) if equals else None
        if decoded is not None:
            pairs.append((_decode(name), decoded))
    return pairs


def _query_pairs(query_string: object, room: int) -> list[_Pair]:
    """The query's pairs, cut to MAX_QUERY characters, split by hand; a value that does not decode is skipped (D6)."""
    # ported: AgentRequestValues.Values.addQuery (:267-292); latin-1, as Starlette reads query_string
    if type(query_string) is not bytes or not query_string:
        return []
    raw = query_string[:MAX_QUERY].decode("latin-1")
    if "%" in raw or "+" in raw:
        return _decoded_query_pairs(raw, room)
    pairs: list[_Pair] = []
    for part in raw.split("&"):
        if len(pairs) >= room:
            break
        name, equals, value = part.partition("=")
        if equals:
            pairs.append((name, value))
    return pairs


def _scope_value(scope: object, key: str) -> object:
    """A key of an ASGI scope that is a plain dict; never a host mapping's own lookup."""
    return cast("dict[str, object]", scope).get(key) if type(scope) is dict else None


def _read_values(scope: object) -> tuple[list[_Pair], bool]:
    """Path values before query values (D4), and whether the path values are still to come."""
    path = _path_pairs(_scope_value(scope, "path_params"), MAX_PAIRS)
    if not path:
        return _query_pairs(_scope_value(scope, "query_string"), MAX_PAIRS), path is None
    return path + _query_pairs(_scope_value(scope, "query_string"), MAX_PAIRS - len(path)), False


_NO_SPANS: list[tuple[int, int, int]] = []
_NO_MATCHED: list[int] = []
_NO_SCAN = (_NO_SPANS, _NO_MATCHED, False)


def _scan(
    scanned: str, values: list[str], pattern: re.Pattern[str] | None = None
) -> tuple[list[tuple[int, int, int]], list[int], bool]:
    """Every value's non-overlapping occurrences, in value order, at most MAX_SPANS; and whether more matched."""
    # ported: RequestValues.compare (:998-1017)
    if pattern is not None and pattern.search(scanned) is None:
        return _NO_SCAN
    spans: list[tuple[int, int, int]] = []
    matched: list[int] = []
    overflow = False
    for index, value in enumerate(values):
        at = scanned.find(value)
        if at >= 0:
            matched.append(index)
        while at >= 0:
            if len(spans) >= MAX_SPANS:
                overflow = True
                break
            spans.append((index, at, at + len(value)))
            at = scanned.find(value, at + len(value))
    return spans, matched, overflow


def _redact(text: str, spans: list[tuple[int, int, int]], names: list[str], flags: int) -> str | None:
    """``text`` with every span replaced by ``{name}``, overlapping spans merged under the first one's name."""
    # ported: RequestValues.redactChecked (:1211-1263)
    if flags & ~F_SEEN or not spans:
        return None
    out: list[str] = []
    position = 0
    for index, start, end in sorted(spans, key=lambda span: (span[1], -span[2])):
        if end <= position:
            continue
        if start >= position:
            out.extend((text[position:start], "{", names[index], "}"))
        position = end
    out.append(text[position:])
    return "".join(out)


def _numeric(text: str, spans: list[tuple[int, int, int]], names: list[str], matched: list[int]) -> frozenset[str]:
    # ported: RequestValues.numericFlag (:815-830)
    first = {index: (start, end) for index, start, end in reversed(spans)}
    return frozenset(names[i] for i in matched if i in first and number(text, *first[i]))


def _unreported(spans: list[tuple[int, int, int]], names: list[str], matched: list[int]) -> frozenset[str]:
    # ported: RequestValues.reported (:801-809)
    reported = {index for index, _, _ in spans}
    return frozenset(names[i] for i in matched if i not in reported)


class RequestValues:
    """The values of the requests running now, keyed by request id, bounded in entries, values and work."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._swept: dict[str, None] = {}
        self._table = threading.Lock()
        self._generation = 0
        # shortcut: an increment racing another may be lost; the line is advisory (BootUI uses LongAdder);
        # move to per-entry counters if an exact count is ever asserted under concurrency.
        self._requests = 0
        self._table_full = 0
        self._values_too_long = 0
        self._values_over_count = 0
        self._checks = 0
        self._partial = 0
        self._stopped = 0
        self._busy = 0

    def _live_values(self, info: RequestInfo, entry: _Entry) -> bool:
        """Whether the entry is live and holds values; path values are pulled only for a live entry (BootUI order)."""
        if entry.generation != self._generation or info.finished_ns is not None:
            return False
        if entry.path_pending:
            self._pull_path(entry, info.scope)
        return bool(entry.values)

    def match(self, info: RequestInfo, text: str, kind: Kind) -> Match:
        """Which of ``info``'s values appear verbatim in ``text``, within the request's budgets. Never waits."""
        # ported: RequestValues.compare (:912-1060), same order of checks
        if (entry := self._entries.get(info.id)) is None and not isinstance(entry := self._insert(info), _Entry):
            return entry
        text_len = len(text)
        if text_len > MAX_SCAN:
            return self._match_partial(info, entry, text, kind)
        if not entry.lock.acquire(False):
            self._busy += 1
            return _BUSY
        try:
            if not self._live_values(info, entry):
                return _EMPTY
            if entry.stopped:
                return _STOPPED
            key = hash(text) if kind == "file" else ~hash(text)
            misses = entry.misses
            if key in misses:
                return _REPEATED
            seen = key in entry.seen
            entry.checks += not seen
            entry.comparisons += text_len * entry.value_chars
            if entry.checks > MAX_CHECKS or entry.comparisons > MAX_COMPARISONS:
                entry.stopped = True
                self._stopped += 1
                return _STOPPED
            self._checks += 1
            if entry.prefix not in text or not (matched := (scan := _scan(text, entry.values, entry.pattern))[1]):
                order = entry.misses_order
                misses.discard(order[0])
                order.append(key)
                misses.add(key)
                return _EMPTY
            spans, overflow = scan[0], scan[2]
            names = list(entry.names)
        finally:
            entry.lock.release()
        return self._matched(info, entry, text, spans, matched, names, key, False, overflow, seen)

    def _match_partial(self, info: RequestInfo, entry: _Entry, text: str, kind: Kind) -> Match:
        scanned = text[:MAX_SCAN]
        if not entry.lock.acquire(False):
            self._busy += 1
            return _BUSY
        try:
            if not self._live_values(info, entry):
                return _EMPTY
            if entry.stopped:
                return _STOPPED
            key = hash((kind, len(text), scanned))
            seen = key in entry.seen
            entry.checks += not seen
            entry.comparisons += MAX_SCAN * entry.value_chars
            if entry.checks > MAX_CHECKS or entry.comparisons > MAX_COMPARISONS:
                entry.stopped = True
                self._stopped += 1
                return _STOPPED
            self._checks += 1
            self._partial += 1
            if entry.prefix not in scanned or not (matched := (scan := _scan(scanned, entry.values, entry.pattern))[1]):
                return _PARTIAL if self._live(info, entry) else _EMPTY
            spans, overflow = scan[0], scan[2]
            names = list(entry.names)
        finally:
            entry.lock.release()
        return self._matched(info, entry, text, spans, matched, names, key, True, overflow, seen)

    def _insert(self, info: RequestInfo) -> _Entry | Match:
        generation = self._generation
        if info.finished_ns is not None or info.id in self._swept:
            return _EMPTY
        pairs, path_pending = _read_values(info.scope)
        if not pairs:
            return _EMPTY
        if not self._table.acquire(False):
            self._busy += 1
            return _BUSY
        try:
            if generation != self._generation:
                return _EMPTY
            self._sweep()
            entry = self._entries.get(info.id)
            if entry is None:
                if info.id in self._swept:
                    return _EMPTY
                if len(self._entries) >= ENTRIES:
                    self._table_full += 1
                    return _EMPTY
                entry = _Entry(generation, self._clock(), path_pending)
                self._add_pairs(entry, pairs)
                self._entries[info.id] = entry
                self._requests += 1
        finally:
            self._table.release()
        if info.finished_ns is not None or generation != self._generation:
            self._drop(info.id, entry)
            return _EMPTY
        return entry

    def _add_pairs(self, entry: _Entry, pairs: list[_Pair]) -> None:
        for name, value in pairs:
            self._count_add(entry, name, value)
        prefix = entry.values[0] if len(entry.values) == 1 else os.path.commonprefix(entry.values)
        entry.prefix = prefix
        entry.pattern = _compile_pattern(entry.values, prefix)

    def _sweep(self) -> None:
        """Pops the entries past the deadline; their requests hold no values again (RequestValues.java:438)."""
        if not self._entries:
            return
        now = self._clock()
        for request_id, current in list(self._entries.items()):
            if now - current.begun <= DEADLINE_SECONDS:
                continue
            if (entry := self._entries.pop(request_id, None)) is not None:
                entry.generation = -1
            if len(self._swept) >= ENTRIES:
                # end and clear change the dict without the table lock: an eviction they race is skipped
                with contextlib.suppress(RuntimeError, StopIteration):
                    self._swept.pop(next(iter(self._swept)), None)
            self._swept[request_id] = None

    def _drop(self, request_id: str, entry: _Entry) -> None:
        if self._entries.get(request_id) is entry:
            self._entries.pop(request_id, None)
            entry.generation = -1

    def _live(self, info: RequestInfo, entry: _Entry) -> bool:
        return entry.generation == self._generation and info.finished_ns is None

    def _matched(
        self,
        info: RequestInfo,
        entry: _Entry,
        text: str,
        spans: list[tuple[int, int, int]],
        matched: list[int],
        names: list[str],
        key: int,
        partial: bool,
        overflow: bool,
        seen: bool,
    ) -> Match:
        flags = (F_PARTIAL if partial else 0) | (F_OVERFLOW if overflow else 0) | (F_SEEN if seen else 0)
        redacted = _redact(text, spans, names, flags)
        result = Match(
            tuple(names[i] for i in matched),
            tuple(spans),
            flags,
            redacted,
            _numeric(text, spans, names, matched),
            key,
            _unreported(spans, names, matched),
        )
        return result if self._live(info, entry) else _EMPTY

    def _pull_path(self, entry: _Entry, scope: object) -> None:
        """Path values routing set after the first check: added once, and remembered texts checked again."""
        # ported: RequestValues.compare (:948-957)
        path = _path_pairs(_scope_value(scope, "path_params"), MAX_VALUES)
        if path is None:
            return
        self._add_pairs(entry, path)
        entry.misses.clear()
        entry.misses_order.extend(_EMPTY_MISSES)
        entry.seen.clear()
        entry.path_pending = False

    def mark_seen(self, request_id: str, match: Match) -> None:
        """Remembers an owned match's text, so the request's next check of it reports ``F_SEEN`` (D2)."""
        entry = self._entries.get(request_id)
        if entry is None or not match.names or match.flags & F_SEEN or entry.generation != self._generation:
            return
        if not entry.lock.acquire(False):
            return
        try:
            if entry.generation == self._generation:
                _remember(entry.seen, MATCHED_HASHES, match.text_hash)
        finally:
            entry.lock.release()

    def end(self, request_id: str) -> None:
        """The request ended: the expired entries are swept, then its values are dropped (RequestValues.java:419)."""
        if self._table.acquire(False):  # a sweep never waits, as BootUI's
            try:
                self._sweep()
            finally:
                self._table.release()
        if (entry := self._entries.pop(request_id, None)) is not None:
            entry.generation = -1
        self._swept.pop(request_id, None)

    def clear(self) -> None:
        """Every value is dropped, and a check under way publishes and inserts nothing. Takes no lock (D5)."""
        self._generation += 1
        self._entries.clear()
        self._swept.clear()

    def held(self) -> int:
        """The number of requests whose values are held: a status and test helper, never read on a request path."""
        return len(self._entries)

    def status(self) -> dict[str, int]:
        return {
            "requests": self._requests,
            "tableFull": self._table_full,
            "valuesTooLong": self._values_too_long,
            "valuesOverCount": self._values_over_count,
            "checks": self._checks,
            "partial": self._partial,
            "stopped": self._stopped,
            "busy": self._busy,
            "notKept": 0,
            "dropped": 0,
        }

    def _count_add(self, entry: _Entry, name: str | None, value: str) -> None:
        if (result := entry.add(name, value)) is not None:
            if result == "valuesTooLong":
                self._values_too_long += 1
            else:
                self._values_over_count += 1


def unchecked(match: Match) -> bool:
    """Whether a check that matched nothing compared nothing, or not the whole text (RequestValues.java:730)."""
    return bool(match.flags & (F_STOPPED | F_BUSY | F_PARTIAL))


def keyed_hash(text: str) -> int:
    """A per-process keyed hash of a text's first MAX_SCAN characters, in 1..2**63-1 (D5)."""
    digest = hashlib.blake2b(text[:MAX_SCAN].encode("utf-8", "surrogatepass"), key=_HASH_KEY, digest_size=8).digest()
    return (int.from_bytes(digest) & (2**63 - 1)) or 1


def valid_name(name: str) -> bool:
    """1 to MAX_NAME characters of ``[A-Za-z0-9_.\\-\\[\\]]`` (RequestValues.validName, :565)."""
    if 0 < len(name) <= MAX_NAME and name.isascii() and name.isalnum():
        return True
    return _NAME.fullmatch(name) is not None


def fallback_name(name: str | None) -> str:
    """``param#`` and 4 hex digits of Java's ``String.hashCode`` of the name, ``param#0000`` for none (:558-562)."""
    code = 0
    if name:
        data = name.encode("utf-16-be", "surrogatepass")
        for i in range(0, len(data), 2):
            code = (31 * code + (data[i] << 8 | data[i + 1])) & 0xFFFFFFFF
    return f"param#{code & 0xFFFF:04x}"


def number(text: str, start: int, end: int) -> bool:
    """Digits, with an optional leading sign and at most one decimal point (RequestValues.number, :1063-1081)."""
    body = text[start:end]
    body = body[1:] if body[:1] in ("-", "+") else body
    integer, _, fraction = body.partition(".")
    digits = integer + fraction
    return digits.isascii() and digits.isdigit() and "." not in fraction
