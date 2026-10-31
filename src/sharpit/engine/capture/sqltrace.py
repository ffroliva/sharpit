"""SQL Trace (F3, spec §7.3): the statement normaliser, the bounded recorder and its report. Framework-free.

Ports of BootUI ``SqlStatementNormalizer`` (verbatim), ``SqlTracingProxies.categoryOf`` and ``SqlTraceRecorder``.
Two changes from BootUI: top statements are cumulative since the last clear (capped at 500 keys, least recently
seen dropped first) instead of grouped over the ring, and SQL is stored normalised unless parameter capture is on,
so inline literals never reach the buffer.
"""

from __future__ import annotations

import functools
import itertools
import re
import sys
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import FrameType
from typing import Any, NamedTuple, cast

from sharpit.engine.capture.exchanges import _iso  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.capture.frames import is_application_frame
from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import MASK, Masker

REPORT_KEYS = (
    "available", "unavailableReason", "capturing", "captureParameters", "bufferSize", "totalCaptured",
    "slowQueryThresholdMillis", "dataSources", "stats", "entries", "topStatements", "warnings",
)  # fmt: skip
STATS_KEYS = (
    "totalQueries", "totalDurationMillis", "maxDurationMillis", "avgDurationMillis", "slowQueries", "failedQueries",
    "batchExecutions", "selectCount", "insertCount", "updateCount", "deleteCount", "otherCount", "evicted",
)  # fmt: skip
ENTRY_KEYS = (
    "id", "timestamp", "sql", "statementType", "category", "durationMillis", "success", "errorMessage",
    "affectedRows", "batchSize", "connectionId", "thread", "slow", "parameters", "traceId", "callSite",
)  # fmt: skip
GROUP_KEYS = (
    "sql", "category", "executions", "totalDurationMillis", "maxDurationMillis", "potentialNPlusOne", "callSites",
)  # fmt: skip

MAX_AGGREGATES = 500
TOP_STATEMENTS_LIMIT = 20
MAX_CALL_SITES_PER_GROUP = 5
MAX_PARAMETER_SETS = 5
MAX_PARAMETERS_PER_SET = 5
MAX_CALL_SITE_FRAMES = 64
PAUSED = "Recording is paused. Resume it to capture new queries."
PARAMETERS_SHOWN = (
    "Bound parameter values are captured in clear text. Set SHARPIT_SQL_TRACE_CAPTURE_PARAMETERS=false to hide them."
)


# --- SqlStatementNormalizer (verbatim port) -------------------------------------------------------------------------

_MAX_SCAN_LENGTH = 20_000


class Normalized(NamedTuple):
    sql: str
    fingerprint: str
    literal_count: int
    predicate_literal_count: int


class _Out:
    """The output builder; ``opens`` holds the unmatched ``(`` positions so the IN-list check is O(1), not a
    backward scan per literal (BootUI's scan is quadratic on a long list, too slow in Python)."""

    def __init__(self) -> None:
        self.chars: list[str] = []
        self.opens: list[int] = []

    def append(self, text: str) -> None:
        for c in text:
            if c == "(":
                self.opens.append(len(self.chars))
            elif c == ")" and self.opens:
                self.opens.pop()
            self.chars.append(c)

    def space(self) -> None:
        if self.chars and self.chars[-1] != " ":
            self.chars.append(" ")

    def last_non_space(self) -> int:
        cursor = len(self.chars) - 1
        while cursor >= 0 and self.chars[cursor] == " ":
            cursor -= 1
        return cursor

    def ends_with_in_list(self) -> bool:
        """The innermost unmatched ``(`` is preceded by the keyword ``in`` (only called at the end of the output)."""
        if not self.opens:
            return False
        before = self.opens[-1] - 1
        while before >= 0 and self.chars[before] == " ":
            before -= 1
        return self.ends_with_keyword(before, "in")

    def ends_with_keyword(self, end_inclusive: int, keyword: str) -> bool:
        start = end_inclusive - len(keyword) + 1
        if start < 0:
            return False
        if "".join(self.chars[start : end_inclusive + 1]).lower() != keyword:
            return False
        return start == 0 or not self.chars[start - 1].isalnum()

    def predicate_position(self) -> bool:
        cursor = self.last_non_space()
        if cursor < 0:
            return False
        last = self.chars[cursor]
        if last in "=<>!":
            return True
        if last in ",(":
            return self.ends_with_in_list()
        return self.ends_with_keyword(cursor, "like") or self.ends_with_keyword(cursor, "ilike")

    def text(self) -> str:
        return "".join(self.chars)


