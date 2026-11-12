"""The resident audit hook (W6 lane S3): one ``sys.addaudithook`` dispatcher a process can never remove.

It is installed on the first ``enable`` and never before, so a process that configures no sensor has no hook. It stays
installed after ``release``: with nothing subscribed it does a dict lookup and returns. A subscription holds its sink
weakly, so a dropped context is not kept alive by the hook. The dispatcher never raises, never re-enters (an event
fired from inside a sensor or a sink is ignored on that thread) and never logs.
"""

from __future__ import annotations

import sys
import threading
import weakref
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol

from sharpit.engine.capture.journal import JournalSink


class Sensor(Protocol):
    name: str
    events: tuple[str, ...]

    def record(self, event: str, args: tuple[Any, ...]) -> Iterable[Mapping[str, object]]: ...


class _Subscription:
    __slots__ = ("on", "sensor", "sink")

    def __init__(self, sensor: Sensor, sink: JournalSink) -> None:
        self.sensor = sensor
        self.sink = weakref.ref(sink)
        self.on = True


class AuditHub:
    def __init__(self, add_hook: Callable[[Callable[[str, tuple[Any, ...]], None]], None] | None = None) -> None:
        self._add_hook = add_hook
        self._installed = False
        self._subs: dict[int, _Subscription] = {}  # by id(sensor): a sensor is subscribed once
        self._by_event: dict[str, tuple[_Subscription, ...]] = {}  # rebuilt on change; the hook only reads it
        self._lock = threading.Lock()
        self._busy = threading.local()

    @property
    def installed(self) -> bool:
        return self._installed

    def enable(self, sensor: Sensor, sink: JournalSink) -> None:
        with self._lock:
            self._subs[id(sensor)] = _Subscription(sensor, sink)
            self._rebuild()
            if not self._installed:
                (self._add_hook or sys.addaudithook)(self._dispatch)
                self._installed = True

    def disable(self, sensor: Sensor) -> bool:
        """Switch ``sensor`` off, keeping nothing but the flag test per event; False when it was not on."""
        with self._lock:
            sub = self._subs.pop(id(sensor), None)
            self._rebuild()
            return sub is not None

    def is_on(self, sensor: Sensor) -> bool:
        sub = self._subs.get(id(sensor))
        return sub is not None and sub.sink() is not None

    def release(self, sensor: Sensor | None = None) -> None:
        """Drop one sensor's subscription, or every one; the dispatcher stays installed, inert."""
        if sensor is not None:
            self.disable(sensor)
            return
        with self._lock:
            self._subs.clear()
            self._rebuild()

    def _rebuild(self) -> None:
        by_event: dict[str, list[_Subscription]] = {}
        for sub in self._subs.values():
            for event in sub.sensor.events:
                by_event.setdefault(event, []).append(sub)
        self._by_event = {event: tuple(subs) for event, subs in by_event.items()}

    def _dispatch(self, event: str, args: tuple[Any, ...]) -> None:
        subs = self._by_event.get(event)
        if subs is None:
            return
        busy = self._busy
        if getattr(busy, "active", False):
            return
        busy.active = True
        try:
            for sub in subs:
                self._deliver(sub, event, args)
        finally:
            busy.active = False

    @staticmethod
    def _deliver(sub: _Subscription, event: str, args: tuple[Any, ...]) -> None:
        sink = sub.sink()
        if sink is None:
            return  # the context is gone: skipped here, dropped at the next release
        try:
            offer = getattr(sink, "offer_flat", sink.offer)  # a sensor's row is flat scalars it never touches again
            for row in sub.sensor.record(event, args):
                offer(row)
        except BaseException:  # noqa: BLE001, S110 - an audit hook must never raise into the host's call
            pass


hub = AuditHub()
