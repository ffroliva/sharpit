"""One run's Side Effects rows.

Not thread-safe: its service serializes it (ST:39-40).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Protocol, cast, runtime_checkable

from sharpit.engine.collectors.sideeffects import wording
from sharpit.engine.collectors.sideeffects.pending import Pending

MAX_ROWS_PER_SENSOR: int = 500
MAX_ROWS: int = 2_000
EXEMPLARS: int = 3
CONFIRMATIONS: int = 4
OTHER: str = "Other"
RINGED: tuple[str, ...] = ("processes", "files", "security-sinks")


def epoch_ms() -> int:
    return time.time_ns() // 1_000_000


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


@dataclass(slots=True)
class StoreRow:
    scope: str
    attribution: str
    sensor: str
    kind: str
    target: str
    call_site: str | None = None
    inside_method: str | None = None
    origin: str | None = None
    location: str | None = None
    count: int = 0
    failed: int = 0
    completed: int = 0
    non_zero_exits: int = 0
    last_exit_status: int | None = None
    total_millis: int = 0
    max_millis: int = 0
    first_seen: int = 0
    last_seen: int = 0
    exemplar_request_ids: list[str] = field(default_factory=list[str])
    client: str | None = None
    capture: str | None = None
    captured_by: str | None = None
    left_running: int = 0
    requests: int = 0
    parameter: str | None = None
    detail: str | None = None
    confirmed: bool = False
    standalone: bool = False

    @property
    def callSite(self) -> str | None:
        return self.call_site

    @property
    def insideMethod(self) -> str | None:
        return self.inside_method

    @property
    def nonZeroExits(self) -> int:
        return self.non_zero_exits

    @property
    def lastExitStatus(self) -> int | None:
        return self.last_exit_status

    @property
    def totalMillis(self) -> int:
        return self.total_millis

    @property
    def maxMillis(self) -> int:
        return self.max_millis

    @property
    def firstSeen(self) -> int:
        return self.first_seen

    @property
    def lastSeen(self) -> int:
        return self.last_seen

    @property
    def exemplarRequestIds(self) -> list[str]:
        return self.exemplar_request_ids

    @property
    def capturedBy(self) -> str | None:
        return self.captured_by

    @property
    def leftRunning(self) -> int:
        return self.left_running


@dataclass(frozen=True, slots=True)
class RowKey:
    scope: str
    attribution: str
    sensor: str
    kind: str
    target: str
    call_site: str | None
    location: str | None
    parameter: str | None


def _stands_alone(row: Mapping[str, object]) -> bool:
    sensor = row.get("sensor") or row.get("source")
    if sensor != "security-sinks":
        return True
    return not (bool(row.get("numeric", False)) or bool(row.get("positionUnknown", False)))


def _attribution_and_scope(row: Mapping[str, object], request_id: str | None) -> tuple[str, str]:
    if request_id is not None:
        scope = str(row.get("scope") or "route")
        attribution = str(row.get("attribution") or row.get("route") or f"route:{request_id}")
        return scope, attribution
    if row.get("scope") == "startup":
        return "startup", "startup"
    thread_name = row.get("threadName")
    if thread_name:
        return "thread", str(row.get("attribution") or thread_name)
    return "unattributed", str(row.get("attribution") or "(unattributed)")


class Row:
    __slots__ = (
        "key",
        "count",
        "failed",
        "completed",
        "non_zero_exits",
        "last_exit_status",
        "total_millis",
        "max_millis",
        "first_seen",
        "last_seen",
        "exemplars",
        "origin",
        "client",
        "capture",
        "captured_by",
        "left_running",
        "requests",
        "standalone",
        "confirmations",
    )

    def __init__(self, key: RowKey) -> None:
        self.key = key
        self.count = 0
        self.failed = 0
        self.completed = 0
        self.non_zero_exits = 0
        self.last_exit_status: int | None = None
        self.total_millis = 0
        self.max_millis = 0
        self.first_seen = 0
        self.last_seen = 0
        self.exemplars: list[str] = []
        self.origin: str | None = None
        self.client: str | None = None
        self.capture: str | None = None
        self.captured_by: str | None = None
        self.left_running = 0
        self.requests = 0
        self.standalone = False
        self.confirmations: list[tuple[int, int, str]] = []

    def remember(self, raw_hash: int, redacted_hash: int, request_id: str | None) -> None:
        if raw_hash == 0 or redacted_hash == 0 or request_id is None:
            return
        for r_h, red_h, _ in self.confirmations:
            if r_h == raw_hash and red_h == redacted_hash:
                return
        if len(self.confirmations) < CONFIRMATIONS:
            self.confirmations.append((raw_hash, redacted_hash, request_id))

    def confirmed(self) -> bool:
        n = len(self.confirmations)
        for i in range(n):
            r1, red1, req1 = self.confirmations[i]
            for j in range(i + 1, n):
                r2, red2, req2 = self.confirmations[j]
                if red1 == red2 and r1 != r2 and req1 != req2:
                    return True
        return False

    def shown(self) -> bool:
        return self.standalone or self.confirmed()

    def add(self, row: Mapping[str, object], request_id: str | None, clock: Callable[[], int]) -> None:
        count = _as_int(row.get("count"), 1)
        self.count += count
        at = _as_int(row.get("at")) or clock()
        self.first_seen = at if self.first_seen == 0 else min(self.first_seen, at)
        self.last_seen = max(self.last_seen, at)
        if self.origin is None and (o := row.get("origin")):
            self.origin = str(o)
        if request_id is not None and len(self.exemplars) < EXEMPLARS and request_id not in self.exemplars:
            self.exemplars.append(request_id)
        if self.key.sensor == "security-sinks":
            self.standalone |= _stands_alone(row)
            raw_hash = _as_int(row.get("rawHash"))
            redacted_hash = _as_int(row.get("redactedHash"))
            self.remember(raw_hash, redacted_hash, request_id)
        else:
            self.standalone = True

    def detail(self) -> str | None:
        if self.key.sensor != "security-sinks":
            return None
        if self.key.scope == "other":
            return wording.OTHER
        mapped_kind = "file path" if self.key.kind in ("file-path", "file path") else self.key.kind
        return wording.detail(mapped_kind, self.key.parameter, self.key.target, confirmed=self.confirmed())

    def to_store_row(self) -> StoreRow:
        return StoreRow(
            scope=self.key.scope,
            attribution=self.key.attribution,
            sensor=self.key.sensor,
            kind=self.key.kind,
            target=self.key.target,
            call_site=self.key.call_site,
            inside_method=None,
            origin=self.origin,
            location=self.key.location,
            count=self.count,
            failed=self.failed,
            completed=self.completed,
            non_zero_exits=self.non_zero_exits,
            last_exit_status=self.last_exit_status,
            total_millis=self.total_millis,
            max_millis=self.max_millis,
            first_seen=self.first_seen,
            last_seen=self.last_seen,
            exemplar_request_ids=list(self.exemplars),
            client=self.client,
            capture=self.capture,
            captured_by=self.captured_by,
            left_running=self.left_running,
            requests=self.requests,
            parameter=self.key.parameter,
            detail=self.detail(),
            confirmed=self.confirmed(),
            standalone=self.standalone,
        )


@runtime_checkable
class SensorRows(Protocol):
    def drain(self, sensor: str) -> list[dict[str, object]]: ...

    def cleared_at(self, sensor: str) -> int: ...


class SideEffectsStore:
    """One run's Side Effects rows.

    Not thread-safe: its service serializes it (ST:39-40).
    """

    def __init__(
        self,
        rows: SensorRows,
        intake: Callable[[Mapping[str, object]], dict[str, object]] = dict,
        clock: Callable[[], int] = epoch_ms,
        max_rows_per_sensor: int = MAX_ROWS_PER_SENSOR,
        max_rows: int = MAX_ROWS,
        route_reader: Callable[[AbstractSet[str]], dict[str, str]] | None = None,
        ready_at: Callable[[], int | None] = lambda: None,
        routes_hidden: Callable[[], bool] = lambda: False,
    ) -> None:
        self._rows = rows
        self._intake = intake
        self.pending = Pending(route_reader, ready_at, routes_hidden) if route_reader is not None else None
        self._clock = clock
        self._max_rows_per_sensor = max_rows_per_sensor
        self._max_rows = max_rows
        self._store_rows: dict[RowKey, Row] = {}
        self._rows_per_sensor: dict[str, int] = {}
        self._last_seen_cleared_at: dict[str, int] = dict.fromkeys(RINGED, 0)
        self._cleared_at = 0
        self._clears = 0
        self._cleared = 0
        self._unconfirmed_past_cap = 0
        self._folded = 0

    def _is_visible(self, row: Row) -> bool:
        if row.key.sensor != "security-sinks":
            return True
        if row.key.scope == "other":
            return True
        return row.shown()

    def _drop_sensor_rows(self, sensor: str) -> None:
        keys_to_remove = [k for k, r in self._store_rows.items() if r.key.sensor == sensor]
        for k in keys_to_remove:
            del self._store_rows[k]
        self._rows_per_sensor[sensor] = 0
        if sensor == "security-sinks":
            self._unconfirmed_past_cap = 0

    def _fold_other(self, row: Mapping[str, object], sensor: str, kind: str, count: int) -> None:
        other_key = RowKey("other", OTHER, sensor, kind, OTHER, None, None, None)
        other_row = self._store_rows.get(other_key)
        if other_row is None:
            if len(self._store_rows) >= self._max_rows + len(RINGED):
                return
            other_row = Row(other_key)
            self._store_rows[other_key] = other_row
        self._folded += count
        other_row.add(row, request_id=None, clock=self._clock)

    def _aggregate(self, row: Mapping[str, object]) -> None:
        sensor = str(row.get("sensor") or row.get("source") or "processes")
        default_kind = "process" if sensor == "processes" else "read" if sensor == "files" else "command"
        kind = str(row.get("kind") or default_kind)
        count = _as_int(row.get("count"), 1)
        request_id = row.get("requestId")
        req_id_str = str(request_id) if request_id is not None else None
        scope, attribution = _attribution_and_scope(row, req_id_str)

        key = RowKey(
            scope=scope,
            attribution=attribution,
            sensor=sensor,
            kind=kind,
            target=str(row.get("target") or ""),
            call_site=cast("str | None", row.get("callSite") or row.get("call_site")),
            location=cast("str | None", row.get("location")),
            parameter=cast("str | None", row.get("parameter")),
        )

        existing = self._store_rows.get(key)
        if existing is not None:
            existing.add(row, req_id_str, clock=self._clock)
            return

        per_sensor = self._rows_per_sensor.get(sensor, 0)
        at_cap = per_sensor >= self._max_rows_per_sensor or len(self._store_rows) >= self._max_rows
        if at_cap:
            if sensor == "security-sinks" and not _stands_alone(row):
                self._unconfirmed_past_cap += count
                return
            self._fold_other(row, sensor, kind, count)
            return

        new_row = Row(key)
        new_row.add(row, req_id_str, clock=self._clock)
        self._store_rows[key] = new_row
        self._rows_per_sensor[sensor] = per_sensor + 1

    def drain(self) -> None:
        """Drain the sensor rings and aggregate rows."""
        for sensor in RINGED:
            ring_cleared_at = self._rows.cleared_at(sensor)
            if ring_cleared_at > self._last_seen_cleared_at.get(sensor, 0):
                self._drop_sensor_rows(sensor)
                self._last_seen_cleared_at[sensor] = ring_cleared_at
                self._cleared_at = max(self._cleared_at, ring_cleared_at)
                self._clears += 1

            drained = self._rows.drain(sensor)
            clear_watermark = max(self._cleared_at, self._last_seen_cleared_at.get(sensor, 0))
            for row in drained:
                row_at = _as_int(row.get("at"))
                if clear_watermark > 0 and row_at <= clear_watermark:
                    self._cleared += 1
                    continue
                intake_row = self._intake(row)
                if self.pending is None:
                    self._aggregate(intake_row)
                else:
                    request_id = intake_row.get("requestId")
                    self.pending.add(intake_row, str(request_id) if request_id is not None else None)
        if self.pending is not None:
            for row in self.pending.resolve(self._clock()):
                self._aggregate(row)

    def rows_of(self, sensor: str) -> list[StoreRow]:
        """Return the visible rows of sensor."""
        candidates = [r for r in self._store_rows.values() if r.key.sensor == sensor and self._is_visible(r)]
        candidates.sort(
            key=lambda r: (
                1 if r.key.scope == "other" else 0,
                -(r.count + r.completed),
                -r.last_seen,
            )
        )
        return [r.to_store_row() for r in candidates]

    def counts(self, sensor: str) -> tuple[int, int]:
        """Return (row_count, occurrences) of visible rows for sensor."""
        visible = self.rows_of(sensor)
        return len(visible), sum(r.count for r in visible)

    def unconfirmed(self) -> int:
        """Return the count of unconfirmed security-sinks matches."""
        hidden = self._unconfirmed_past_cap
        for row in self._store_rows.values():
            if row.key.sensor == "security-sinks" and not self._is_visible(row):
                hidden += 1
        return hidden

    def folded(self) -> int:
        """Return operations counted in Other rows."""
        return self._folded

    def clears(self) -> int:
        """Return how many recording clears were observed."""
        return self._clears

    def cleared(self) -> int:
        """Return rows dropped because their timestamp was not after a clear."""
        return self._cleared

    def clear(self, now: int) -> None:
        """Clear store state at now."""
        self._store_rows.clear()
        self._rows_per_sensor.clear()
        self._unconfirmed_past_cap = 0
        self._folded = 0
        self._cleared_at = now
        if self.pending is not None:
            self.pending.clear(now)
        for sensor in RINGED:
            self._last_seen_cleared_at[sensor] = max(self._last_seen_cleared_at.get(sensor, 0), now)
        self._clears += 1
