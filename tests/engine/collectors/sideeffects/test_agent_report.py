from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from sharpit.engine.collectors.sideeffects.agent_report import (
    LIMITATION_AGENT_OMITTED,
    LIMITATION_FILES,
    LIMITATION_NETWORK,
    LIMITATION_VALUES,
    agent_limitations,
)
from sharpit.engine.collectors.sideeffects.service import SideEffectsService
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.mcp import PROMPTS
from sharpit.engine.sensors.floor import SIDE_EFFECTS_LIMITATIONS
from sharpit.engine.sensors.rows import SensorRows

REQUEST = "0123456789abcdef"
SEEDED = "cnry7Q4x"
SECRET_NAME = "AKIAIOSFODNN7EXAMPLE"
RAW_HASH, REDACTED_HASH = 8_675_309_123, 5_550_100_987
_ROUTES: dict[str, str] = {}


def _service(exposure: Exposure = Exposure.MASKED) -> tuple[SideEffectsService, SensorRows]:
    _ROUTES.clear()
    rows = SensorRows()
    capture = SimpleNamespace(
        sensors=SimpleNamespace(rows=rows, is_on=lambda _name: True),
        journal=SimpleNamespace(request_routes=lambda ids: {key: _ROUTES[key] for key in ids if key in _ROUTES}),
    )
    return SideEffectsService(capture, Masker(exposure=exposure, mask_secrets=True), ready_at=lambda: None), rows


def _append(rows: SensorRows, source: str, **values: object) -> None:
    request_id = values.get("requestId")
    route = values.get("route")
    if isinstance(request_id, str) and isinstance(route, str):
        _ROUTES[request_id] = route
    rows.append({"source": source, "at": 1_000_000, "callSite": "app:run", **values})


def _process(rows: SensorRows, target: str, **values: object) -> None:
    _append(rows, "processes", kind="process", target=target, route="GET /reports", requestId=REQUEST, **values)


def _sink(rows: SensorRows, **values: object) -> None:
    fields: dict[str, object] = {
        "kind": "file-path",
        "target": "./reports/{name}.csv",
        "parameter": "name",
        "rawHash": RAW_HASH,
        "redactedHash": REDACTED_HASH,
        "requestId": REQUEST,
        "route": "GET /reports",
    }
    _append(rows, "security-sinks", **{**fields, **values})


def _no_echo(report: dict[str, object]) -> str:
    """The report as text without the agent's own query and the line that quotes it."""
    shown = {key: value for key, value in report.items() if key != "query"}
    limitations = [line for line in report["limitations"] if not line.startswith("No row matched")]  # type: ignore[attr-defined]
    return json.dumps({**shown, "limitations": limitations})


