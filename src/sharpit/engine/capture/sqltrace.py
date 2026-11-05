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

from sharpit.engine.capture.frames import is_application_frame
from sharpit.engine.capture.sqlscan import MYSQL_DIALECTS, Normalized, is_mysql, normalize, normalize_sql
from sharpit.engine.capture.statement import masked_shape
from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import MASK, Masker

__all__ = ["MYSQL_DIALECTS", "Normalized", "is_mysql", "normalize", "normalize_sql"]

REPORT_KEYS = (
    "available", "unavailableReason", "capturing", "captureParameters", "bufferSize", "totalCaptured",
    "slowQueryThresholdMillis", "dataSources", "stats", "entries", "topStatements", "warnings", "retention",
)  # fmt: skip
STATS_KEYS = (
    "totalQueries", "totalDurationMillis", "maxDurationMillis", "avgDurationMillis", "slowQueries", "failedQueries",
    "batchExecutions", "selectCount", "insertCount", "updateCount", "deleteCount", "otherCount", "evicted",
)  # fmt: skip
ENTRY_KEYS = (
    "id", "timestamp", "sql", "statementType", "category", "durationMicros", "durationMillis", "success",
    "errorMessage", "affectedRows", "batchSize", "connectionId", "thread", "slow", "parameters", "traceId", "callSite",
    "requestId", "executionId", "threadKind", "requestPhase",
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
        "retention": None,
    }


def entry_dto(row: dict[str, Any]) -> dict[str, Any]:
    """``SqlTraceEntryDto`` from a stored row: epoch ms; sharpit's ``traceId`` is the request id, so both carry it."""
    dto = {
        **row,
        "timestamp": row["timestamp"] // 1_000_000,
        "requestId": row["traceId"],
        "executionId": None,
        "threadKind": None,
        "requestPhase": None,
    }
    dto.pop("shape", None)  # internal: the recorder's Normalized, kept for grouping without re-normalising
    dto.pop("mysql", None)  # internal: how the grouping re-reads a stored text
    return dto


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


class SqlTotals(NamedTuple):
    """Statement counts survive ring eviction and ``clear()``; the slowest SELECT is reset by ``clear()``."""

    statements: int
    selects: int
    max_millis: int
    max_sql: str | None


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
        # the same statements repeat: per recorder, so one masker's results never reach another's
        self._shape = functools.lru_cache(maxsize=1024)(functools.partial(masked_shape, masker))
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
        self._selects = 0
        self._max_millis = -1  # -1: no SELECT since the last clear
        self._max_sql: str | None = None
        self._lock = threading.Lock()
        self.changes = ChangeStream()

    def totals(self) -> SqlTotals:
        with self._lock:
            return SqlTotals(self._total, self._selects, max(self._max_millis, 0), self._max_sql)

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
        mysql: bool = False,
    ) -> None:
        """Build the masked row once, at capture time; a paused recorder returns before any work."""
        if not self.recording:
            return
        masker = self._masker
        shape = self._shape(sql, mysql)
        stored = shape.sql if not masker.capture_parameters else (masker.mask_text(sql) or "")
        error_message: str | None = None
        if error is not None:
            text = str(error)
            if not masker.capture_parameters:
                if sql:  # before the masker, whose edit would make this miss: SQLAlchemy repeats it in [SQL: ...]
                    text = text.replace(sql.strip(), shape.sql)
                # interim: for another statement than ``sql`` the scan below still reads masked text; ``error_text``
                # replaces all of this at Task 22
                text = masker.mask_text(_driver_values_dropped(text)) or ""  # the scan hides what the masker reads
                text = _sql_block_normalized(text, mysql)
            masked = masker.mask_text(text)
            error_message = _truncate(masked, self._max_sql_length) if masked is not None else None
        has_parameters = bool(parameters)
        millis = duration_ns // 1_000_000
        category = category_of(sql)
        site = call_site if self.capture_call_site else None
        row = {
            "id": 0,
            "timestamp": time.time_ns(),  # epoch ns, for ordering; entry_dto converts to the contract's epoch ms
            "sql": _truncate(stored, self._max_sql_length),
            "statementType": "PREPARED" if has_parameters else "STATEMENT",
            "category": category,
            "durationMicros": duration_ns // 1_000,
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
            "shape": shape,
            "mysql": mysql,
        }
        with self._lock:
            row["id"] = next(self._ids)
            if len(self._entries) == self.max_entries:
                self._evicted += 1
            self._entries.append(row)
            self._total += 1
            self._selects += category == "SELECT"
            if category == "SELECT" and millis > self._max_millis:  # rare: only a new slowest SELECT pays to mask
                self._new_max(millis, shape.sql)
            key = shape.fingerprint
            aggregate = self._aggregates.get(key)
            if aggregate is None:
                aggregate = self._aggregates[key] = _Aggregate(shape.sql, category)
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

    def _new_max(self, millis: int, sql: str) -> None:
        """Under the lock: the slowest SELECT since the last clear, masked like the ring rows."""
        self._max_millis = millis
        shown = self._masker.mask_text(sql)
        self._max_sql = _truncate(shown, self._max_sql_length) if shown is not None else None

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._aggregates.clear()
            self._max_millis, self._max_sql = -1, None
        self.changes.signal()

    def set_recording(self, enabled: bool) -> None:
        if self.recording != enabled:
            self.recording = enabled
            self.changes.signal()

    def rows(self) -> list[dict[str, Any]]:
        """The ring as stored, oldest first (``timestamp`` in epoch ns); ``entry_dto`` builds one DTO."""
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
            "retention": {  # CaptureRetentionDto: a plain ring, no share reserved for slow or failed statements
                "applicationManaged": False,
                "capacity": self.max_entries,
                "reservedCapacity": None,
                "retained": len(rows),
                "reserved": None,
                "evicted": evicted,
                "slowThresholdMillis": self.slow_query_threshold_millis,
            },
        }


