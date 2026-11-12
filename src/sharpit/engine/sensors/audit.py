"""STUB for the red commit: a hub that never installs, binds or dispatches. Replaced by the feat commit."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol

from sharpit.engine.capture.journal import JournalSink


class Sensor(Protocol):
    name: str
    events: tuple[str, ...]

    def record(self, event: str, args: tuple[Any, ...]) -> Iterable[Mapping[str, object]]: ...


class AuditHub:
    def __init__(self, add_hook: Callable[[Callable[[str, tuple[Any, ...]], None]], None] | None = None) -> None:
        self._add_hook = add_hook
        self._installed = False

    @property
    def installed(self) -> bool:
        return self._installed

    def enable(self, sensor: Sensor, sink: JournalSink) -> None:
        del sensor, sink

    def disable(self, sensor: Sensor) -> bool:
        del sensor
        return False

    def is_on(self, sensor: Sensor) -> bool:
        del sensor
        return False

    def release(self, sensor: Sensor | None = None) -> None:
        del sensor


hub = AuditHub()