def _skip_quoted(sql: str, index: int, closing: str) -> int:
    cursor, length = index + 1, len(sql)
    while cursor < length:
        c = sql[cursor]
        if c == "\\" and closing == "'" and cursor + 1 < length:
            cursor += 2
            continue
        if c == closing:
            if cursor + 1 < length and sql[cursor + 1] == closing:
                cursor += 2
                continue
            return cursor + 1
        cursor += 1
    return length


def _dollar_quote_end(sql: str, index: int) -> int:
    cursor, length, body_start = index + 1, len(sql), -1
    while cursor < length:
        c = sql[cursor]
        if c == "$":
            body_start = cursor + 1
            break
        if not (c.isalpha() or c == "_" or (cursor > index + 1 and c.isdigit())):
            return -1
        cursor += 1
    if body_start < 0:
        return -1
    tag = sql[index:body_start]
    end = sql.find(tag, body_start)
    return -1 if end < 0 else end + len(tag)


def _identifier_like(sql: str, index: int, end: int) -> bool:
    start = index + 1
    stop = end - 1 if end > start and sql[end - 1] == '"' else end
    if stop <= start:
        return False
    return all((c.isascii() and c.isalnum()) or c in "_$." for c in sql[start:stop])


def _matches_keyword(sql: str, index: int, keyword: str) -> bool:
    after = index + len(keyword)
    if after > len(sql) or sql[index:after].lower() != keyword:
        return False
    return after >= len(sql) or not (sql[after].isalnum() or sql[after] in "_$")


def _identifier_char_before(out: _Out) -> bool:
    return bool(out.chars) and (out.chars[-1].isalnum() or out.chars[-1] in "_$.")


def _keyword_literal_start(sql: str, index: int, out: _Out) -> bool:
    if sql[index] not in "tTfF" or _identifier_char_before(out):
        return False
    return _matches_keyword(sql, index, "true") or _matches_keyword(sql, index, "false")


def _skip_number(sql: str, index: int) -> int:
    cursor, length = index, len(sql)
    while cursor < length and (sql[cursor].isdigit() or sql[cursor] == "."):
        cursor += 1
    if cursor < length and sql[cursor] in "eE":
        exponent = cursor + 1
        if exponent < length and sql[exponent] in "+-":
            exponent += 1
        if exponent < length and sql[exponent].isdigit():
            cursor = exponent
            while cursor < length and sql[cursor].isdigit():
                cursor += 1
    return cursor


def _collapse_placeholder_lists(normalized: str) -> str:
    if "?" not in normalized:
        return normalized
    out = _Out()
    index, length = 0, len(normalized)
    while index < length:
        c = normalized[index]
        cursor = out.last_non_space()
        inside = cursor >= 0 and out.chars[cursor] in "(," and out.ends_with_in_list()
        if c != "?" or not inside:
            out.append(c)
            index += 1
            continue
        cursor = last_placeholder = index
        while True:
            following = cursor + 1
            while following < length and normalized[following] == " ":
                following += 1
            if following < length and normalized[following] == ",":
                following += 1
                while following < length and normalized[following] == " ":
                    following += 1
                if following < length and normalized[following] == "?":
                    cursor = last_placeholder = following
                    continue
            break
        out.append("?")
        index = last_placeholder + 1
    return out.text()


