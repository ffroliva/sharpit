"""Service facade for Side Effects observations."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
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

# SideEffectsService.holderLine (SV:1772-1790): after the two fixed counts, each skip only when it happened
_HOLDER_SKIPS = (
    ("valuesTooLong", " values longer than 256 characters were not held."),
    ("valuesOverCount", " values past 32 in a request were not held."),
    ("tableFull", " requests held nothing: 128 requests held values already."),
    ("stopped", " requests reached their matching budget: later sinks were not checked."),
    ("partial", " texts were checked in their first 16 KB only."),
    ("busy", " checks were skipped while another check of the same request ran."),
    ("notKept", " targets or names were not kept: too many distinct ones in this run."),
    ("dropped", " matches were dropped: the agent's ring was full."),
)


SINKS_OFF_REASON = (
    "Request-value matching is off: set SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true and restart the application "
    "to check whether request input reaches a command or a file path."
)


def _sinks_reason(processes: bool, files: bool) -> str:
    """JavaAgentService.securitySinksCoverage (JavaAgentService.java:289-336), adapted to the two sinks (F1, F2)."""
    if not processes and not files:
        return "Checks no sink: the processes and files sensors are off."
    if not processes:
        return "Checks file paths through the files sensor; not commands: the processes sensor is off."
    if not files:
        return "Checks commands through the processes sensor; not file paths: the files sensor is off."
    return "Checks commands through the processes sensor; file paths through the files sensor."


def holder_line(holder: Mapping[str, int]) -> str:
    line = f"Request-value matching: {holder.get('requests', 0)} requests held values, "
    line += f"{holder.get('checks', 0)} sink checks ran."
    return line + "".join(f" {holder[key]}{text}" for key, text in _HOLDER_SKIPS if holder.get(key, 0) > 0)


class SideEffectsService:
    def __init__(
        self,
        capture: Any,
        masker: Any = None,
        ready_at: Any = None,
        exchanges_enabled: Callable[[], bool] = lambda: True,
    ) -> None:
        self.capture = capture
        self._exchanges_enabled = exchanges_enabled
        self.masker = masker
        self.lock = threading.Lock()
        lane = getattr(capture, "sensors", None)
        self.store = (
            SideEffectsStore(
                lane.rows,
                display.intake(masker),
                route_reader=capture.journal.request_routes,
                ready_at=ready_at,
                routes_hidden=self._routes_hidden,
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
            return self._report_locked(self.store)

    def _report_locked(self, store: SideEffectsStore) -> dict[str, Any]:
        """One drain, then the counts and limitations of that drain: the caller holds ``self.lock``."""
        store.drain()
        sensors: list[dict[str, object]] = []
        lane = self.capture.sensors
        for sensor_id, group, label in SIDE_EFFECT_SENSORS:
            if sensor_id in RINGED:
                count, occurrences = store.counts(sensor_id)
                state, reason = self._state(sensor_id)
                dropped = lane.rows.dropped(sensor_id) + store.dropped(sensor_id)
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
                folded=store.folded(),
                cleared=store.clears() > 0,
                unconfirmed=store.unconfirmed(),
                holder=self._holder(),
                routes_hidden=self._routes_hidden(),
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
                    folded=store.folded(),
                    cleared=store.clears() > 0,
                    unconfirmed=store.unconfirmed(),
                    holder=self._holder(),
                    routes_hidden=self._routes_hidden(),
                ),
            }

    def report_sensor(self, wanted: str, item: tuple[str, str, str]) -> dict[str, Any]:
        lane = self.capture.sensors
        if wanted in RINGED:
            store = cast("SideEffectsStore", self.store)
            count, occurrences = store.counts(wanted)
            state, reason = self._state(wanted)
            dropped = lane.rows.dropped(wanted) + store.dropped(wanted)
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

    def _routes_hidden(self) -> bool:
        """BootUI's ``!read.requests()``: route rows cannot be named while HTTP Exchanges does not record."""
        accepts = getattr(self.capture.journal, "accepts", None)
        return not self._exchanges_enabled() or (accepts is not None and not accepts("http"))

    def _state(self, sensor_id: str) -> tuple[str, str | None]:
        lane = self.capture.sensors
        if sensor_id == "security-sinks" and lane.is_on(sensor_id):
            return "recording", _sinks_reason(lane.is_on("processes"), lane.is_on("files"))
        if lane.is_on(sensor_id):
            return "recording", None
        if sensor_id == "security-sinks" and self._holder() is None:
            return "disabled", SINKS_OFF_REASON
        return "disabled", "The sensor is off."

    def _holder(self) -> dict[str, int] | None:
        """The request-value holder's counters; None while the setting is off (the lane then has no such sensor)."""
        lane = self.capture.sensors
        status = lane.holder_status()
        if status is None:
            return None
        return {**status, "dropped": lane.rows.dropped("security-sinks")}

    def limitations(self, **kwargs: Any) -> list[str]:
        sinks = (
            "Security sinks: request input is matched only while SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES is on, "
            "against the current request's query and path parameter values of 4 to 256 characters, at most 32 of "
            "them, never form values, headers, or bodies, and only verbatim: a value encoded, trimmed, or changed "
            "in case is not seen. The values are compared, never stored, and forgotten when the response completes. "
            "A command is checked where the processes sensor sees it start; a file path only with the files sensor; "
            "SQL text and outbound URLs are not checked. Work the request hands off, to a thread, a task, a "
            "background task, or a streamed body, is checked only while the request is live: work that runs after "
            "the response completes, or after 60 seconds, is not checked and its rows keep the raw text. Hand-off "
            "work publishes no security-sinks row: only the request's own endpoint and its dependencies do. A row's "
            "target is the redacted text, the value replaced by the parameter's name; when a text was scanned only in "
            "part or held more matches than could be redacted, no text is kept. A value made of digits only, or one "
            "whose place in the text is not known, is shown once a second request confirms the text varies with it."
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
        holder = kwargs.get("holder")
        holder_enabled = kwargs.get("holder_enabled", False) or holder is not None
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
            lines.append(holder_line(holder or {}))
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
        if self.store is None:
            report = self.report()
            return agent_dto(False, report["unavailableReason"], asked, report["sensors"], [], 0, [])
        with self.lock:  # counts and rows of one drain, so a row arriving between them cannot disagree
            store = self.store
            report = self._report_locked(store)
            sensors = report["sensors"]
            by_sensor = any(sensor["id"] == asked for sensor in sensors)
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
