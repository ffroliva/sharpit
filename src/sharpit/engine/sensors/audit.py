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

from sharpit.engine.capture.journal import SCALAR_BYTES, JournalSink

_PROCESS_KEYS = ("source", "kind", "target", "requestId", "at", "callSite", "threadName")
_PROCESS_BASE = sum(map(len, _PROCESS_KEYS)) + len("processes") + len("start") + 2 * SCALAR_BYTES
_FILE_KEYS = ("source", "kind", "target", "origin", "location", "requestId", "at", "callSite", "threadName")
_FILE_BASE = sum(map(len, _FILE_KEYS)) + len("files") + len("unknown") + 2 * SCALAR_BYTES
_SINK_KEYS = (
    "source", "kind", "target", "parameter", "numeric", "positionUnknown",
    "callSite", "at", "requestId", "rawHash", "redactedHash",
)  # fmt: skip
_SINK_BASE = sum(map(len, _SINK_KEYS)) + len("security-sinks") + 5 * SCALAR_BYTES


def _sink_row_size(row: Mapping[str, Any]) -> int:
    return (
        _SINK_BASE
        + len(row["kind"])
        + (SCALAR_BYTES if (target := row["target"]) is None else len(target))
        + len(row["parameter"])
        + (SCALAR_BYTES if (site := row["callSite"]) is None else len(site))
        + (SCALAR_BYTES if (req := row["requestId"]) is None else len(req))
    )


def row_size(row: Mapping[str, Any]) -> int:
    """The byte charge ``RuntimeJournal._flat`` computes for a sensor row, without walking its items."""
    source = row.get("source")
    if source == "processes":
        return (
            _PROCESS_BASE
            + len(row["target"])
            + (SCALAR_BYTES if (req := row["requestId"]) is None else len(req))
            + (SCALAR_BYTES if (th := row["threadName"]) is None else len(th))
        )
    if source == "files":
        return (
            _FILE_BASE
            + len(row["kind"])
            + len(row["target"])
            + len(row["location"])
            + (SCALAR_BYTES if (req := row["requestId"]) is None else len(req))
            + (SCALAR_BYTES if (th := row["threadName"]) is None else len(th))
        )
    return _sink_row_size(row) if source == "security-sinks" else 0


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
        try:  # no line of an audit hook runs unguarded: at interpreter shutdown even the thread-local can fail
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
        except Exception:  # noqa: BLE001, S110 - an audit hook must never raise into the host's call
            pass

    @staticmethod
    def _deliver(sub: _Subscription, event: str, args: tuple[Any, ...]) -> None:
        sink = sub.sink()
        if sink is None:
            return  # the context is gone: skipped here, dropped at the next release
        try:
            offer_flat = getattr(sink, "offer_flat", None)  # a sensor's row is flat scalars it never touches again
            if offer_flat is not None:
                for row in sub.sensor.record(event, args):
                    offer_flat(row, row_size(row))
            else:
                offer = sink.offer
                for row in sub.sensor.record(event, args):
                    offer(row)
        except Exception:  # noqa: BLE001, S110 - an audit hook must never raise into the host's call
            pass


hub = AuditHub()
