"""Service facade for Side Effects observations."""

from __future__ import annotations

import threading
import time
from typing import Any, cast

from sharpit.engine.collectors.sideeffects import display
from sharpit.engine.collectors.sideeffects.agent_report import (
    LIMITATION_FILES,
    LIMITATION_NETWORK,
    LIMITATION_VALUES,
    agent_dto,
    agent_limitations,
    clamp,
    matching,
    no_match_line,
)
from sharpit.engine.collectors.sideeffects.store import RINGED, SideEffectsStore
from sharpit.engine.sensors.floor import (
    SIDE_EFFECT_SENSORS,
    SIDE_EFFECTS_LIMITATIONS,
    SensorRefusal,
)


class SideEffectsService:
    def __init__(self, capture: Any, masker: Any = None, ready_at: Any = None) -> None:
        self.capture = capture
        self.masker = masker
        self.lock = threading.Lock()
        lane = getattr(capture, "sensors", None)
        self.store = (
            SideEffectsStore(
                lane.rows, display.intake(masker), route_reader=capture.journal.request_routes, ready_at=ready_at
            )
            if lane is not None and masker is not None
            else None
        )
        self._clears = 0
        self._ready_at = ready_at or (lambda: None)

    def report(self) -> dict[str, Any]:
        if self.store is None:
            from sharpit.engine.sensors.floor import side_effects_report

            return side_effects_report()
        with self.lock:
            store = self.store
            store.drain()
            sensors: list[dict[str, object]] = []
            lane = self.capture.sensors
            for sensor_id, group, label in SIDE_EFFECT_SENSORS:
                if sensor_id in RINGED:
                    count, occurrences = store.counts(sensor_id)
                    state, reason = ("recording", None) if lane.is_on(sensor_id) else ("disabled", "The sensor is off.")
                    dropped = lane.rows.dropped(sensor_id)
                else:
                    state, reason, count, occurrences, dropped = (
                        "not-available",
                        "Not available in this version.",
                        0,
                        0,
                        0,
                    )
                sensors.append(
                    {
                        "id": sensor_id,
                        "group": group,
                        "label": label,
                        "state": state,
                        "reason": reason,
                        "rows": count,
                        "occurrences": occurrences,
                        "dropped": dropped,
                        "hooks": [],
                        "toggle": None,
                    }
                )
            return {
                "available": True,
                "unavailableReason": None,
                "sensors": sensors,
                "limitations": self.limitations(
                    folded=store.folded(), cleared=store.clears() > 0, unconfirmed=store.unconfirmed()
                ),
            }

    def sensor(self, sensor_id: str | None, offset: int | None, limit: int | None) -> dict[str, Any]:
        if self.store is None:
            from sharpit.engine.sensors.floor import side_effects_sensor

            return side_effects_sensor(sensor_id, offset, limit)
        wanted = sensor_id.strip() if sensor_id is not None else None
        sensor = next((item for item in SIDE_EFFECT_SENSORS if item[0] == wanted), None)
        if sensor is None:
            known = ", ".join(item[0] for item in SIDE_EFFECT_SENSORS)
            raise SensorRefusal(
                400,
                f"Unknown Side Effects sensor '{'null' if sensor_id is None else sensor_id}'; the sensors are {known}.",
            )
        if wanted is None:
            raise SensorRefusal(
                400,
                "Unknown Side Effects sensor 'null'; the sensors are "
                + ", ".join(s[0] for s in SIDE_EFFECT_SENSORS)
                + ".",
            )
        if (offset is not None and offset < 0) or (limit is not None and limit < 0):
            raise SensorRefusal(400, "offset and limit must not be negative.")
        size = 100 if not limit else min(limit, 500)
        with self.lock:
            store = self.store
            store.drain()
            raw = store.rows_of(wanted) if wanted in RINGED else []
            rows = [display.row_dto(row, self.masker) for row in raw]
            start = offset or 0
            selected = rows[start : start + size]
            summary = self.report_sensor(wanted, sensor)
            return {
                "available": True,
                "unavailableReason": None,
                "sensor": summary,
                "rows": selected,
                "page": {
                    "total": len(rows),
                    "matched": len(rows),
                    "offset": start,
                    "limit": size,
                    "returned": len(selected),
                    "hasMore": start + len(selected) < len(rows),
                },
                "limitations": self.limitations(
                    folded=store.folded(), cleared=store.clears() > 0, unconfirmed=store.unconfirmed()
                ),
            }

    def report_sensor(self, wanted: str, item: tuple[str, str, str]) -> dict[str, Any]:
        lane = self.capture.sensors
        if wanted in RINGED:
            store = cast("SideEffectsStore", self.store)
            count, occurrences = store.counts(wanted)
            state, reason = ("recording", None) if lane.is_on(wanted) else ("disabled", "The sensor is off.")
            dropped = lane.rows.dropped(wanted)
        else:
            state, reason, count, occurrences, dropped = "not-available", "Not available in this version.", 0, 0, 0
        return {
            "id": item[0],
            "group": item[1],
            "label": item[2],
            "state": state,
            "reason": reason,
            "rows": count,
            "occurrences": occurrences,
            "dropped": dropped,
            "hooks": [],
            "toggle": None,
        }

    def limitations(self, **kwargs: Any) -> list[str]:
        sinks = (
            "Security sinks: request input is matched only while SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES is on, "
            "against the current request's query and path parameter values of 4 to 256 characters, at most 32 of "
            "them, never form values, headers, or bodies, and only verbatim: a value encoded, trimmed, or changed "
            "in case is not seen. The values are compared, never stored, and forgotten when the response completes. "
            "A command is checked where the processes sensor sees it start; a file path only with the files sensor; "
            "SQL text and outbound URLs are not checked. Work the request hands off, to a thread, a task, a "
            "background task, or a streamed body, is checked so that its own rows are redacted, but publishes no "
            "security-sinks row: only the request's own endpoint and its dependencies do. A row's target is the "
            "redacted text, the value replaced by the parameter's name; when a text was scanned only in part or "
            "held more matches than could be redacted, no text is kept. A value made of digits only, or one whose "
            "place in the text is not known, is shown once a second request confirms the text varies with it."
        )
        attribution = (
            "A row is attributed to its request's route as HTTP Exchanges names it, else to startup, or to its "
            "thread's family. Work handed to another thread without sharpit's request context shows under its "
            "thread's family."
        )
        lines = [
            SIDE_EFFECTS_LIMITATIONS[0],
            LIMITATION_VALUES,
            LIMITATION_NETWORK,
            LIMITATION_FILES,
            sinks,
            attribution,
        ]
        routes_hidden = kwargs.get("routes_hidden", False)
        folded = kwargs.get("folded", 0)
        cleared = kwargs.get("cleared", False) or self._clears > 0
        holder_enabled = kwargs.get("holder_enabled", False)
        unconfirmed = kwargs.get("unconfirmed", 0)
        if routes_hidden:
            lines.append(
                "HTTP Exchanges is disabled: Side Effects attributes rows to the request's route only while "
                "HTTP Exchanges records; without it, rows are attributed to startup or their thread's family."
            )
        if folded:
            lines.append(
                f"{folded} operation{'s are' if folded != 1 else ' is'} counted in an Other row: a sensor keeps "
                "at most 500 rows and the run 2000."
            )
        if cleared:
            lines.append(
                "The recording was cleared: rows recorded before then were dropped, and so is a record the agent "
                "still held whose first occurrence came before the clear."
            )
        if holder_enabled:
            lines.append("Request-value matching: 0 requests held values, 0 sink checks ran.")
        if unconfirmed:
            lines.append(
                f"{unconfirmed} security-sinks match is not shown yet: a number, or one whose place in the text "
                "is not known may be a word the text always holds, until a second request confirms the text varies "
                "with it."
            )
        return lines

    def ready_at(self) -> int | None:
        return self._ready_at()

    def clear_recording(self) -> None:
        with self.lock:
            if self.store is not None:
                now = time.time_ns() // 1_000_000
                for sensor in RINGED:
                    self.capture.sensors.rows.clear(sensor, now)
                self.store.clear(now)
            self._clears += 1

    def agent_report(self, query: str | None, limit: int | None) -> dict[str, Any]:
        """``SideEffectsService.agentReport``: every sensor's coverage, then the matching rows, most frequent first."""
        asked = (query or "").strip()
        report = self.report()
        sensors = report["sensors"]
        if not report["available"]:
            return agent_dto(False, report["unavailableReason"], asked, sensors, [], 0, [])
        by_sensor = any(sensor["id"] == asked for sensor in sensors)
        with self.lock:
            store = cast("SideEffectsStore", self.store)
            store.drain()
            built = [
                display.row_dto(row, self.masker)
                for sensor_id, _group, _label in SIDE_EFFECT_SENSORS
                if sensor_id in RINGED and (not by_sensor or sensor_id == asked)
                for row in store.rows_of(sensor_id)
            ]
        found = matching(built, asked, by_sensor)
        listed = found[: clamp(limit)]
        shown: set[str] = {str(row["sensor"]) for row in listed}
        if by_sensor:
            shown.add(asked)
        limitations = agent_limitations(report["limitations"], shown)
        if asked and not found:
            limitations.append(no_match_line(asked))
        return agent_dto(True, None, asked, sensors, listed, len(found), limitations)
