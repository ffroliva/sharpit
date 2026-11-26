from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

PENDING_MILLIS = 30_000
MAX_PENDING = 10_000
READ_RESOLVE_MILLIS = 250
MAX_THREAD_FAMILY = 120
UNKNOWN_ROUTE = "(unknown route)"
ROUTE_HIDDEN = "(route hidden)"
_SAFE_OR_DIGITS = re.compile(r"\d+|[^a-zA-Z._:/ \[\]-]+")
_SECRET_TOKEN = re.compile(
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|(?:gh[pousr]_|github_pat_|glpat-|xox[bpa]-|AIza|sk-(?:live|test|ant|proj)_)[A-Za-z0-9_-]{16,}"
)


def thread_family(name: str | None) -> str | None:
    if not name:
        return None
    safe = name[:MAX_THREAD_FAMILY]
    safe = _SECRET_TOKEN.sub("******", safe)
    return _SAFE_OR_DIGITS.sub(lambda match: "{n}" if match.group().isdigit() else "?", safe)


@dataclass(slots=True)
class _Waiting:
    observation: dict[str, object]
    request_id: str | None


class Pending:
    """Rows awaiting the retained HTTP event that names their request."""

    def __init__(self, reader: Callable[[AbstractSet[str]], dict[str, str]], ready_at: Callable[[], int | None]):
        self.reader = reader
        self.ready_at = ready_at
        self._waiting: list[_Waiting] = []
        self.dropped = 0
        self._last_read = 0
        self._routes: dict[str, str] = {}

    @property
    def waiting_count(self) -> int:
        return len(self._waiting)

    def add(self, observation: Mapping[str, object], request_id: str | None) -> None:
        if len(self._waiting) >= MAX_PENDING:
            self.dropped += 1
            return
        self._waiting.append(_Waiting(dict(observation), request_id))

    def resolve(self, now: int) -> list[dict[str, object]]:
        ids = frozenset(item.request_id for item in self._waiting if item.request_id is not None)
        if ids and (not self._last_read or now - self._last_read >= READ_RESOLVE_MILLIS):
            self._routes.update(self.reader(ids))
            self._last_read = now

        resolved: list[dict[str, object]] = []
        waiting: list[_Waiting] = []
        for item in self._waiting:
            observation = item.observation
            request_id = item.request_id
            route = self._routes.get(request_id) if request_id is not None else None
            at = _as_int(observation.get("at"))
            if route is not None:
                resolved.append(_owned(observation, route, request_id))
            elif request_id is not None and now - at >= PENDING_MILLIS:
                resolved.append(_owned(observation, UNKNOWN_ROUTE, request_id))
            elif request_id is None:
                resolved.append(_unowned(observation, self.ready_at()))
            else:
                waiting.append(item)
        self._waiting = waiting
        waiting_ids = {item.request_id for item in waiting}
        self._routes = {request_id: route for request_id, route in self._routes.items() if request_id in waiting_ids}
        return resolved

    def clear(self, cleared_at: int) -> None:
        self._waiting = [item for item in self._waiting if _as_int(item.observation.get("at")) > cleared_at]


def _as_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _owned(observation: Mapping[str, object], route: str, request_id: str | None) -> dict[str, object]:
    return {
        **observation,
        "scope": "route",
        "attribution": route,
        "requestId": request_id,
    }


def _unowned(observation: Mapping[str, object], ready_at: int | None) -> dict[str, object]:
    at = _as_int(observation.get("at"))
    thread_name = observation.get("threadName")
    if ready_at is not None and at < ready_at:
        scope, attribution = "startup", "startup"
    elif family := thread_family(thread_name if isinstance(thread_name, str) else None):
        scope, attribution = "thread", family
    else:
        scope, attribution = "unattributed", "(unattributed)"
    return {**observation, "scope": scope, "attribution": attribution}