@functools.lru_cache(maxsize=1024)  # the same statements repeat: the scan runs once per distinct text
def normalize(sql: str) -> Normalized:
    """Literals become ``?``, comments and whitespace runs one space, ``IN (?, ?)`` lists ``IN (?)``."""
    if not sql or sql.isspace():
        return Normalized("", "", 0, 0)
    source = sql[:_MAX_SCAN_LENGTH]
    out = _Out()
    literals = predicate_literals = 0
    index, length = 0, len(source)
    while index < length:
        c = source[index]
        dollar_end = _dollar_quote_end(source, index) if c == "$" else -1
        literal = False
        if c == "-" and source.startswith("-", index + 1):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline
            out.space()
        elif c == "/" and source.startswith("*", index + 1):
            end = source.find("*/", index + 2)
            index = length if end < 0 else end + 2
            out.space()
        elif c == "'":
            index, literal = _skip_quoted(source, index, "'"), True
        elif dollar_end > 0:
            index, literal = dollar_end, True
        elif c in '"`[':
            end = _skip_quoted(source, index, "]" if c == "[" else c)
            if c == '"' and not _identifier_like(source, index, end):
                literal = True
            else:
                out.append(source[index:end])
            index = end
        elif _keyword_literal_start(source, index, out):
            index, literal = index + (4 if _matches_keyword(source, index, "true") else 5), True
        elif c.isspace():
            out.space()
            index += 1
        elif c.isdigit() and not _identifier_char_before(out):
            index, literal = _skip_number(source, index), True
        else:
            out.append(c)
            index += 1
        if literal:
            literals += 1
            predicate_literals += out.predicate_position()
            out.append("?")
    collapsed = _collapse_placeholder_lists(out.text().strip())
    return Normalized(collapsed, collapsed.lower(), literals, predicate_literals)


def normalize_sql(sql: str) -> str:
    return normalize(sql).sql


# --- SqlTracingProxies.categoryOf -----------------------------------------------------------------------------------

_CATEGORIES = {
    **dict.fromkeys(("SELECT", "WITH", "SHOW", "VALUES", "TABLE"), "SELECT"),
    "INSERT": "INSERT",
    **dict.fromkeys(("UPDATE", "MERGE", "UPSERT"), "UPDATE"),
    "DELETE": "DELETE",
    **dict.fromkeys(("CREATE", "ALTER", "DROP", "TRUNCATE", "COMMENT", "RENAME", "GRANT", "REVOKE"), "DDL"),
}


@functools.lru_cache(maxsize=1024)
def category_of(sql: str) -> str:
    i, length = 0, len(sql)
    while i < length:  # skip leading whitespace, comments and opening parens
        c = sql[i]
        if c.isspace() or c == "(":
            i += 1
        elif sql.startswith("--", i):
            newline = sql.find("\n", i)
            i = length if newline < 0 else newline + 1
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = length if end < 0 else end + 2
        else:
            break
    start = i
    while i < length and sql[i].isalpha():
        i += 1
    return _CATEGORIES.get(sql[start:i].upper(), "OTHER")


# --- call site ------------------------------------------------------------------------------------------------------


def call_site(frame: FrameType | None) -> str | None:
    """The first application frame as ``module:function:line``, walking at most 64 frames; an ``AsyncSession``
    statement runs in a greenlet holding only SQLAlchemy frames, so the walk continues into its parent."""
    current = frame if frame is not None else sys._getframe()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    greenlet_module = sys.modules.get("greenlet")
    parent: Any = None
    if greenlet_module is not None:
        parent = getattr(greenlet_module.getcurrent(), "parent", None)
    for _ in range(MAX_CALL_SITE_FRAMES):
        if current is None:
            if parent is None:
                return None
            current, parent = parent.gr_frame, getattr(parent, "parent", None)
            if current is None:
                return None
        code = current.f_code
        if is_application_frame(code.co_filename):
            return f"{current.f_globals.get('__name__', '?')}:{code.co_name}:{current.f_lineno}"
        current = current.f_back
    return None


# --- SqlTraceRecorder -----------------------------------------------------------------------------------------------


def _empty_stats() -> dict[str, Any]:
    return dict.fromkeys(STATS_KEYS, 0)


def unavailable_report(reason: str) -> dict[str, Any]:
    """``SqlTraceReport.unavailable``."""
    return {
        "available": False,
        "unavailableReason": reason,
        "capturing": False,
        "captureParameters": False,
        "bufferSize": 0,
        "totalCaptured": 0,
        "slowQueryThresholdMillis": 0,
        "dataSources": [],
        "stats": _empty_stats(),
        "entries": [],
        "topStatements": [],
        "warnings": [],
    }


def entry_dto(row: dict[str, Any]) -> dict[str, Any]:
    """``SqlTraceEntryDto`` from a stored row."""
    return {**row, "timestamp": _iso(row["timestamp"])}


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "…"


@dataclass(eq=False)
class _Aggregate:
    sql: str
    category: str
    executions: int = 0
    total_duration: int = 0
    max_duration: int = 0
    call_sites: dict[str, None] = field(default_factory=dict[str, None])


