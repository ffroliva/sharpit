"""The sensor lane: which of the process and file sensors a context runs, and how it switches them (W6 lane S3).

Built at install only when ``agent_sensors`` names a sensor this version ships (``processes``, ``files``); with none, no
lane exists and the audit hook is never installed. Each sensor is also a capture-registry entry, so suspending the
registry (idle, low-footprint) switches the sensor off at the hook; detaching (shutdown, ``uninstall_capture``)
unbinds it, leaving the resident hook inert.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sharpit.engine.capture.journal import JournalSink
from sharpit.engine.sensors.audit import AuditHub, Sensor, hub
from sharpit.engine.sensors.files import FilesSensor
from sharpit.engine.sensors.floor import DEFAULT_REASONS, SWITCHABLE_SENSORS
from sharpit.engine.sensors.processes import ProcessesSensor
from sharpit.engine.sensors.rows import SensorRows, TeeSink
from sharpit.engine.sensors.sinks import SecuritySinksSensor, SinkMatcher

BUILT = ("processes", "files", "security-sinks")  # the sensors this version builds
SWITCHABLE = tuple(name for name in SWITCHABLE_SENSORS if name in BUILT)  # BootUI keeps processes always on


def _wipe(sensor: Sensor | None) -> None:
    wipe = getattr(sensor, "wipe", None)
    if callable(wipe):
        wipe()


class SensorHook:
    """One sensor as a capture-registry entry (``Suspendable``)."""

    def __init__(self, name: str, lane: SensorLane) -> None:
        self.name = name
        self._lane = lane

    def suspend(self) -> None:
        self._lane.pause(self.name)

    def resume(self) -> None:
        self._lane.unpause(self.name)

    def discard(self) -> None:
        """Suspension never clears recorded rows; only an explicit recording clear does."""


class SensorLane:
    def __init__(
        self,
        sensors: list[Sensor],
        sink: JournalSink,
        audit: AuditHub = hub,
        configured: tuple[str, ...] | None = None,
        rows: SensorRows | None = None,
    ) -> None:
        self._sensors = {sensor.name: sensor for sensor in sensors}
        self._configured = frozenset(self._sensors if configured is None else configured)
        self._sink = sink
        self._hub = audit
        self._paused: set[str] = set()
        # off by the action or by configuration (a switchable sensor nobody asked for starts off): kept across restarts
        self._off = {name for name in self._sensors if name in SWITCHABLE and name not in self._configured}
        self._matcher: SinkMatcher | None = getattr(self._sensors.get("security-sinks"), "matcher", None)
        self.attached = False
        self.rows = rows or SensorRows()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._sensors)

    def is_on(self, name: str) -> bool:
        return self.attached and name in self._sensors and name not in self._paused and name not in self._off

    def wipe(self, name: str) -> None:
        _wipe(self._sensors.get(name))

    def hooks(self) -> list[SensorHook]:
        return [SensorHook(name, self) for name in self._sensors]

    def attach(self) -> None:
        """Bind every sensor that is neither paused nor switched off; idempotent."""
        self.attached = True
        for name, sensor in self._sensors.items():
            if name not in self._paused | self._off and not self._hub.is_on(sensor):
                self._hub.enable(sensor, self._sink)

    def detach(self) -> None:
        self.attached = False
        for sensor in self._sensors.values():
            self._hub.release(sensor)
            _wipe(sensor)

    def pause(self, name: str) -> None:
        self._paused.add(name)
        if (sensor := self._sensors.get(name)) is not None:
            self._hub.disable(sensor)
            _wipe(sensor)

    def unpause(self, name: str) -> None:
        self._paused.discard(name)
        if self.attached:
            self.attach()

    def request_ended(self, request_id: str) -> None:
        if self._matcher is not None:
            self._matcher.request_ended(request_id)

    def toggles(self) -> list[dict[str, Any]]:
        """``JavaAgentSensorToggleDto`` for each sensor this lane switches at run time."""
        return [
            {
                "id": name,
                "configured": name in self._configured,
                "enabled": (on := name not in self._off),
                "overridden": on != (name in self._configured),
                "state": "installed" if on else "off",
                "optInReason": DEFAULT_REASONS[name],
                "available": True,
                "unavailableReason": None,
                "failure": None,
            }
            for name in self._sensors
            if name in SWITCHABLE
        ]

    def switch(self, name: str, enabled: bool) -> bool:
        """The W6 sensor action: False when this lane cannot switch ``name`` (not configured or not switchable)."""
        if name not in self._sensors or name not in SWITCHABLE:
            return False
        if enabled:
            self._off.discard(name)
            if self.attached:
                self.attach()
        else:
            self._off.add(name)
            sensor = self._sensors[name]
            self._hub.disable(sensor)
            _wipe(sensor)
        return True


def build_lane(
    configured: tuple[str, ...],
    sink: JournalSink | None,
    mask_path: Callable[[str], str],
    own: tuple[str, ...] = (),
    audit: AuditHub = hub,
    *,
    request_values: bool = False,
    context_id: str = "",
    owner: Callable[[Mapping[str, Any]], str | None] = lambda scope: None,
    owns: Callable[[Mapping[str, Any]], bool] | None = None,
) -> SensorLane | None:
    """The lane for ``configured`` sensors, or None: nothing configured, or no journal to offer to."""
    available = BUILT if request_values else tuple(name for name in BUILT if name != "security-sinks")
    if not any(name in configured for name in available) or sink is None:
        return None
    lane: SensorLane | None = None
    matcher = (
        SinkMatcher(
            context_id,
            on=lambda: lane is not None and lane.is_on("security-sinks"),
            owner=owner,
            owns=owns,
        )
        if request_values
        else None
    )
    built: dict[str, Any] = {
        "processes": lambda: ProcessesSensor(matcher=matcher),
        "files": lambda: FilesSensor(mask_path, own=own, matcher=matcher),
    }
    if matcher is not None:
        built["security-sinks"] = lambda: SecuritySinksSensor(matcher)
    # a switchable sensor is built even when not configured, off: the action may switch it on (BootUI's toggle)
    wanted = [name for name in available if name in configured or name in SWITCHABLE]
    rows = SensorRows()
    lane = SensorLane([built[name]() for name in wanted], TeeSink(sink, rows), audit, configured, rows)
    return lane
