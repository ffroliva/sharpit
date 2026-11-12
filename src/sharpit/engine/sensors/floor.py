"""The W6 floor: every agent-sensor panel answers BootUI's shape, unavailable, with BootUI's reason.

sharpit has no agent sensors yet (S3 to S5 build them), so each read below is BootUI's "without the agent" DTO
(``JavaAgentService``, ``CodePathsService``, ``CodeInventoryService``, ``SideEffectsService``, ``MethodProbeService``)
and each action is BootUI's refusal. Nothing here reads host state: no read opens, hooks or changes anything.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, cast

from sharpit import __version__

# JavaAgentService.NOT_ATTACHED_REASON, BootUI -> sharpit and JVM -> process; this version ships no agent to attach
NOT_ATTACHED_REASON = (
    "This process runs without the sharpit agent. sharpit works without it; this version does not ship the agent's"
    " sensors yet."
)
_SEE_PANEL = " See the Java Agent panel."
# JavaAgentService.*_REQUIREMENT, BootUI -> sharpit
INVENTORY_REQUIREMENT = "Requires the sharpit agent's inventory sensor"
CODE_PATHS_REQUIREMENT = "Requires the sharpit agent's code-paths sensor"
SIDE_EFFECTS_REQUIREMENT = "Requires the sharpit agent"

INVENTORY_REASON = f"{INVENTORY_REQUIREMENT}: {NOT_ATTACHED_REASON}{_SEE_PANEL}"
CODE_PATHS_REASON = f"{CODE_PATHS_REQUIREMENT}: {NOT_ATTACHED_REASON}{_SEE_PANEL}"
SIDE_EFFECTS_REASON = f"{SIDE_EFFECTS_REQUIREMENT}: {NOT_ATTACHED_REASON}{_SEE_PANEL}"

# Panel id -> why it is unavailable (BootUI: the panel is unavailable with the Java Agent panel's reason)
PANEL_REASONS: dict[str, str] = {
    "code-inventory": INVENTORY_REASON,
    "code-paths": CODE_PATHS_REASON,
    "side-effects": SIDE_EFFECTS_REASON,
}
# JavaAgentPresence.AGENT_SENSOR_TOOLS: advertised only while the agent's sensor records, so never here; name -> panel
AGENT_SENSOR_TOOLS: dict[str, str] = {
    "get_code_inventory": "code-inventory",
    "get_code_paths": "code-paths",
    "start_method_probe": "code-paths",
    "get_method_probe": "code-paths",
    "get_side_effects": "side-effects",
}
# AgentSensorSettings.SWITCHABLE_SENSORS
SWITCHABLE_SENSORS = ("threads", "files", "environment", "thread-activity", "thread-locals", "security-sinks")
_THREADS_AND_LEAKS = "Threads and leaks"
# SideEffectsCatalog.SENSORS, in tab order: (id, group, label)
SIDE_EFFECT_SENSORS = (
    ("network", "Network", "Hosts the application connects to"),
    ("files", "Files and processes", "Files the application reads and writes"),
    ("processes", "Files and processes", "Processes the application starts"),
    ("environment", "Environment", "Environment variables and system properties read"),
    ("thread-activity", _THREADS_AND_LEAKS, "Threads and executors started per route"),
    ("thread-locals", _THREADS_AND_LEAKS, "Thread locals left set after a request"),
    ("resources", _THREADS_AND_LEAKS, "Streams, channels, and sockets left open"),
    ("blocking", "Blocking", "Blocking calls started on an event loop"),
    (
        "security-sinks",
        "Security sinks",
        "Request input reaching SQL, commands, file paths, and URLs; deserialization without a filter, weak"
        " algorithms, and trust managers",
    ),
)
# SideEffectsService.LIMITATION_SCOPE, _VALUES, _NETWORK: the minimisation the sensors will keep, BootUI -> sharpit
SIDE_EFFECTS_LIMITATIONS = (
    "Side Effects records only what the sharpit agent's side-effect sensors hook.",
    "A process row shows the command's file name only, never its arguments or its environment, which can hold"
    " secrets. A file row shows a path pattern, never the file's contents. An environment row shows the name read,"
    " never its value or a default.",
    "A network row shows a host and port, never a byte sent or received, nor a URL's path or query.",
)
# MethodProbeService.LIMITATION_METADATA, _BOUNDS, _CALLER, BootUI -> sharpit (no JVM, no instrumentation)
PROBE_LIMITATIONS = (
    "A probe records each invocation's duration, thread kind, request id, outcome (returned, or the thrown"
    " exception's type), and calling frame: never an argument or a return value.",
    "A probe records at most 20 invocations, for at most 60 seconds, five probes at once, and ends with the run (a"
    " restart or a reload).",
    "The calling frame is the first frame of the application's packages above the method, past wrappers and"
    " decorators, else the frame right above it.",
)
# McpToolGuide.ID_SOURCES for the sensor switches, BootUI -> sharpit
SENSOR_ID_SOURCE = (
    "a switchable sharpit agent sensor id (threads, files, environment, thread-activity, thread-locals, or"
    " security-sinks)"
)
ID_SOURCES = {"enable_agent_sensor": SENSOR_ID_SOURCE, "disable_agent_sensor": SENSOR_ID_SOURCE}
# Sonar S1192: the keys every unavailable DTO repeats
AVAILABLE, UNAVAILABLE_REASON, LIMITATIONS = "available", "unavailableReason", "limitations"
_JAVA_LONG = re.compile(r"[+-]?\d+")  # Long.parseLong: an optional sign and decimal digits (Character.digit)
_LONG_MIN, _LONG_MAX = -(2**63), 2**63 - 1
_JAVA_TRIM = "".join(map(chr, range(33)))  # String.trim: every char up to U+0020
# CodePathsService / SideEffectsService / MethodProbeService bounds
CODE_PATHS_DEFAULT_LIMIT, CODE_PATHS_MAX_LIMIT, CODE_PATHS_DEFAULT_DEPTH, CODE_PATHS_MAX_DEPTH = 200, 500, 8, 33
SIDE_EFFECTS_DEFAULT_LIMIT, SIDE_EFFECTS_MAX_LIMIT = 100, 500
PROBE_MAX_ACTIVE, PROBE_MAX_INVOCATIONS, PROBE_WINDOW_SECONDS = 5, 20, 60
EXPECTED_PROTOCOL = 1


class SensorRefusal(Exception):
    """A BootUI refusal: ``status`` is the HTTP status (400, 404 or 409), ``message`` the ``error`` text."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def body_field(raw: bytes, name: str) -> object:
    """``name`` of a JSON object body; None for an empty, unparsable or non-object body (Spring's absent request)."""
    try:
        body: object = json.loads(raw) if raw.strip() else None
    except (ValueError, RecursionError):
        return None
    return cast("dict[str, object]", body).get(name) if isinstance(body, dict) else None