class SqlTraceRecorder:
    """The bounded ring of statements, newest last, with cumulative per-statement aggregates."""

    def __init__(
        self,
        masker: Masker,
        *,
        max_entries: int = 200,
        slow_query_threshold_millis: int = 100,
        max_sql_length: int = 2000,
        max_parameter_length: int = 200,
        n_plus_one_threshold: int = 5,
        capture_call_site: bool = True,
        recording: bool = True,
    ) -> None:
        self._masker = masker
        self.max_entries = max_entries
        self.slow_query_threshold_millis = slow_query_threshold_millis
        self._max_sql_length = max_sql_length
        self._max_parameter_length = max_parameter_length
        self._n_plus_one_threshold = n_plus_one_threshold
        self.capture_call_site = capture_call_site
        self.recording = recording
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._aggregates: OrderedDict[str, _Aggregate] = OrderedDict()
        self._ids = itertools.count(1)
        self._total = 0
        self._evicted = 0
        self._lock = threading.Lock()
        self.changes = ChangeStream()

    @property
    def aggregate_count(self) -> int:
        return len(self._aggregates)

    def _slow(self, millis: int) -> bool:
        return self.slow_query_threshold_millis > 0 and millis >= self.slow_query_threshold_millis

    def _parameters(self, parameters: object, executemany: bool) -> list[str]:
        sets: Sequence[object] = cast_sets(parameters, executemany)
        rendered: list[str] = []
        for values in sets[:MAX_PARAMETER_SETS]:
            if isinstance(values, Mapping):
                pairs = list(cast_mapping(cast(object, values)).items())[:MAX_PARAMETERS_PER_SET]
                rendered += [f"{k}={self._parameter(str(k), v)}" for k, v in pairs]
            elif isinstance(values, Sequence) and not isinstance(values, str | bytes):
                rendered += [
                    self._parameter("", v) for v in list(cast_sequence(cast(object, values)))[:MAX_PARAMETERS_PER_SET]
                ]
            else:
                rendered.append(self._parameter("", values))
        return rendered

    def _parameter(self, name: str, value: object) -> str:
        shown, masked = self._masker.mask(name, value)
        return _truncate(MASK if masked else repr(shown), self._max_parameter_length)

    def record(
        self,
        sql: str,
        *,
        duration_ns: int,
        thread: str,
        connection_id: str | None,
        parameters: object = None,
        executemany: bool = False,
        success: bool = True,
        error: BaseException | None = None,
        rowcount: int = -1,
        request_id: str | None = None,
        call_site: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        """Build the masked row once, at capture time; a paused recorder returns before any work."""
        if not self.recording:
            return
        masker = self._masker
        normalized = normalize(sql)
        stored = normalized.sql if not masker.capture_parameters else (masker.mask_text(sql) or "")
        error_message: str | None = None
        if error is not None:
            text = str(error)
            if not masker.capture_parameters:
                text = _driver_values_dropped(text)
                if sql:
                    text = text.replace(sql.strip(), normalized.sql)  # SQLAlchemy repeats the statement in [SQL: ...]
            masked = masker.mask_text(text)
            error_message = _truncate(masked, self._max_sql_length) if masked is not None else None
        has_parameters = bool(parameters)
        millis = duration_ns // 1_000_000
        category = category_of(sql)
        site = call_site if self.capture_call_site else None
        row = {
            "id": 0,
            "timestamp": time.time_ns(),  # formatted by report(): strftime costs more than the rest of the row
            "sql": _truncate(stored, self._max_sql_length),
            "statementType": "PREPARED" if has_parameters else "STATEMENT",
            "category": category,
            "durationMillis": millis,
            "success": success and error is None,
            "errorMessage": error_message,
            "affectedRows": rowcount if rowcount >= 0 and error is None else None,
            "batchSize": (batch_size if batch_size is not None else len(cast_sequence(parameters)))
            if executemany and has_parameters
            else 0,
            "connectionId": connection_id,
            "thread": thread,
            "slow": self._slow(millis),
            "parameters": self._parameters(parameters, executemany)
            if masker.capture_parameters and has_parameters
            else [],
            "traceId": request_id,
            "callSite": site,
        }
        with self._lock:
            row["id"] = next(self._ids)
            if len(self._entries) == self.max_entries:
                self._evicted += 1
            self._entries.append(row)
            self._total += 1
            key = normalized.fingerprint
            aggregate = self._aggregates.get(key)
            if aggregate is None:
                aggregate = self._aggregates[key] = _Aggregate(normalized.sql, category)
                if len(self._aggregates) > MAX_AGGREGATES:
                    self._aggregates.popitem(last=False)
            else:
                self._aggregates.move_to_end(key)
            aggregate.executions += 1
            aggregate.total_duration += millis
            aggregate.max_duration = max(aggregate.max_duration, millis)
            if site is not None and len(aggregate.call_sites) < MAX_CALL_SITES_PER_GROUP:
                aggregate.call_sites[site] = None
        self.changes.signal()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._aggregates.clear()
        self.changes.signal()

    def set_recording(self, enabled: bool) -> None:
        if self.recording != enabled:
            self.recording = enabled
            self.changes.signal()

    def rows(self) -> list[dict[str, Any]]:
        """The ring as stored, oldest first (``timestamp`` in epoch ns); ``entry_dto`` formats one row."""
        with self._lock:
            return list(self._entries)

    def report(self, data_sources: list[str]) -> dict[str, Any]:
        """``SqlTraceReport``: entries newest first, stats over the ring, top statements since the last clear."""
        with self._lock:
            rows = list(self._entries)
            groups = [
                (a.sql, a.category, a.executions, a.total_duration, a.max_duration, list(a.call_sites))
                for a in self._aggregates.values()
            ]
            total, evicted = self._total, self._evicted
        stats = _empty_stats()
        for row in rows:
            millis = row["durationMillis"]
            stats["totalQueries"] += 1
            stats["totalDurationMillis"] += millis
            stats["maxDurationMillis"] = max(stats["maxDurationMillis"], millis)
            stats["slowQueries"] += self._slow(millis)
            stats["failedQueries"] += not row["success"]
            stats["batchExecutions"] += row["batchSize"] > 0
            counter = f"{row['category'].lower()}Count"
            stats[counter if counter in stats else "otherCount"] += 1
        stats["avgDurationMillis"] = stats["totalDurationMillis"] / len(rows) if rows else 0
        stats["evicted"] = evicted
        groups.sort(key=lambda g: (-g[2], g[0]))
        top = [
            dict(
                zip(
                    GROUP_KEYS,
                    (
                        sql,
                        category,
                        n,
                        total_ms,
                        max_ms,
                        category == "SELECT" and n >= self._n_plus_one_threshold,
                        sites,
                    ),
                    strict=True,
                )
            )
            for sql, category, n, total_ms, max_ms, sites in groups[:TOP_STATEMENTS_LIMIT]
        ]
        warnings: list[str] = []
        if not self.recording:
            warnings.append(PAUSED)
        if self._masker.capture_parameters:
            warnings.append(PARAMETERS_SHOWN)
        if evicted > 0:
            warnings.append(f"Older queries were dropped; the buffer keeps the most recent {self.max_entries}.")
        return {
            "available": True,
            "unavailableReason": None,
            "capturing": self.recording,
            "captureParameters": self._masker.capture_parameters,
            "bufferSize": self.max_entries,
            "totalCaptured": total,
            "slowQueryThresholdMillis": self.slow_query_threshold_millis,
            "dataSources": data_sources,
            "stats": stats,
            "entries": [entry_dto(row) for row in reversed(rows)],
            "topStatements": top,
            "warnings": warnings,
        }


_QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")


def _driver_values_dropped(text: str) -> str:
    """The driver's message without the row values it echoes: PostgreSQL's ``DETAIL:`` lines and quoted values.

    Only the message's first line is kept, with quoted runs as ``?``. SQLAlchemy's ``[SQL: ...]`` and
    ``[parameters: ...]`` lines that follow are kept for the caller to normalise and mask.
    """
    head, sep, tail = text.partition("\n[SQL: ")
    return _QUOTED.sub("?", head.split("\n", 1)[0]) + sep + tail


def cast_sets(parameters: object, executemany: bool) -> Sequence[object]:
    """The parameter sets of one execution: several for ``executemany``, else the single set."""
    if executemany and isinstance(parameters, Sequence) and not isinstance(parameters, str | bytes):
        return cast_sequence(cast(object, parameters))
    return [parameters]


def cast_sequence(values: object) -> Sequence[object]:
    return values if isinstance(values, Sequence) else ()  # pyright: ignore[reportUnknownVariableType]


def cast_mapping(values: object) -> Mapping[object, object]:
    return values if isinstance(values, Mapping) else {}  # pyright: ignore[reportUnknownVariableType]