def test_the_agent_report_filters_rows_and_clear_recording_drops_them() -> None:
    # ported: SideEffectsServiceTests.theAgentReportFiltersRowsAndClearRecordingDropsThem
    service, rows = _service()
    _process(rows, "git")
    _process(rows, "convert")

    everything = service.agent_report(None, None)
    git = service.agent_report("git", None)
    by_sensor = service.agent_report("processes", 1)

    assert everything["matched"] == 2
    assert [row["target"] for row in git["rows"]] == ["git"]
    assert len(by_sensor["rows"]) == 1
    assert by_sensor["omitted"] == 1
    assert [sensor["id"] for sensor in by_sensor["sensors"]] == [item["id"] for item in service.report()["sensors"]]
    assert all(REQUEST in row["exemplarRequestIds"] for row in everything["rows"])
    assert service.agent_report(REQUEST, None)["matched"] == 2
    assert service.agent_report("00000000deadbeef", None)["matched"] == 0

    service.clear_recording()

    assert service.sensor("processes", None, None)["rows"] == []
    assert any(line.startswith("The recording was cleared") for line in service.limitations(cleared=True))
    time.sleep(0.3)  # the pending rows read their routes at most every 250 ms
    _process(rows, "git", at=time.time_ns() // 1_000_000)
    assert [row["target"] for row in service.sensor("processes", None, None)["rows"]] == ["git"]


def test_the_report_keys_follow_the_dto_order_and_no_match_says_so() -> None:
    service, _rows = _service()
    report = service.agent_report("  nothing  ", None)
    assert list(report) == [
        "available",
        "unavailableReason",
        "query",
        "sensors",
        "matched",
        "rows",
        "omitted",
        "limitations",
    ]
    assert report["query"] == "nothing"
    assert 'No row matched "nothing": call get_side_effects without a query to list them.' in report["limitations"]
    asked = service.agent_report(REQUEST.upper(), None)
    assert asked["limitations"][-1].endswith("among their exemplar requests, at most three each.")


def test_agents_get_the_fixed_limitations_of_the_sensors_they_see_and_every_run_specific_one() -> None:
    # ported: SideEffectsServiceTests.agentsGetTheFixedLimitationsOfTheSensorsTheySeeAndEveryRunSpecificOne
    scope = SIDE_EFFECTS_LIMITATIONS[0]
    attribution = "A row is attributed to its request's route as HTTP Exchanges names it."
    specific = "3 operations are counted in an Other row: a sensor keeps at most 500 rows and the run 2000."
    lines = [scope, LIMITATION_VALUES, LIMITATION_NETWORK, LIMITATION_FILES, attribution, specific]

    assert agent_limitations(lines, {"network"}) == [scope, LIMITATION_NETWORK, attribution, specific] + [
        LIMITATION_AGENT_OMITTED
    ]
    files = agent_limitations(lines, {"files"})
    assert LIMITATION_VALUES in files
    assert LIMITATION_FILES in files
    assert LIMITATION_NETWORK not in files
    assert agent_limitations([scope], set()) == [scope]


def test_request_input_in_sink_is_a_check_to_perform_and_its_sensor_is_opt_in() -> None:
    # ported: McpGuidanceTests.requestInputInSinkIsACheckToPerformAndItsSensorIsOptIn
    prompts = {prompt.name: prompt.text for prompt in PROMPTS}
    diagnose, assessment = prompts["diagnose_runtime_issue"], prompts["assess_application"]
    assert "does not record code-path or request-input-in-sink" not in diagnose
    assert "security-sinks row (request-input-in-sink)" in diagnose
    assert "check to perform, never a vulnerability verdict" in diagnose
    assert "SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true" in diagnose
    assert "seen in one request so far" in diagnose
    assert "unavailable rather than clean" in diagnose
    assert "security-sinks sensor is opt-in" in assessment
    assert "SHARPIT_AGENT_SENSORS lists security-sinks" in assessment
    assert "SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true" in assessment
    assert "unavailable rather than clean" in assessment


@pytest.mark.parametrize("seeded", [SEEDED, SEEDED.upper(), SEEDED[2:6]], ids=["raw", "upper", "substring"])
def test_a_query_holding_the_seeded_value_matches_no_row(seeded: str) -> None:
    service, rows = _service()
    _sink(rows)
    _sink(rows, requestId="fedcba9876543210", rawHash=RAW_HASH + 1)

    assert service.agent_report(None, None)["matched"] == 1
    report = service.agent_report(seeded, None)

    assert report["matched"] == 0
    assert report["rows"] == []
    assert SEEDED not in _no_echo(service.agent_report(None, None))


@pytest.mark.parametrize(
    "query",
    [str(RAW_HASH), str(REDACTED_HASH), "Check that it is validated", "reached this file path unchanged"],
    ids=["raw-hash", "redacted-hash", "detail", "detail-phrase"],
)
def test_matching_never_reads_a_hash_or_the_detail(query: str) -> None:
    service, rows = _service()
    _sink(rows)
    _sink(rows, requestId="fedcba9876543210", rawHash=RAW_HASH + 1)
    assert service.agent_report(None, None)["matched"] == 1
    assert "Check that it is validated" in service.agent_report(None, None)["rows"][0]["detail"]

    assert service.agent_report(query, None)["matched"] == 0


def test_a_query_by_parameter_name_finds_its_row() -> None:
    service, rows = _service()
    _sink(rows, parameter="page_size", target="./reports/{page_size}.csv")
    _sink(rows, requestId="fedcba9876543210", parameter="page_size", target="./reports/{page_size}.csv", rawHash=1)

    report = service.agent_report("PAGE_SIZE", None)

    assert report["matched"] == 1
    assert report["rows"][0]["parameter"] == "page_size"


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY, Exposure.FULL], ids=lambda e: e.name)
def test_a_query_holding_a_masked_parameter_name_or_segment_matches_no_row(exposure: Exposure) -> None:
    service, rows = _service(exposure)
    _sink(rows, parameter=SECRET_NAME, target=f"./reports/{{{SECRET_NAME}}}.csv")
    _sink(
        rows, requestId="fedcba9876543210", parameter=SECRET_NAME, target=f"./reports/{{{SECRET_NAME}}}.csv", rawHash=1
    )
    _append(rows, "files", kind="write", target=f"/srv/{SECRET_NAME}/report.csv", location="/srv", origin="application")

    shown = service.agent_report(None, None)

    assert shown["matched"] == 2
    assert SECRET_NAME not in _no_echo(shown)
    assert service.agent_report(SECRET_NAME, None)["matched"] == 0
    assert service.agent_report(SECRET_NAME.lower(), None)["matched"] == 0
    assert service.agent_report(SECRET_NAME[4:12], None)["matched"] == 0


def test_the_limit_is_clamped_and_a_negative_one_takes_the_default() -> None:
    service, rows = _service()
    for index in range(25):
        _process(rows, f"tool-{index}")

    assert len(service.agent_report(None, None)["rows"]) == 20
    assert len(service.agent_report(None, -1)["rows"]) == 20
    assert len(service.agent_report(None, 0)["rows"]) == 20
    assert len(service.agent_report(None, 3)["rows"]) == 3
    assert service.agent_report(None, 3)["omitted"] == 22
    assert len(service.agent_report(None, 10_000)["rows"]) == 25


def test_rows_are_listed_by_count_plus_completed_descending() -> None:
    service, rows = _service()
    _process(rows, "once")
    for _ in range(3):
        _process(rows, "often")

    assert [row["target"] for row in service.agent_report(None, None)["rows"]] == ["often", "once"]


def test_a_sensor_id_lists_that_sensor_and_names_it_in_the_limitations() -> None:
    service, rows = _service()
    _process(rows, "git")
    _append(rows, "files", kind="write", target="/srv/out.csv", location="/srv", origin="application")

    by_files = service.agent_report("files", None)
    by_network = service.agent_report("network", None)

    assert {row["sensor"] for row in by_files["rows"]} == {"files"}
    assert LIMITATION_FILES in by_files["limitations"]
    assert LIMITATION_NETWORK in by_network["limitations"]
    assert by_network["matched"] == 0


def test_without_the_lane_the_agent_report_is_unavailable_with_its_reason() -> None:
    report = SideEffectsService(None).agent_report("git", None)
    assert report["available"] is False
    assert report["unavailableReason"].startswith("Requires the sharpit agent:")
    assert report["rows"] == []
    assert report["matched"] == 0
