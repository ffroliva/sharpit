"""W6 floor: the agent-sensor panels answer BootUI's shape, unavailable with BootUI's reason, and refuse its actions.

sharpit ships no agent sensors yet, so every read is BootUI's "without the agent" answer and every action BootUI's
refusal (AbstractBootUiApiConformanceTest: codeInventory/codePaths/sideEffects ...WithoutTheAgent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.guard import PANEL_ACCESS_DENIED
from sharpit.engine.panels import read_only_reason

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api"
GOLDENS = Path(__file__).resolve().parents[1] / "fixtures" / "bootui" / "2.3.0"
INVENTORY = "Requires the sharpit agent's inventory sensor: "
CODE_PATHS = "Requires the sharpit agent's code-paths sensor: "
SIDE_EFFECTS = "Requires the sharpit agent: "
SENSORS = [
    "network",
    "files",
    "processes",
    "environment",
    "thread-activity",
    "thread-locals",
    "resources",
    "blocking",
    "security-sinks",
]
# (route, golden, reason prefix): every W6 read with a BootUI 2.3.0 golden
READS = [
    ("/code-inventory", "code-inventory/captured.json", INVENTORY),
    ("/code-inventory/changes", "code-inventory/changes.captured.json", INVENTORY),
    ("/code-inventory/methods?status=never-executed", "code-inventory/methods.captured.json", INVENTORY),
    ("/code-inventory/dependencies", "code-inventory/dependencies.captured.json", INVENTORY),
    ("/code-paths", "code-paths/captured.json", CODE_PATHS),
    ("/code-paths/route?route=GET%20%2Fnot-a-route", "code-paths/route.captured.json", CODE_PATHS),
    ("/code-paths/beans", "code-paths/beans.captured.json", CODE_PATHS),
    ("/code-paths/probes", "code-paths/probes.captured.json", CODE_PATHS),
    ("/side-effects", "side-effects/captured.json", SIDE_EFFECTS),
]


def _client(**options: Any) -> TestClient:
    app = FastAPI()
    install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _golden(name: str) -> dict[str, Any]:
    return json.loads((GOLDENS / name).read_text(encoding="utf-8"))


def _keys(value: Any) -> Any:
    """The key tree of a DTO: dict keys, recursively; list items by their first element."""
    if isinstance(value, dict):
        return {key: _keys(child) for key, child in value.items()}
    if isinstance(value, list) and value:
        return [_keys(value[0])]
    return None


def test_panels_list_the_sensor_panels_unavailable_with_the_java_agent_reason() -> None:
    # ported: AbstractBootUiApiConformanceTest.codeInventoryIsUnavailableWithTheJavaAgentReasonWithoutTheAgent
    # ported: AbstractBootUiApiConformanceTest.codePathsIsUnavailableWithTheJavaAgentReasonWithoutTheAgent
    # ported: AbstractBootUiApiConformanceTest.sideEffectsIsUnavailableWithTheJavaAgentReasonWithoutTheAgent
    panels = {p["id"]: p for p in _client().get(f"{API}/panels").json()["panels"]}
    assert {"java-agent", "code-inventory", "code-paths", "side-effects"} <= set(panels)
    assert panels["java-agent"]["available"] is True
    assert panels["code-inventory"]["available"] is False
    assert panels["code-inventory"]["unavailableReason"].startswith(INVENTORY)
    assert panels["code-paths"]["available"] is False
    assert panels["code-paths"]["unavailableReason"].startswith(CODE_PATHS)
    assert panels["side-effects"]["available"] is False
    assert panels["side-effects"]["unavailableReason"].startswith(SIDE_EFFECTS)


@pytest.mark.parametrize(("route", "golden", "prefix"), READS, ids=[r[1] for r in READS])
def test_read_answers_bootui_shape_unavailable(route: str, golden: str, prefix: str) -> None:
    # ported: CodePathsServiceTests.withoutTheSensorEveryReadAnswersItsUnavailableShape
    # ported: CodeInventoryServiceTests.isUnavailableWithTheAgentsReason
    # ported: SideEffectsServiceTests.withoutTheAgentEveryReadIsUnavailableWithItsReason
    resp = _client().get(API + route)
    assert resp.status_code == 200, f"{route} returned HTTP {resp.status_code}"
    body = resp.json()
    expected = _golden(golden)
    assert list(body) == list(expected)
    assert _keys(body) == _keys(expected)
    assert body["available"] is False
    assert body["unavailableReason"].startswith(prefix)


def test_java_agent_report_is_not_attached_with_bootui_keys() -> None:
    # ported: JavaAgentControllerTests.servesTheReportWithItsSetupSnippetsWithoutTheAgent
    resp = _client().get(f"{API}/java-agent")
    assert resp.status_code == 200
    body = resp.json()
    assert list(body) == list(_golden("java-agent/captured.json"))
    assert body["state"] == "NOT_ATTACHED"
    assert body["reason"].startswith("This process runs without the sharpit agent.")
    assert body["sensors"] == []
    assert body["claim"] is None
    assert list(body["setup"]) == ["jarPath", "jarFound", "buildTool", "snippets"]


def test_side_effects_lists_every_sensor_unavailable() -> None:
    # ported: AbstractBootUiApiConformanceTest.sideEffectsIsUnavailableWithTheJavaAgentReasonWithoutTheAgent
    resp = _client().get(f"{API}/side-effects")
    assert resp.status_code == 200
    sensors = resp.json()["sensors"]
    assert [s["id"] for s in sensors] == SENSORS
    assert {s["state"] for s in sensors} == {"unavailable"}
    assert all(s["reason"].startswith(SIDE_EFFECTS) for s in sensors)


def test_side_effects_sensor_answers_its_shape() -> None:
    resp = _client().get(f"{API}/side-effects/sensor?sensor=processes")
    assert resp.status_code == 200
    body = resp.json()
    assert list(body) == ["available", "unavailableReason", "sensor", "rows", "page", "limitations"]
    assert body["sensor"]["id"] == "processes"
    assert body["sensor"]["state"] == "unavailable"
    assert body["rows"] == []
    assert body["page"]["limit"] == 100


@pytest.mark.parametrize("query", ["?sensor=not-a-sensor", ""], ids=["unknown", "missing"])
def test_side_effects_unknown_sensor_is_400(query: str) -> None:
    # ported: SideEffectsServiceTests.anUnknownSensorOrANegativePageIsRejected
    resp = _client().get(f"{API}/side-effects/sensor{query}")
    assert resp.status_code == 400
    assert resp.json()["error"].startswith("Unknown Side Effects sensor '")


def test_side_effects_negative_offset_is_400() -> None:
    # ported: SideEffectsServiceTests.anUnknownSensorOrANegativePageIsRejected
    resp = _client().get(f"{API}/side-effects/sensor?sensor=files&offset=-1")
    assert resp.status_code == 400
    assert resp.json() == {"error": "offset and limit must not be negative."}


def test_code_paths_request_tree_echoes_the_request_id() -> None:
    # ported: CodePathsServiceTests.withoutTheSensorEveryReadAnswersItsUnavailableShape
    resp = _client().get(f"{API}/code-paths/requests/0000000000000000")
    assert resp.status_code == 200
    body = resp.json()
    assert body["requestId"] == "0000000000000000"
    assert body["available"] is False
    assert body["unavailableReason"].startswith(CODE_PATHS)
    assert body["found"] is False


def test_code_paths_route_applies_bootui_bounds() -> None:
    # ported: CodePathsServiceTests.withoutTheSensorEveryReadAnswersItsUnavailableShape
    client = _client()
    capped_resp = client.get(f"{API}/code-paths/route?route=GET%20%2Fx&depth=99&limit=9999")
    assert capped_resp.status_code == 200
    capped = capped_resp.json()
    defaults = client.get(f"{API}/code-paths/route?limit=0").json()
    assert capped["route"] == "GET /x"
    assert capped["depth"] == 33
    assert capped["page"]["limit"] == 500
    assert defaults["route"] is None
    assert defaults["depth"] == 8
    assert defaults["page"]["limit"] == 200


def test_code_inventory_list_echoes_the_limit_in_its_empty_page() -> None:
    # ported: CodeInventoryServiceTests.isUnavailableWithTheAgentsReason
    resp = _client().get(f"{API}/code-inventory/methods?limit=5")
    assert resp.status_code == 200
    assert resp.json()["page"]["limit"] == 5


def test_code_inventory_non_integer_limit_is_400() -> None:
    assert _client().get(f"{API}/code-inventory/changes?limit=x").status_code == 400


# --- actions: BootUI's refusals without the agent ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sensor", "body", "status", "fragment"),
    [
        ("environment", {}, 400, "enabled"),
        ("executors", {"enabled": True}, 400, "cannot be switched"),
        ("files", {"enabled": False}, 409, "not armed"),
    ],
    ids=["no-enabled", "unswitchable", "not-armed"],
)
def test_sensor_switch_refusals(sensor: str, body: dict[str, Any], status: int, fragment: str) -> None:
    # ported: AbstractBootUiApiConformanceTest.aSwitchableSensorCannotBeSwitchedWithoutTheAgentAndOtherSensorsNever
    resp = _client().post(f"{API}/java-agent/sensors/{sensor}", json=body)
    assert resp.status_code == status
    assert fragment in resp.json()["error"]


@pytest.mark.parametrize(
    ("method", "path", "body", "status", "fragment"),
    [
        ("POST", "/code-paths/probes", {}, 400, "Name the method to probe"),
        ("POST", "/code-paths/probes", {"method": "app.Prices#quote"}, 409, CODE_PATHS),
        ("POST", "/code-paths/probes/x/stop", None, 400, "A method probe id is a number"),
        ("POST", "/code-paths/probes/7/stop", None, 404, "This run has no method probe 7."),
        ("DELETE", "/code-paths/probes/7", None, 404, "This run has no method probe 7."),
    ],
    ids=["start-no-method", "start-not-armed", "stop-bad-id", "stop-unknown", "delete-unknown"],
)
def test_probe_refusals(method: str, path: str, body: Any, status: int, fragment: str) -> None:
    # ported: MethodProbeServiceTests.invalidMethodsAreBadRequestsAndRefusalsAreConflicts
    # ported: MethodProbeServiceTests.withoutTheAgentProbesAreUnavailable
    resp = _client().request(method, API + path, json=body)
    assert resp.status_code == status
    assert fragment in resp.json()["error"]


@pytest.mark.parametrize(
    ("panel", "path", "body"),
    [
        ("java-agent", "/java-agent/sensors/files", {"enabled": True}),
        ("code-paths", "/code-paths/probes", {"method": "app.Prices#quote"}),
    ],
)
def test_read_only_panel_refuses_the_action(
    monkeypatch: pytest.MonkeyPatch, panel: str, path: str, body: dict[str, Any]
) -> None:
    # ported: PanelAccessFilterTests.readOnlyCodePathsRefusesMethodProbesButNotItsReads
    monkeypatch.setenv(f"SHARPIT_PANELS_{panel.upper().replace('-', '_')}_READ_ONLY", "true")
    resp = _client().post(API + path, json=body)
    assert resp.status_code == 403
    assert resp.json() == {"error": PANEL_ACCESS_DENIED, "panel": panel, "reason": read_only_reason(panel, False)}


def test_sensor_reads_have_no_side_effects(no_side_effects: SideEffectGuard) -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop opens a self-pipe socket pair.
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        no_side_effects.block_network()
        statuses = [client.get(API + route).status_code for route, _golden, _prefix in READS]
        statuses.append(client.get(f"{API}/java-agent").status_code)
        statuses.append(client.get(f"{API}/side-effects/sensor?sensor=network").status_code)
        statuses.append(client.get(f"{API}/code-paths/requests/0000000000000000").status_code)
    assert statuses == [200] * (len(READS) + 3)
    assert no_side_effects.violations == []


@pytest.mark.parametrize(
    ("probe_id", "status", "error"),
    [
        ("x", 400, "A method probe id is a number, as get_method_probe returns it: x"),
        ("7", 404, "This run has no method probe 7."),
    ],
    ids=["not-a-number", "unknown"],
)
def test_probe_show_refusals(probe_id: str, status: int, error: str) -> None:
    # ported: MethodProbeServiceTests.withoutTheAgentProbesAreUnavailable
    resp = _client().get(f"{API}/code-paths/probes/{probe_id}")
    assert resp.status_code == status
    assert resp.json() == {"error": error}


# Long.parseLong after String.trim (MethodProbeService.parseId): a sign and outer spaces are allowed; an underscore, an
# inner space, a hex prefix or a value outside the signed 64-bit range is not
@pytest.mark.parametrize(
    ("probe_id", "status"),
    [
        ("1_0", 400),
        ("1%200", 400),
        ("0x10", 400),
        ("9223372036854775808", 400),
        ("-9223372036854775809", 400),
        ("9223372036854775807", 404),
        ("-9223372036854775808", 404),
        ("+7", 404),
        ("%207%20", 404),
    ],
)
@pytest.mark.parametrize(("method", "suffix"), [("GET", ""), ("POST", "/stop"), ("DELETE", "")])
def test_probe_ids_parse_as_java_longs(method: str, suffix: str, probe_id: str, status: int) -> None:
    # ported: MethodProbeServiceTests.invalidMethodsAreBadRequestsAndRefusalsAreConflicts
    resp = _client().request(method, f"{API}/code-paths/probes/{probe_id}{suffix}")
    assert resp.status_code == status


def test_probe_report_lists_the_bounds_that_apply_to_sharpit() -> None:
    limitations = _client().get(f"{API}/code-paths/probes").json()["limitations"]
    assert len(limitations) == 3
    assert any(
        line.startswith("A probe records at most 20 invocations, for at most 60 seconds") for line in limitations
    )


def test_side_effects_limitations_keep_the_minimisation_entries() -> None:
    limitations = _client().get(f"{API}/side-effects").json()["limitations"]
    assert len(limitations) == 3
    assert any(line.startswith("A process row shows the command's file name only") for line in limitations)
    assert any(line.startswith("A network row shows a host and port") for line in limitations)