def _page(limit: int) -> dict[str, Any]:
    return {"total": 0, "matched": 0, "offset": 0, "limit": limit, "returned": 0, "hasMore": False}


def _empty_page(limit: int | None) -> dict[str, Any]:
    """CodeInventoryService.emptyPage."""
    return _page(0 if limit is None else max(0, limit))


def java_agent_report() -> dict[str, Any]:
    """``JavaAgentReport`` in state NOT_ATTACHED: no claim, no sensors, nothing to attach."""
    return {
        "state": "NOT_ATTACHED",
        "reason": NOT_ATTACHED_REASON,
        "agentVersion": None,
        "bootUiVersion": __version__,
        "protocol": None,
        "expectedProtocol": EXPECTED_PROTOCOL,
        "jdk": f"{sys.version.split()[0]} ({sys.implementation.name})",
        "loadMode": None,
        "jarPath": None,
        "startupMicros": None,
        "claim": None,
        "heldBy": None,
        "sensors": [],
        "toggles": [],
        "retransformation": None,
        "counters": None,
        "messages": [],
        "warnings": [],
        "setup": {"jarPath": None, "jarFound": False, "buildTool": "UNKNOWN", "snippets": []},
    }


def switch_sensor(sensor_id: str, enabled: object) -> dict[str, Any]:
    """``JavaAgentController.switchSensor``: 400 without ``enabled`` or for an unswitchable id, else 409 not armed."""
    if not isinstance(enabled, bool):
        raise SensorRefusal(400, 'The request body must say {"enabled": true} or {"enabled": false}.')
    return switch_sensor_for_agents(sensor_id)


