from __future__ import annotations

import sys
from collections.abc import Callable
from threading import RLock
from typing import Any, cast

TOOL_IDS = (3, 4)


def _clear_callbacks(monitoring: Any, tool_id: int) -> None:
    events = monitoring.events
    if isinstance(events, dict):
        callbacks: dict[tuple[int, int], object] = monitoring.callbacks
        event_ids = {event for owner, event in callbacks if owner == tool_id}
    else:
        event_values = cast(dict[str, object], vars(events))
        event_ids = {value for value in event_values.values() if isinstance(value, int) and value}
    for event in event_ids:
        monitoring.register_callback(tool_id, event, None)


class MonitoringTool:
    def __init__(self, monitoring: Any, tool_id: int, lock: RLock, claimed: set[int]) -> None:
        self.monitoring = monitoring
        self.tool_id = tool_id
        self._lock = lock
        self._claimed = claimed
        self._events: set[int] = set()
        self._released = False

    def on_event(self, event: int, callback: Callable[..., object] | None) -> None:
        with self._lock:
            if not self._released:
                if callback is None:
                    self._events.discard(event)
                else:
                    self._events.add(event)
                self.monitoring.register_callback(self.tool_id, event, callback)

    def listen(self, events: int) -> None:
        with self._lock:
            if not self._released:
                self.monitoring.set_events(self.tool_id, events)

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
            if self.monitoring.get_tool(self.tool_id) != "sharpit":
                self._claimed.discard(self.tool_id)
                return
            errors: list[Exception] = []
            try:
                self.monitoring.set_events(self.tool_id, 0)
            except Exception as error:
                errors.append(error)
            for event in self._events:
                try:
                    self.monitoring.register_callback(self.tool_id, event, None)
                except Exception as error:
                    errors.append(error)
            clear_tool_id = getattr(self.monitoring, "clear_tool_id", None)
            if clear_tool_id is not None:
                try:
                    clear_tool_id(self.tool_id)
                except Exception as error:
                    errors.append(error)
            try:
                self.monitoring.free_tool_id(self.tool_id)
            except Exception as error:
                errors.append(error)
            finally:
                self._claimed.discard(self.tool_id)
            if errors:
                raise errors[0]


class MonitoringToolAllocator:
    def __init__(self, monitoring: Any | None = None) -> None:
        self.monitoring = monitoring if monitoring is not None else getattr(sys, "monitoring", None)
        self._lock = RLock()
        self._claimed: set[int] = set()

    def claim(self) -> MonitoringTool | None:
        if self.monitoring is None:
            return None
        with self._lock:
            for tool_id in TOOL_IDS:
                if tool_id in self._claimed or self.monitoring.get_tool(tool_id) is not None:
                    continue
                try:
                    self.monitoring.use_tool_id(tool_id, "sharpit")
                except ValueError:
                    continue
                try:
                    clear_tool_id = getattr(self.monitoring, "clear_tool_id", None)
                    if clear_tool_id is not None:
                        clear_tool_id(tool_id)
                    else:
                        # shortcut: local events of a previous owner stay set on <3.14 but have no callback; clear_tool_id when 3.14 is the floor  # noqa: E501
                        _clear_callbacks(self.monitoring, tool_id)
                    self.monitoring.set_events(tool_id, 0)
                except BaseException:
                    self.monitoring.free_tool_id(tool_id)
                    raise
                self._claimed.add(tool_id)
                return MonitoringTool(self.monitoring, tool_id, self._lock, self._claimed)
        return None


allocator = MonitoringToolAllocator()
