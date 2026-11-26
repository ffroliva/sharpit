"""The security-sinks matcher: joins request context, holder and an injected ownership port; builds sink rows."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from sharpit.engine.capture.correlation import INTERNAL, REQUEST, RequestInfo
from sharpit.engine.sensors.sinks.values import (
    F_BUSY,
    F_SEEN,
    MIN_LENGTH,
    Kind,
    Match,
    RequestValues,
    keyed_hash,
)

Row = Mapping[str, object]
_EMPTY_SCOPE: Mapping[str, Any] = {}
_BUSY = Match((), (), F_BUSY, None, frozenset())
_INTERNAL_GET = INTERNAL.get
_REQUEST_GET = REQUEST.get
_UNSET: Any = object()


def _no_owner(scope: Mapping[str, Any]) -> str | None:
    del scope
    return None


class SinkMatcher:
    def __init__(
        self,
        context_id: str,
        on: Callable[[], bool] | bool = True,
        values: RequestValues | None = None,
        owner: Callable[[Mapping[str, Any]], str | None] = _no_owner,
    ) -> None:
        self._context_id = context_id
        # a bool is a constant; a callable is asked on every check
        self.enabled = on if isinstance(on, bool) else True
        self._on = None if isinstance(on, bool) else on
        self._values = values if values is not None else RequestValues()
        self._owner = owner

    def check(self, text: str, kind: Kind, request: RequestInfo | None = _UNSET) -> Match | None:
        # ported: RequestValues.java:680-725, check order per spec
        if not self.enabled or (self._on is not None and not self._on()):
            return None
        if request is _UNSET:
            request = _REQUEST_GET()
        if request is None or request.context_id != self._context_id or len(text) < MIN_LENGTH or _INTERNAL_GET():
            return None
        try:
            return self._values.match(request, text, kind)
        except Exception:
            return _BUSY

    def rows(
        self, kind: Kind, match: Match, text: str, target: str | None, request: RequestInfo | None = _UNSET
    ) -> tuple[Row, ...]:
        if match.flags & F_SEEN or not match.names:
            return ()
        if request is _UNSET:
            request = _REQUEST_GET()
        if request is None or request.context_id != self._context_id:
            return ()
        scope: Mapping[str, Any] = request.scope if request.scope is not None else _EMPTY_SCOPE
        try:
            call_site = self._owner(scope)
        except Exception:
            return ()
        if call_site is None:
            return ()
        self._values.mark_seen(request.id, match)
        row_kind = "file-path" if kind == "file" else "command"
        at = time.time_ns() // 1_000_000
        raw_hash = keyed_hash(text)
        redacted_hash = keyed_hash(match.redacted) if match.redacted is not None else 0
        return tuple(
            {
                "source": "security-sinks",
                "kind": row_kind,
                "target": target,
                "parameter": name,
                "numeric": name in match.numeric,
                "positionUnknown": name in match.unreported,
                "callSite": call_site,
                "at": at,
                "requestId": request.id,
                "rawHash": raw_hash,
                "redactedHash": redacted_hash,
            }
            for name in match.names
        )

    def holder_status(self) -> dict[str, int]:
        return self._values.status()

    def request_ended(self, request_id: str) -> None:
        self._values.end(request_id)

    def clear(self) -> None:
        self._values.clear()

    def __repr__(self) -> str:
        return "SinkMatcher()"


class SecuritySinksSensor:
    name = "security-sinks"
    events: tuple[str, ...] = ()
    matcher: SinkMatcher

    def __init__(self, matcher: SinkMatcher) -> None:
        self.matcher = matcher

    def record(self, event: str, args: tuple[Any, ...]) -> tuple[Row, ...]:
        return ()

    def wipe(self) -> None:
        self.matcher.clear()

    def __repr__(self) -> str:
        return "SecuritySinksSensor()"
