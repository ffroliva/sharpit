"""HTTP Exchanges (F1, spec §7.1): the bounded ring of served requests and its report.

Port of BootUI ``HttpExchangeBuffer`` and ``HttpExchangesService``. Rows are built and masked at capture time, so the
buffer never holds a raw secret; ``report()`` only filters and pages.
"""

from __future__ import annotations

import re
import threading
from collections import deque
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import Masker
from sharpit.engine.paging import paged

MAX_PATH = 2048
MAX_QUERY = 2048
MAX_HEADERS = 50  # per side
MAX_VALUE = 1024

# HttpExchangeDto, in BootUI's record order; rows carry two more keys (``error``, ``endpoint``) for later panels
DTO_KEYS = (
    "id", "timestamp", "method", "path", "query", "uri", "status", "statusFamily", "durationMs", "responseSizeBytes",
    "remoteAddress", "principal", "sessionId", "traceId", "requestHeaders", "responseHeaders",
)  # fmt: skip
_TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}", re.IGNORECASE)
_EMPTY_PAGE = {"total": 0, "matched": 0, "offset": 0, "limit": 0, "returned": 0, "hasMore": False}

RawHeaders = Sequence[tuple[bytes, bytes]]


def _cut(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[: cap - 1] + "…"


def status_family(status: int) -> str:
    return f"{status // 100}xx" if 100 <= status < 600 else "unknown"


def _iso(epoch_ns: int) -> str:
    """ISO-8601 UTC with milliseconds and ``Z``, as Jackson writes an ``Instant``."""
    stamp = datetime.fromtimestamp(epoch_ns // 1_000_000_000, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{stamp}.{epoch_ns // 1_000_000 % 1000:03d}Z"


def _headers(masker: Masker, raw: RawHeaders) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for name, value in raw[:MAX_HEADERS]:
        grouped.setdefault(_cut(name.decode("latin-1"), MAX_VALUE), []).append(value.decode("latin-1"))
    rows: list[dict[str, Any]] = []
    for name in sorted(grouped, key=str.lower):
        values, masked = masker.mask_header(name, grouped[name])  # mask first: a cut must not hide a secret
        rows.append({"name": name, "values": [_cut(v, MAX_VALUE) for v in values], "masked": masked})
    return rows


def trace_id(request_headers: RawHeaders, request_id: str) -> str:
    """The trace id of a valid W3C ``traceparent`` (non-zero), else the request id."""
    for name, value in request_headers:
        if name == b"traceparent":
            match = _TRACEPARENT.fullmatch(value.decode("latin-1").strip())
            if match and match.group(1).strip("0"):
                return match.group(1).lower()
            break
    return request_id


def exchange_row(
    masker: Masker,
    *,
    request_id: str,
    started_epoch_ns: int,
    method: str,
    path: str,
    query_string: bytes,
    status: int,
    duration_ms: int,
    size: int,
    client: Sequence[object] | None,
    user: object,
    request_headers: RawHeaders,
    response_headers: RawHeaders,
    error: bool = False,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """One masked, capped row: the ``HttpExchangeDto`` keys plus ``error`` and ``endpoint``."""
    shown_path = _cut(masker.mask_path(path), MAX_PATH)
    raw_query = query_string.decode("latin-1")
    query = masker.mask_query(raw_query) if raw_query else None
    query = None if query is None else _cut(query, MAX_QUERY)
    principal = None
    if user is not None and getattr(user, "is_authenticated", False):  # Starlette's AuthenticationMiddleware
        principal = masker.mask("principal", getattr(user, "display_name", None))[0]
    return {
        "id": request_id,
        "timestamp": _iso(started_epoch_ns),
        "method": method,
        "path": shown_path,
        "query": query,
        "uri": shown_path + (f"?{query}" if query else ""),
        "status": status,
        "statusFamily": status_family(status),
        "durationMs": duration_ms,
        "responseSizeBytes": size,
        "remoteAddress": str(client[0]) if client else None,
        "principal": principal,
        "sessionId": None,  # Starlette sessions are signed cookies with no id
        "traceId": trace_id(request_headers, request_id),
        "requestHeaders": _headers(masker, request_headers),
        "responseHeaders": _headers(masker, response_headers),
        "error": error,
        "endpoint": endpoint,
    }


def unavailable_report(reason: str) -> dict[str, Any]:
    """``HttpExchangesReport.unavailable``."""
    return {
        "total": 0,
        "recorded": 0,
        "hiddenSelf": 0,
        "exchanges": [],
        "page": dict(_EMPTY_PAGE),
        "unavailableReason": reason,
    }


class HttpExchangeBuffer:
    """``deque(maxlen)`` behind a lock; ``hidden_self`` counts sharpit's own requests, which are never stored."""

    def __init__(self, max_exchanges: int) -> None:
        self._rows: deque[dict[str, Any]] = deque(maxlen=max_exchanges)
        self._lock = threading.Lock()
        self.hidden_self = 0
        self.unavailable_reason: str | None = None  # set by the wiring when the middleware could not be added
        self.changes = ChangeStream()

    def add(self, row: dict[str, Any]) -> None:
        with self._lock:
            self._rows.append(row)
        self.changes.signal()

    def count_hidden_self(self) -> None:
        with self._lock:
            self.hidden_self += 1

    def get(self, request_id: str) -> dict[str, Any] | None:
        """The stored row (``error`` and ``endpoint`` included), or ``None`` once evicted."""
        with self._lock:
            return next((r for r in reversed(self._rows) if r["id"] == request_id), None)

    def report(
        self, q: str | None, method: str | None, status_class: str | None, offset: int | None, limit: int | None
    ) -> dict[str, Any]:
        if self.unavailable_reason is not None:
            return unavailable_report(self.unavailable_reason)
        with self._lock:
            rows = list(reversed(self._rows))  # newest first
            hidden = self.hidden_self
        wanted_method = (method or "").strip().upper()
        wanted_family = (status_class or "").strip()
        filtered = [
            r
            for r in rows
            if (not wanted_method or r["method"].upper() == wanted_method)
            and (not wanted_family or r["statusFamily"] == wanted_family)
        ]
        # HttpExchangesService.matchesQuery: path, query, uri and traceId; the method has its own filter
        page_rows, page = paged(filtered, q, offset, limit, lambda r: (r["path"], r["query"], r["uri"], r["traceId"]))
        page["total"] = len(rows)  # PagedList: total counts every visible row, matched the filtered ones
        return {
            "total": len(rows),
            "recorded": len(rows) + hidden,  # BootUI: every captured exchange, self traffic included
            "hiddenSelf": hidden,
            "exchanges": [{k: r[k] for k in DTO_KEYS} for r in page_rows],
            "page": page,
            "unavailableReason": None,
        }
