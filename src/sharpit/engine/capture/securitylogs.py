"""``security-logs`` (BootUI ``SecurityLogsService``): a bounded audit ring, masked at read."""

from __future__ import annotations

import inspect
import logging
import re
import threading
import time
import weakref
from collections import Counter, deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from sharpit.engine.capture.correlation import REQUEST
from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import MASK, Masker
from sharpit.engine.paging import paged
from sharpit.engine.panels import panel_is_implemented

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

logger = logging.getLogger("sharpit")

PANEL = "security-logs"
AUTHENTICATION_SUCCESS = "AUTHENTICATION_SUCCESS"
AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
DEFAULT_MAX_LOGS = 500
# fastapi/capture.py CAPTURE_TOO_LATE_REASON, which the engine may not import (tests pin the two equal)
CAPTURE_UNAVAILABLE_REASON = "Request capture is unavailable: install() ran after the app started"
INVALID_AFTER = "Invalid 'after' parameter: expected an ISO-8601 instant with an offset"
MAX_DATA_ENTRIES = 20
MAX_VALUE_LENGTH = 256
_ADDRESS_MARKERS = ("sessionid", "remoteaddress", "remoteaddr", "ipaddress")
_NON_ALNUM = re.compile(r"[^a-z0-9]")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SECOND = 1_000_000_000
# installed contexts whose panel is enabled, by context id: record_security_event finds the current request's app here
_contexts: weakref.WeakValueDictionary[str, SharpitContext] = weakref.WeakValueDictionary()


class SecurityEvent(NamedTuple):
    timestamp_ns: int
    principal: str | None
    type: str
    data: tuple[tuple[str, str | None], ...]  # sorted by key, at most MAX_DATA_ENTRIES
    omitted: int
    request_id: str | None


def clamp_max_logs(n: int) -> int:
    return min(max(n, 1), 10_000)


class SecurityEventBuffer:
    """Raw events, newest kept; values are stringified on the host thread so a read never runs host code."""

    def __init__(self, max_logs: int) -> None:
        self.max_logs = clamp_max_logs(max_logs)
        self.changes = ChangeStream()
        self._events: deque[SecurityEvent] = deque(maxlen=self.max_logs)
        self._lock = threading.Lock()

    def add(
        self,
        type: str,
        principal: str | None,
        data: Mapping[str, object],
        request_id: str | None,
        *,
        timestamp_ns: int | None = None,
    ) -> None:
        items = sorted(((str(k), None if v is None else str(v)) for k, v in data.items()), key=lambda kv: kv[0])
        event = SecurityEvent(
            time.time_ns() if timestamp_ns is None else timestamp_ns,
            principal,
            type,
            tuple(items[:MAX_DATA_ENTRIES]),
            max(len(items) - MAX_DATA_ENTRIES, 0),
            request_id,
        )
        with self._lock:
            self._events.append(event)
        self.changes.signal()

    def snapshot(self) -> list[SecurityEvent]:
        with self._lock:
            return list(self._events)


def format_instant(timestamp_ns: int) -> str:
    """Java ``Instant.toString()``: the fraction in groups of three digits, none for a whole second."""
    seconds, nanos = divmod(timestamp_ns, _SECOND)
    text = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    if nanos == 0:
        return f"{text}Z"
    if nanos % 1_000_000 == 0:
        return f"{text}.{nanos // 1_000_000:03d}Z"
    if nanos % 1000 == 0:
        return f"{text}.{nanos // 1000:06d}Z"
    return f"{text}.{nanos:09d}Z"


def parse_after(raw: str | None) -> int | None:
    """An ISO-8601 instant with an offset (``Z`` or ``+02:00``) as epoch ns; blank is None; anything else ValueError."""
    if raw is None or not raw.strip():
        return None
    parsed = datetime.fromisoformat(raw.strip())
    if parsed.tzinfo is None:
        raise ValueError("the instant has no offset")
    return (parsed - _EPOCH) // timedelta(microseconds=1) * 1000


def _row(masker: Masker, masks_keys: bool, name: str, value: str | None) -> dict[str, Any]:
    shown, masked = masker.mask(name, value)
    if shown is not None and not masked:
        if masks_keys and any(m in _NON_ALNUM.sub("", name.lower()) for m in _ADDRESS_MARKERS):
            shown, masked = MASK, True
        else:  # sharpit widening: a secret inside the text (``Bearer <jwt>``, ``token=...``) is scrubbed
            scrubbed = masker.mask_text(str(shown))
            shown, masked = scrubbed, scrubbed != shown
    truncated = isinstance(shown, str) and len(shown) > MAX_VALUE_LENGTH
    if truncated:
        shown = f"{str(shown)[:MAX_VALUE_LENGTH]}..."
    return {"name": name, "value": shown, "masked": masked, "truncated": truncated}


def _event(event: SecurityEvent, masker: Masker, metadata_only: bool, masks_keys: bool) -> dict[str, Any]:
    rows = [_row(masker, masks_keys, name, value) for name, value in event.data]
    if event.omitted:
        rows.append(
            {"name": "...", "value": f"{event.omitted} more entries omitted", "masked": False, "truncated": False}
        )
    return {
        "timestamp": format_instant(event.timestamp_ns),
        "principal": None if metadata_only else event.principal,
        "type": event.type,
        "data": rows,
        "traceId": event.request_id,  # sharpit has no trace id here; the request id correlates, as exchanges do
        "requestId": event.request_id,
    }


