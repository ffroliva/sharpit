from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from sharpit.engine.masking import Exposure, Masker

PENDING_MILLIS = 30_000
MAX_PENDING = 10_000
READ_RESOLVE_MILLIS = 250
MAX_THREAD_FAMILY = 120
UNKNOWN_ROUTE = "(unknown route)"
_SAFE_OR_DIGITS = re.compile(r"\d+|[^a-zA-Z._:/ \[\]-]+")
_THREAD_NAME_MASKER = Masker(Exposure.MASKED, True)
# own copy: masking's vendor pattern lacks the AWS ids and keeps a lookbehind, so reusing it would change thread names
_SECRET_TOKEN = re.compile(
    r"(?:AKIA|ASIA)[A-Z0-9]{16}"
    r"|(?:sk_live_|sk_test_|rk_live_|pk_live_|ghp_|gho_|ghs_|ghu_|github_pat_|glpat-|xoxb-|xoxp-|xoxa-|AIza|sk-ant-|sk-proj-)[A-Za-z0-9_-]{16,}"
)


def thread_family(name: str | None) -> str | None:
    if not name:
        return None
    safe = _SECRET_TOKEN.sub("******", name)
    safe = _THREAD_NAME_MASKER.mask_text(safe)
    safe = str(safe)[:MAX_THREAD_FAMILY]
    return _SAFE_OR_DIGITS.sub(lambda match: "{n}" if match.group().isdigit() else "?", safe)


@dataclass(slots=True)
class _Waiting:
    observation: dict[str, object]
    request_id: str | None


class Pending:
    """Rows awaiting the retained HTTP event that names their request."""

    def __init__(
        self,
        reader: Callable[[AbstractSet[str]], dict[str, str]],
        ready_at: Callable[[], int | None],
        hidden: Callable[[], bool] = lambda: False,
    ):
        self.reader = reader
        self.hidden = hidden
        self.ready_at = ready_at
        self._waiting: list[_Waiting] = []
        self.dropped = 0
        self.dropped_by_sensor: dict[str, int] = {}
        self._last_read = 0
        self._routes: dict[str, str] = {}

    @property
    def waiting_count(self) -> int:
        return len(self._waiting)

    def add(self, observation: Mapping[str, object], request_id: str | None) -> dict[str, object] | None:
        """Queue a row for its route; when the list is full, a row whose route is known is decided now (ST:958-962)."""
        if len(self._waiting) >= MAX_PENDING:
            route = self._routes.get(request_id) if request_id is not None else None
            if route is not None:
                return _owned(observation, route, request_id)
            self.dropped += 1
            sensor = str(observation.get("sensor") or observation.get("source") or "")
            self.dropped_by_sensor[sensor] = self.dropped_by_sensor.get(sensor, 0) + 1
            return None
        self._waiting.append(_Waiting(dict(observation), request_id))
        return None

    def unowned(self, observation: Mapping[str, object]) -> dict[str, object]:
        """A row with no request needs no route: attributed at once (ST:970-978)."""
        return _unowned(observation, self.ready_at())

    def resolve(self, now: int) -> list[dict[str, object]]:
        hidden = self.hidden()  # without HTTP Exchanges a route is never named later: decide now, the read hides it
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
            elif request_id is not None and (hidden or now - at >= PENDING_MILLIS):
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