_SQL_BLOCK = "[SQL: "
_SQL_ERROR_SHAPE = re.compile(
    r"^(?:sqlalchemy\.(?:exc|engine)\.|(?:psycopg2?|sqlite3|pymysql|MySQLdb|mysql(?:\.connector)?|asyncpg)\.)"
    r"[\w.]+:"
)
# no anchor: SQLAlchemy opens with ``(pymysql.err.X)``, a stack trace names the driver further down
_MYSQL_DRIVER = re.compile(r"\b(?:pymysql|MySQLdb|asyncmy|mariadb|mysql\.connector)\.")
_QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")


def _driver_values_dropped(text: str) -> str:
    """The driver's message without the row values it echoes: PostgreSQL's ``DETAIL:`` lines and quoted values.

    Only the message's first line is kept, with quoted runs as ``?``. SQLAlchemy's ``[SQL: ...]`` and
    ``[parameters: ...]`` lines that follow are kept for the caller to normalise and mask.
    """
    head, sep, tail = text.partition("\n[SQL: ")
    return _QUOTED.sub("?", head.split("\n", 1)[0]) + sep + tail


def _traceback_prefix(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines or not lines[0].startswith("Traceback (most recent call last):"):
        return "", "\n".join(lines)
    frame_count = 1
    for line in lines[1:]:
        if line.startswith("  File ") or (line.startswith("    ") and line.strip()):
            frame_count += 1
        else:
            break
    return "\n".join(lines[:frame_count]), "\n".join(lines[frame_count:])


def _sql_block_normalized(text: str, mysql: bool) -> str:
    """Everything after the first ``[SQL: `` goes through the scan: where a statement ends is a guess, and a wrong guess
    shows a literal. What follows the block is normalised too."""
    start = text.find(_SQL_BLOCK)
    if start < 0:
        return text
    body = start + len(_SQL_BLOCK)
    return text[:body] + normalize(text[body:], mysql).sql


def _redact_sql_errors(text: str, mysql: bool) -> str:
    frames, remainder = _traceback_prefix(text)
    cleaned = _driver_values_dropped(remainder or text)
    return _sql_block_normalized(f"{frames}\n{cleaned}" if frames else cleaned, mysql)


def mask_error(masker: Masker, text: str | None, mysql: bool = False) -> str | None:
    """An error text for display: every path from an exception to output comes here.

    ``Masker.mask_text`` masks secrets by shape, so a literal in the ``[SQL: ...]`` block SQLAlchemy appends passes it.
    With parameter capture off that block is masked, normalised and masked again: the scan turns a key or a token into
    ``?``, which hides it from the masker, so the masker reads the raw text first. ``mysql`` is for text known to be
    MySQL's, and a MySQL driver named in the text counts as known. Text with no block pays one substring check and one
    anchored match.
    """
    if text is None:
        return None
    if not masker.capture_parameters and (_SQL_BLOCK in text or _SQL_ERROR_SHAPE.match(text)):
        known_mysql = mysql or _MYSQL_DRIVER.search(text) is not None
        text = _redact_sql_errors(masker.mask_text(text) or "", known_mysql)
    return masker.mask_text(text)


def cast_sets(parameters: object, executemany: bool) -> Sequence[object]:
    """The parameter sets of one execution: several for ``executemany``, else the single set."""
    if executemany and isinstance(parameters, Sequence) and not isinstance(parameters, str | bytes):
        return cast_sequence(cast(object, parameters))
    return [parameters]


def cast_sequence(values: object) -> Sequence[object]:
    return values if isinstance(values, Sequence) else ()  # pyright: ignore[reportUnknownVariableType]


def cast_mapping(values: object) -> Mapping[object, object]:
    return values if isinstance(values, Mapping) else {}  # pyright: ignore[reportUnknownVariableType]