def switch_sensor_for_agents(sensor_id: str) -> dict[str, Any]:
    """``JavaAgentService.switchSensor``: never switches here, the agent is not attached."""
    if sensor_id.strip() not in SWITCHABLE_SENSORS:
        raise SensorRefusal(
            400,
            f"'{sensor_id}' cannot be switched at run time: the sensors switched at run time are "
            f"{', '.join(SWITCHABLE_SENSORS)}.",
        )
    raise SensorRefusal(
        409,
        "The sharpit agent is not armed for this application, so its sensors cannot be switched: "
        + NOT_ATTACHED_REASON,
    )


def code_inventory_report() -> dict[str, Any]:
    """``CodeInventoryReport.unavailable``."""
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: INVENTORY_REASON,
        "run": None,
        "scan": None,
        "methods": None,
        "changes": None,
        "dependencies": None,
        LIMITATIONS: [],
        "recordingClearedAt": None,
    }


def code_inventory_changes(limit: int | None) -> dict[str, Any]:
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: INVENTORY_REASON,
        "counts": None,
        "changes": [],
        "page": _empty_page(limit),
    }


def code_inventory_methods(limit: int | None) -> dict[str, Any]:
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: INVENTORY_REASON,
        "packages": [],
        "classes": [],
        "methods": [],
        "page": _empty_page(limit),
    }


def code_inventory_dependencies(limit: int | None) -> dict[str, Any]:
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: INVENTORY_REASON,
        "counts": None,
        "dependencies": [],
        "page": _empty_page(limit),
    }


def code_paths_report() -> dict[str, Any]:
    """``CodePathsReport.unavailable``."""
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: CODE_PATHS_REASON,
        "status": None,
        "routes": [],
        "excludedMethods": [],
        LIMITATIONS: [],
    }


def code_paths_route(route: str | None, depth: int | None, limit: int | None) -> dict[str, Any]:
    """``CodePathsRouteTreeReport.empty(false, reason, route, depth, limit)`` with BootUI's bounds applied."""
    max_depth = CODE_PATHS_DEFAULT_DEPTH if depth is None or depth < 0 else min(depth, CODE_PATHS_MAX_DEPTH)
    size = CODE_PATHS_DEFAULT_LIMIT if limit is None or limit <= 0 else min(limit, CODE_PATHS_MAX_LIMIT)
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: CODE_PATHS_REASON,
        "route": route,
        "found": False,
        "assemblyOnly": False,
        "warmRequests": 0,
        "firstRequestMillis": None,
        "firstRequestId": None,
        "ownMillis": 0.0,
        "handlerMillis": None,
        "shareOf": "handler",
        "depth": max_depth,
        "nodes": [],
        "methods": [],
        "exemplarRequestIds": [],
        "page": _page(size),
        LIMITATIONS: [],
    }


def code_paths_beans() -> dict[str, Any]:
    """``CodePathsBeansReport.unavailable``."""
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: CODE_PATHS_REASON,
        "beansAvailable": False,
        "edges": [],
        "observedEdges": 0,
        "declaredEdges": 0,
        "notCalled": 0,
        "omitted": 0,
        LIMITATIONS: [],
    }


def code_paths_request(request_id: str) -> dict[str, Any]:
    """``CodePathsRequestTreeReport.empty(false, reason, requestId)``."""
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: CODE_PATHS_REASON,
        "requestId": request_id,
        "found": False,
        "route": None,
        "assemblyOnly": False,
        "ownMillis": 0.0,
        "asyncMillis": 0.0,
        "cut": False,
        "droppedCalls": 0,
        "nodes": [],
        "topMethods": [],
        LIMITATIONS: [],
    }


