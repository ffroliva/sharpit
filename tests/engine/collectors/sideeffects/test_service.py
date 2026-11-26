from __future__ import annotations

from types import SimpleNamespace

import pytest

from sharpit.engine.collectors.sideeffects.service import SideEffectsService
from sharpit.engine.sensors.floor import SensorRefusal
from sharpit.engine.sensors.rows import SensorRows
from sharpit.engine.masking import Exposure, Masker


def test_every_sensor_is_listed_in_tab_order_and_those_not_shipped_say_so() -> None:
    # ported: SideEffectsServiceTests.everySensorIsListedInTabOrderAndThoseNotShippedSaySo
    capture = SimpleNamespace(
        sensors=SimpleNamespace(rows=SensorRows(), is_on=lambda _name: True),
        journal=SimpleNamespace(request_routes=lambda _ids: {}),
    )
    report = SideEffectsService(capture, object()).report()
    assert [sensor["id"] for sensor in report["sensors"]] == [
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
    assert report["sensors"][0]["reason"] == "Not available in this version."
    assert report["sensors"][1]["state"] == "recording"


def test_an_unknown_sensor_or_a_negative_page_is_rejected() -> None:
    # ported: SideEffectsServiceTests.anUnknownSensorOrANegativePageIsRejected
    service = SideEffectsService(None)
    with pytest.raises(SensorRefusal, match="sockets"):
        service.sensor("sockets", 0, 10)


def test_without_the_lane_every_read_is_unavailable_with_its_reason() -> None:
    # ported: SideEffectsServiceTests.withoutTheAgentEveryReadIsUnavailableWithItsReason
    report = SideEffectsService(None).report()
    assert report["available"] is False
    assert report["unavailableReason"].startswith("Requires the sharpit agent:")


def test_the_holder_line_is_shown_whenever_the_setting_is_on() -> None:
    assert "Request-value matching: 0 requests held values, 0 sink checks ran." in SideEffectsService(None).limitations(
        holder_enabled=True
    )


def test_no_holder_line_without_the_setting() -> None:
    assert not any("Request-value matching:" in line for line in SideEffectsService(None).limitations())


def test_limitation_lines_follow_bootuis_order() -> None:
    lines = SideEffectsService(None).limitations(
        holder_enabled=True, routes_hidden=True, cleared=True, folded=1, unconfirmed=1
    )
    assert lines.index(
        "HTTP Exchanges is disabled: Side Effects attributes rows to the request's route only while "
        "HTTP Exchanges records; without it, rows are attributed to startup or their thread's family."
    ) < lines.index("1 operation is counted in an Other row: a sensor keeps at most 500 rows and the run 2000.")
    assert lines.index(
        "The recording was cleared: rows recorded before then were dropped, and so is a record the agent "
        "still held whose first occurrence came before the clear."
    ) < lines.index("Request-value matching: 0 requests held values, 0 sink checks ran.")


def test_the_files_and_attribution_lines_are_the_adapted_texts() -> None:
    lines = SideEffectsService(None).limitations()
    assert any("the interpreter's own files (imports)" in line for line in lines)
    assert any("A row is attributed to its request's route" in line for line in lines)


def test_two_reads_and_a_clear_at_once_lose_and_duplicate_nothing() -> None:
    service = SideEffectsService(None)
    assert service.report()["available"] is False
    service.clear_recording()


def test_ready_at_is_when_the_host_lifespan_startup_completed() -> None:
    assert SideEffectsService(None).ready_at() is None


def test_without_a_lifespan_no_row_counts_under_startup() -> None:
    assert SideEffectsService(None).ready_at() is None


def test_clearing_the_recording_clears_the_side_effects_rows() -> None:
    # adapted from: SideEffectsServiceTests.theAgentReportFiltersRowsAndClearRecordingDropsThem
    service = SideEffectsService(None)
    service.clear_recording()
    assert (
        "The recording was cleared: rows recorded before then were dropped, and so is a record the agent "
        "still held whose first occurrence came before the clear." in service.limitations()
    )


def test_an_idle_or_low_footprint_suspend_keeps_the_side_effects_rows() -> None:
    assert "RECORDING_CLEARED" not in SideEffectsService(None).limitations()


def test_report_keys_follow_the_dto_order() -> None:
    assert list(SideEffectsService(None).report()) == ["available", "unavailableReason", "sensors", "limitations"]


def test_sensor_report_keys_follow_the_dto_order() -> None:
    assert list(SideEffectsService(None).sensor("files", 0, 100)) == [
        "available",
        "unavailableReason",
        "sensor",
        "rows",
        "page",
        "limitations",
    ]


def test_sensor_dto_keys_follow_the_dto_order() -> None:
    assert list(SideEffectsService(None).report()["sensors"][0]) == [
        "id",
        "group",
        "label",
        "state",
        "reason",
        "rows",
        "occurrences",
        "dropped",
        "hooks",
        "toggle",
    ]


def test_an_inactive_console_builds_no_ring_or_store_and_answers_404() -> None:
    assert SideEffectsService(None).store is None


_ROUTES: dict[str, str] = {}


def _service_with_rows() -> tuple[SideEffectsService, SensorRows]:
    _ROUTES.clear()
    rows = SensorRows()
    lane = SimpleNamespace(rows=rows, is_on=lambda _name: True)
    capture = SimpleNamespace(
        sensors=lane,
        journal=SimpleNamespace(request_routes=lambda ids: {key: _ROUTES[key] for key in ids if key in _ROUTES}),
    )
    return SideEffectsService(capture, Masker(exposure=Exposure.MASKED, mask_secrets=True)), rows


def _append(rows: SensorRows, source: str, **values: object) -> None:
    request_id = values.get("requestId")
    route = values.get("route")
    if isinstance(request_id, str) and isinstance(route, str):
        _ROUTES[request_id] = route
    rows.append({"source": source, "at": 1_000_000, "callSite": "app:run", **values})


def test_a_digits_only_argument_waits_for_confirmation() -> None:
    # adapted from: SecuritySinksServiceTests.aDigitsOnlyValueInsideALiteralAlsoWaitsForConfirmation
    service, rows = _service_with_rows()
    _append(rows, "security-sinks", kind="command", target="convert, argument 1", parameter="page", numeric=True,
            rawHash=1, redactedHash=2, requestId="0000000000000001")
    first = service.sensor("security-sinks", 0, 20)
    assert first["rows"] == []
    assert any("not shown yet" in line for line in first["limitations"])


def test_a_file_row_reads_file_path_and_its_sentence() -> None:
    service, rows = _service_with_rows()
    _append(rows, "security-sinks", kind="file-path", target="./reports/{name}.csv", parameter="name",
            requestId="0000000000000001", route="GET /reports")
    result = service.sensor("security-sinks", 0, 20)
    assert len(result["rows"]) == 1
    assert result["rows"][0]["kind"] == "file path"
    assert result["rows"][0]["location"] is None
    assert "Check that it is validated and cannot leave its directory." in result["rows"][0]["detail"]


def test_a_report_written_outside_the_temporary_directory_is_an_application_write_of_its_route_by_pattern_only() -> None:
    # ported: SideEffectsServiceTests.aReportWrittenOutsideTheTemporaryDirectoryIsAnApplicationWriteOfItsRouteByPatternOnly
    service, rows = _service_with_rows()
    _append(rows, "files", kind="write", target="/srv/exports/hunter{n}-secret-{n}-{n}-{n}.csv",
            location="/srv/exports", route="GET /reports", requestId="0000000000000001",
            callSite="sideeffectsapp.Launcher#writeFile", origin="application")
    result = service.sensor("files", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["attribution"] == "GET /reports"
    assert result[0]["origin"] == "application"
    assert "{n}" in result[0]["target"]


def test_a_requests_failed_start_is_a_row_of_its_route_with_the_commands_file_name_only() -> None:
    # adapted from: SideEffectsServiceTests.aRequestsFailedStartIsARowOfItsRouteWithTheCommandsFileNameOnly
    service, rows = _service_with_rows()
    _append(rows, "processes", kind="process", target="report-tool", route="GET /reports", failed=2,
            requestId="0000000000000001", callSite="sideeffectsapp.Launcher#failedStart")
    result = service.sensor("processes", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["attribution"] == "GET /reports"
    assert result[0]["target"] == "report-tool"
    assert result[0]["failed"] == 0


def test_a_second_request_with_another_value_confirms_the_row() -> None:
    # adapted from: SecuritySinksServiceTests.aSecondRequestWithAnotherValueConfirmsTheRow
    service, rows = _service_with_rows()
    for request_id, raw_hash in (("0000000000000001", 1), ("0000000000000002", 2)):
        _append(rows, "security-sinks", kind="file-path", target="./reports/{name}.csv", parameter="name",
                requestId=request_id, rawHash=raw_hash, redactedHash=7)
    result = service.sensor("security-sinks", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["parameter"] == "name"
    assert result[0]["count"] == 2


def test_a_text_with_more_matches_than_can_be_redacted_keeps_no_text() -> None:
    # adapted from: SecuritySinksServiceTests.aStatementWithMoreMatchesThanCanBeRedactedKeepsNoText
    service, rows = _service_with_rows()
    _append(rows, "security-sinks", kind="command", target="(text not kept)", parameter="name",
            requestId="0000000000000001", rawHash=1, redactedHash=2, matches=9)
    result = service.sensor("security-sinks", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["target"] == "(text not kept)"
    assert "secret" not in str(result[0]["detail"]).lower()


def test_the_security_sinks_label_names_commands_and_file_paths() -> None:
    from sharpit.engine.sensors.floor import SIDE_EFFECT_SENSORS

    label = next(item[2] for item in SIDE_EFFECT_SENSORS if item[0] == "security-sinks")
    assert label == "Request input reaching commands and file paths"


def test_the_security_sinks_limitation_names_only_commands_and_file_paths() -> None:
    lines = SideEffectsService(None).limitations()
    limitation = next(line for line in lines if line.startswith("Security sinks:"))
    assert "command" in limitation
    assert "file path" in limitation
    assert "SQL text and outbound URLs are not checked." in limitation


def test_while_http_exchanges_is_hidden_route_rows_are_merged_without_request_ids() -> None:
    service, rows = _service_with_rows()
    for request_id in ("0000000000000001", "0000000000000002"):
        _append(rows, "processes", kind="start", target="python", requestId=request_id)
    result = service.sensor("processes", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["attribution"] == "(unknown route)"
    assert result[0]["count"] == 2
    assert "requestId" not in result[0]
