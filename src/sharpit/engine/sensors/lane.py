"""The sensor lane: which of the process and file sensors a context runs, and how it switches them (W6 lane S3).

Built at install only when ``agent_sensors`` names a sensor this version ships (``processes``, ``files``); with none, no
lane exists and the audit hook is never installed. Each sensor is also a capture-registry entry, so suspending the
registry (idle, low-footprint) switches the sensor off at the hook; detaching (shutdown, ``uninstall_capture``)
unbinds it, leaving the resident hook inert.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sharpit.engine.capture.journal import JournalSink
from sharpit.engine.sensors.audit import AuditHub, Sensor, hub
from sharpit.engine.sensors.files import FilesSensor
from sharpit.engine.sensors.processes import ProcessesSensor

BUILT = ("processes", "files")  # the sensors this version builds
SWITCHABLE = ("files",)  # AgentSensorSettings.SWITCHABLE_SENSORS ∩ BUILT: BootUI keeps the processes sensor always on


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
        """Nothing is held here: rows live in the journal."""


class SensorLane:
    def __init__(self, sensors: list[Sensor], sink: JournalSink, audit: AuditHub = hub) -> None:
        self._sensors = {sensor.name: sensor for sensor in sensors}
        self._sink = sink
        self._hub = audit
        self._paused: set[str] = set()
        self._off: set[str] = set()  # switched off by the action: kept across restarts
        self.attached = False

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._sensors)

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

    def pause(self, name: str) -> None:
        self._paused.add(name)
        self._hub.disable(self._sensors[name])

    def unpause(self, name: str) -> None:
        self._paused.discard(name)
        if self.attached:
            self.attach()

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
            self._hub.disable(self._sensors[name])
        return True


def build_lane(
    configured: tuple[str, ...],
    sink: JournalSink | None,
    mask_path: Callable[[str], str],
    own: tuple[str, ...] = (),
    audit: AuditHub = hub,
) -> SensorLane | None:
    """The lane for ``configured`` sensors, or None: nothing configured, or no journal to offer to."""
    wanted = [name for name in BUILT if name in configured]
    if not wanted or sink is None:
        return None
    built: dict[str, Any] = {"processes": ProcessesSensor, "files": lambda: FilesSensor(mask_path, own=own)}
    return SensorLane([built[name]() for name in wanted], sink, audit)
