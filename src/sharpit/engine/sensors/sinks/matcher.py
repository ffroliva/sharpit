"""The security-sinks matcher: joins request context, holder and an injected ownership port; builds sink rows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sharpit.engine.sensors.sinks.values import (
    Kind,
    Match,
    RequestValues,
)

Row = Mapping[str, object]

_STUB_MATCH = Match((), (), 0, None, frozenset())


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
        return _STUB_MATCH

    def rows(self, kind: Kind, match: Match, text: str, target: str | None) -> tuple[Row, ...]:
        return ()

    def request_ended(self, request_id: str) -> None:
        pass

    def clear(self) -> None:
        pass


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