def code_paths_probes() -> dict[str, Any]:
    """``CodePathsProbesReport`` without the agent: no probes, shapes unavailable for the same reason."""
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: CODE_PATHS_REASON,
        "maxActive": PROBE_MAX_ACTIVE,
        "maxInvocations": PROBE_MAX_INVOCATIONS,
        "windowSeconds": PROBE_WINDOW_SECONDS,
        "probes": [],
        LIMITATIONS: list(PROBE_LIMITATIONS),
        "shapesAvailable": False,
        "shapesUnavailableReason": CODE_PATHS_REASON,
    }


def start_probe(method: object) -> dict[str, Any]:
    """``MethodProbeService.start``: 400 without a method, else 409 with Code Paths' reason."""
    if not isinstance(method, str) or not method.strip():
        raise SensorRefusal(400, "Name the method to probe, as com.example.PriceService#quote.")
    raise SensorRefusal(409, CODE_PATHS_REASON)


def _parse_probe_id(probe_id: str) -> int:
    """``MethodProbeService.parseId``: ``Long.parseLong(id.trim())``, else 400."""
    trimmed = probe_id.strip(_JAVA_TRIM)
    value = int(trimmed) if _JAVA_LONG.fullmatch(trimmed) else None
    if value is None or not _LONG_MIN <= value <= _LONG_MAX:
        raise SensorRefusal(400, f"A method probe id is a number, as get_method_probe returns it: {probe_id}")
    return value


def stop_probe(probe_id: str) -> dict[str, Any]:
    """``MethodProbeService.stop`` (and DELETE, and ``probe`` for GET): 400 for a non-number id, else 404, this run
    has no probes (the panel is shown, so ``probe`` reaches the run lookup)."""
    _parse_probe_id(probe_id)
    raise SensorRefusal(404, f"This run has no method probe {probe_id}.")


def _side_effect_sensor(sensor_id: str, group: str, label: str) -> dict[str, Any]:
    return {
        "id": sensor_id,
        "group": group,
        "label": label,
        "state": "unavailable",
        "reason": SIDE_EFFECTS_REASON,
        "rows": 0,
        "occurrences": 0,
        "dropped": 0,
        "hooks": [],
        "toggle": None,
    }


def side_effects_report() -> dict[str, Any]:
    """``SideEffectsReport`` without the agent: every sensor listed, unavailable with the Java Agent panel's reason."""
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: SIDE_EFFECTS_REASON,
        "sensors": [_side_effect_sensor(*sensor) for sensor in SIDE_EFFECT_SENSORS],
        LIMITATIONS: list(SIDE_EFFECTS_LIMITATIONS),
    }


def side_effects_sensor(sensor_id: str | None, offset: int | None, limit: int | None) -> dict[str, Any]:
    """``SideEffectsService.sensor``: 400 for an unknown sensor or a negative offset or limit."""
    wanted = None if sensor_id is None else sensor_id.strip()
    sensor = next((s for s in SIDE_EFFECT_SENSORS if s[0] == wanted), None)
    if sensor is None:
        known = ", ".join(s[0] for s in SIDE_EFFECT_SENSORS)
        shown = "null" if sensor_id is None else sensor_id  # Java's string concatenation of a null id
        raise SensorRefusal(400, f"Unknown Side Effects sensor '{shown}'; the sensors are {known}.")
    if (offset is not None and offset < 0) or (limit is not None and limit < 0):
        raise SensorRefusal(400, "offset and limit must not be negative.")
    size = SIDE_EFFECTS_DEFAULT_LIMIT if not limit else min(limit, SIDE_EFFECTS_MAX_LIMIT)
    return {
        AVAILABLE: False,
        UNAVAILABLE_REASON: SIDE_EFFECTS_REASON,
        "sensor": _side_effect_sensor(*sensor),
        "rows": [],
        "page": _page(size),
        LIMITATIONS: list(SIDE_EFFECTS_LIMITATIONS),
    }
