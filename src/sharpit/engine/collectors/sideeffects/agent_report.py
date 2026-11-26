"""The Side Effects report an agent reads (``SideEffectsService.agentReport`` of BootUI)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# SideEffectsService.LIMITATION_VALUES, _NETWORK and _FILES, BootUI -> sharpit (see the adaptation table, F11)
LIMITATION_VALUES = (
    "A process row shows the command's file name only, never its arguments or its environment, which can hold "
    "secrets. A process row records the start only: its exit status and lifetime are not recorded."
)
LIMITATION_NETWORK = "A network row shows a host and port, never a byte sent or received, nor a URL's path or query."
LIMITATION_FILES = (
    "Files: the interpreter's own files (imports) and sharpit's own state are counted, not recorded per route. "
    "A call site's frames are read once per run and file pattern, so two call sites of one pattern share the "
    "first one's. A file opened without an audit event, as native code may, is not seen. A move or a copy "
    "records its source and its destination."
)
LIMITATION_AGENT_OMITTED = "What the rows of a sensor without listed rows cannot see is left out: query its id for it."
# SideEffectsService.LIMITATION_SENSORS: the sensors whose rows each fixed limitation describes; the others apply to all
LIMITATION_SENSORS: Mapping[str, frozenset[str]] = {
    LIMITATION_VALUES: frozenset({"processes", "files", "environment"}),
    LIMITATION_NETWORK: frozenset({"network"}),
    LIMITATION_FILES: frozenset({"files"}),
}
DEFAULT_LIMIT, MAX_LIMIT = 20, 500  # SideEffectsAgentReport.DEFAULT_LIMIT, SideEffectsService.MAX_LIMIT
_REQUEST_ID = re.compile(r"[0-9a-f]{16}")
# SideEffectsService.matches: the fields of a built row DTO a query is compared with, never ``detail``
_SEARCHED = ("attribution", "target", "parameter", "kind", "callSite", "insideMethod", "sensor", "client")


def agent_limitations(limitations: Sequence[str], shown: set[str]) -> list[str]:
    """Those of this run and those every row shares, and a fixed line only for the sensors in ``shown``."""
    kept = [line for line in limitations if line not in LIMITATION_SENSORS or LIMITATION_SENSORS[line] & shown]
    return [*kept, LIMITATION_AGENT_OMITTED] if len(kept) < len(limitations) else kept


def _matches(row: Mapping[str, Any], needle: str) -> bool:
    return any(needle in str(row[key]).lower() for key in _SEARCHED if row[key] is not None) or any(
        needle == str(request_id).lower() for request_id in row["exemplarRequestIds"]
    )


def matching(rows: Iterable[Mapping[str, Any]], asked: str, by_sensor: bool) -> list[Mapping[str, Any]]:
    needle = asked.lower()
    found = [row for row in rows if by_sensor or not needle or _matches(row, needle)]
    return sorted(found, key=lambda row: row["count"] + row["completed"], reverse=True)


def clamp(limit: int | None) -> int:
    return DEFAULT_LIMIT if limit is None or limit <= 0 else min(limit, MAX_LIMIT)


def no_match_line(asked: str) -> str:
    clause = (
        " A request id matches only the rows naming it among their exemplar requests, at most three each."
        if _REQUEST_ID.fullmatch(asked.lower())
        else ""
    )
    return f'No row matched "{asked}": call get_side_effects without a query to list them.{clause}'


def agent_dto(
    available: bool,
    reason: str | None,
    asked: str,
    sensors: list[dict[str, Any]],
    listed: Sequence[Mapping[str, Any]],
    matched: int,
    limitations: list[str],
) -> dict[str, Any]:
    """``SideEffectsAgentReport``, keys in BootUI's order."""
    return {
        "available": available,
        "unavailableReason": reason,
        "query": asked,
        "sensors": sensors,
        "matched": matched,
        "rows": list(listed),
        "omitted": matched - len(listed),
        "limitations": limitations,
    }