def security_logs_report(
    buffer: SecurityEventBuffer | None,
    masker: Masker,
    *,
    principal: str | None,
    type: str | None,
    after_ns: int | None,
    offset: int | None,
    limit: int | None,
    unavailable_reason: str | None,
) -> dict[str, Any]:
    """Filter, newest first, at most ``maxLogs``, type summaries over the kept set, then page (BootUI order)."""
    if buffer is None:
        empty: list[SecurityEvent] = []
        _, page = paged(empty, None, None, None, lambda _e: ())
        return {
            "auditEventsPresent": False,
            "unavailableReason": unavailable_reason,
            "maxLogs": DEFAULT_MAX_LOGS,
            "typeSummaries": [],
            "events": [],
            "page": page,
        }
    who, kind = (principal or "").strip(), (type or "").strip()
    events = [
        e
        for e in reversed(buffer.snapshot())
        if (not who or e.principal == who)
        and (not kind or e.type == kind)
        and (after_ns is None or e.timestamp_ns > after_ns)
    ]
    events.sort(key=lambda e: e.timestamp_ns, reverse=True)  # stable: equal stamps keep newest-added first
    del events[buffer.max_logs :]
    counts = sorted(Counter(e.type for e in events).items(), key=lambda tc: (-tc[1], tc[0]))
    kept, page = paged(events, None, offset, limit, lambda _e: ())
    metadata_only = masker.mask_text("") is None  # mask_text returns None for a string only under METADATA_ONLY
    masks_keys = masker.mask("secret", "x")[1]  # the policy that masks a secret key name: MASKED + mask-secrets
    return {
        "auditEventsPresent": True,
        "unavailableReason": unavailable_reason,
        "maxLogs": buffer.max_logs,
        "typeSummaries": [{"type": t, "count": c} for t, c in counts],
        "events": [_event(e, masker, metadata_only, masks_keys) for e in kept],
        "page": page,
    }


def context_report(
    ctx: SharpitContext,
    *,
    principal: str | None = None,
    type: str | None = None,
    after_ns: int | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """The panel's report for one context: without the capture middleware only recorded events arrive (contract)."""
    buffer = ctx.capture.security_logs
    attached = getattr(ctx.capture.wiring, "middleware_added", False)
    return security_logs_report(
        buffer if isinstance(buffer, SecurityEventBuffer) else None,
        ctx.masker,
        principal=principal,
        type=type,
        after_ns=after_ns,
        offset=offset,
        limit=limit,
        unavailable_reason=None if attached else CAPTURE_UNAVAILABLE_REASON,
    )


def principal_of(user: object) -> str | None:
    """``scope["user"]``'s plain ``identity`` attribute, else its type name; never runs a user property."""
    if user is None or type(user).__name__ == "UnauthenticatedUser":
        return None
    identity = inspect.getattr_static(user, "identity", None)  # a property comes back as the descriptor, unrun
    return identity if isinstance(identity, str) else type(user).__name__


def on_security_event(buffer: SecurityEventBuffer, masker: Masker) -> Callable[[Mapping[str, Any], int], None]:
    """The capture middleware's 401/403 hook; it runs before the request id is reset (R12)."""

    def hook(scope: Mapping[str, Any], status: int) -> None:
        info = REQUEST.get()
        data = {"method": scope["method"], "path": masker.mask_path(scope["path"]), "status": status}
        kind = AUTHENTICATION_FAILURE if status == 401 else AUTHORIZATION_FAILURE
        buffer.add(kind, principal_of(scope.get("user")), data, info.id if info is not None else None)

    return hook


def attach(ctx: SharpitContext) -> Callable[[Mapping[str, Any], int], None] | None:
    """Give an enabled panel its buffer and its context registration; return the 401/403 hook, or None."""
    if not (panel_is_implemented(PANEL) and ctx.settings.panels[PANEL].enabled):
        return None
    buffer = ctx.capture.security_logs = SecurityEventBuffer(ctx.settings.security_logs_max_logs)
    _contexts[ctx.context_id] = ctx
    return on_security_event(buffer, ctx.masker)


def record_security_event(type: str, principal: str | None = None, data: Mapping[str, object] | None = None) -> None:
    """Record an audit event (e.g. ``AUTHENTICATION_SUCCESS``) in the sharpit console of the app serving the current
    request. Outside a request, for an inactive sharpit or a disabled panel it does nothing; it never raises."""
    try:
        info = REQUEST.get()
        ctx = _contexts.get(info.context_id) if info is not None else None
        buffer = ctx.capture.security_logs if ctx is not None else None
        if info is None or not isinstance(buffer, SecurityEventBuffer):
            return
        given = cast("tuple[object, object, object]", (type, principal, data))  # public API: untyped callers
        if not (isinstance(given[0], str) and given[0].strip()) or not isinstance(given[1], str | None):
            logger.warning("sharpit record_security_event dropped an event: type must be a non-blank str")
            return
        if not isinstance(given[2], Mapping | None):
            logger.warning("sharpit record_security_event dropped an event: data must be a mapping")
            return
        buffer.add(type.strip(), principal, data or {}, info.id)
    except Exception as exc:  # noqa: BLE001 - the host's request never fails on sharpit
        logger.warning("sharpit record_security_event dropped an event (%s)", exc.__class__.__name__)
