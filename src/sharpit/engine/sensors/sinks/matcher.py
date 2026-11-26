"""The security-sinks matcher: joins request context, holder and an injected ownership port; builds sink rows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sharpit.engine.capture.correlation import INTERNAL, REQUEST
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


class SinkMatcher:
    def __init__(
        self,
        context_id: str,
        on: Callable[[], bool],
        values: RequestValues | None = None,
        owns: Callable[[Mapping[str, Any]], bool] = lambda scope: False,
    ) -> None:
        self._context_id = context_id
        self._on = on
        self._values = values if values is not None else RequestValues()
        self._owns = owns

    def check(self, text: str, kind: Kind) -> Match | None:
        # ported: RequestValues.java:680-725, check order per spec
        if not self._on():
            return None
        if INTERNAL.get():
            return None
        request = REQUEST.get()
        if request is None:
            return None
        if request.context_id != self._context_id:
            return None
        if len(text) < MIN_LENGTH:
            return None
        try:
            return self._values.match(request, text, kind)
        except Exception:
            return Match((), (), F_BUSY, None, frozenset())

    def rows(self, kind: Kind, match: Match, text: str, target: str | None) -> tuple[Row, ...]:
        if match.flags & F_SEEN or not match.names:
            return ()
        request = REQUEST.get()
        if request is None or request.context_id != self._context_id:
            return ()
        scope: Mapping[str, Any] = request.scope if request.scope is not None else _EMPTY_SCOPE
        try:
            owned = self._owns(scope)
        except Exception:
            return ()
        if not owned:
            return ()
        self._values.mark_seen(request.id, match)
        row_kind = "file-path" if kind == "file" else "command"
        raw_hash = keyed_hash(text)
        redacted_hash = keyed_hash(match.redacted) if match.redacted is not None else 0
        return tuple(
            {
                "source": "security-sinks",
                "kind": row_kind,
                "target": target,
                "parameter": name,
                "numeric": name in match.numeric,
                "requestId": request.id,
                "rawHash": raw_hash,
                "redactedHash": redacted_hash,
            }
            for name in match.names
        )

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
