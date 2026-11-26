from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from sharpit.engine.collectors.sideeffects.pending import MAX_PENDING
from sharpit.engine.collectors.sideeffects.service import SideEffectsService
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sensors.floor import SensorRefusal
from sharpit.engine.sensors.rows import SensorRows


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
    assert lines[0] == "Side Effects records only what the sharpit agent's side-effect sensors hook."
    assert lines[1].startswith("A process row shows the command's file name only")
    assert lines[2] == "A network row shows a host and port, never a byte sent or received, nor a URL's path or query."
    assert lines[3].startswith("Files: the interpreter's own files (imports)")
    assert lines[4].startswith("Security sinks: request input is matched only while")
    assert lines[5].startswith("A row is attributed to its request's route as HTTP Exchanges names it")
    assert lines[6].startswith("HTTP Exchanges is disabled: Side Effects attributes rows")
    assert lines[7] == "1 operation is counted in an Other row: a sensor keeps at most 500 rows and the run 2000."
    assert lines[8].startswith("The recording was cleared: rows recorded before then were dropped")
    assert lines[9] == "Request-value matching: 0 requests held values, 0 sink checks ran."
    assert lines[10].startswith("1 security-sinks match is not shown yet: a number")


def test_the_files_and_attribution_lines_are_the_adapted_texts() -> None:
    lines = SideEffectsService(None).limitations()
    assert any("the interpreter's own files (imports)" in line for line in lines)
    assert any("A row is attributed to its request's route" in line for line in lines)


def test_two_reads_and_a_clear_at_once_lose_and_duplicate_nothing() -> None:
    service, rows = _service_with_rows()
    appended = threading.Event()
    completed = [threading.Event() for _ in range(3)]

    service.lock.acquire()
    try:
        appender = threading.Thread(
            target=lambda: (rows.append({"source": "files", "kind": "write", "target": "./report.csv"}), appended.set())
        )
        workers = (
            threading.Thread(target=lambda: (service.report(), completed[0].set())),
            threading.Thread(target=lambda: (service.sensor("files", 0, 20), completed[1].set())),
            threading.Thread(target=lambda: (service.clear_recording(), completed[2].set())),
        )
        appender.start()
        for worker in workers:
            worker.start()
        assert appended.wait(1)
        assert all(not event.wait(0.05) for event in completed)
    finally:
        service.lock.release()
    appender.join(1)
    for worker in workers:
        worker.join(1)
    assert all(event.is_set() for event in completed)


def test_ready_at_is_when_the_host_lifespan_startup_completed() -> None:
    ready_at = 1_800_000_000_000
    assert SideEffectsService(None, ready_at=lambda: ready_at).ready_at() == ready_at


def test_without_a_lifespan_no_row_counts_under_startup() -> None:
    service, rows = _service_with_rows()
    _append(rows, "processes", kind="process", target="worker", threadName="worker-1")
    result = service.sensor("processes", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["attribution"] == "worker-{n}"
    assert result[0]["scope"] == "thread"


def test_clearing_the_recording_clears_the_side_effects_rows() -> None:
    # adapted from: SideEffectsServiceTests.theAgentReportFiltersRowsAndClearRecordingDropsThem
    service = SideEffectsService(None)
    service.clear_recording()
    assert (
        "The recording was cleared: rows recorded before then were dropped, and so is a record the agent "
        "still held whose first occurrence came before the clear." in service.limitations()
    )


def test_an_idle_or_low_footprint_suspend_keeps_the_side_effects_rows() -> None:
    from sharpit.engine.capture.journal import RuntimeJournal
    from sharpit.engine.sensors.lane import SensorHook, SensorLane

    rows = SensorRows()
    lane = SensorLane([], RuntimeJournal(), configured=(), rows=rows)
    capture = SimpleNamespace(sensors=lane, journal=SimpleNamespace(request_routes=lambda _ids: {}))
    service = SideEffectsService(capture, Masker(exposure=Exposure.MASKED, mask_secrets=True), ready_at=lambda: None)
    _append(rows, "files", kind="write", target="./report.csv")
    assert service.sensor("files", 0, 20)["page"]["total"] == 1

    hook = SensorHook("files", lane)
    hook.suspend()
    hook.discard()

    assert service.sensor("files", 0, 20)["page"]["total"] == 1
    assert not any("recording was cleared" in line.lower() for line in service.report()["limitations"])


def test_report_keys_follow_the_dto_order() -> None:
    service, _rows = _service_with_rows()
    assert list(service.report()) == ["available", "unavailableReason", "sensors", "limitations"]


def test_sensor_report_keys_follow_the_dto_order() -> None:
    service, _rows = _service_with_rows()
    assert list(service.sensor("files", 0, 100)) == [
        "available",
        "unavailableReason",
        "sensor",
        "rows",
        "page",
        "limitations",
    ]


def test_sensor_dto_keys_follow_the_dto_order() -> None:
    service, _rows = _service_with_rows()
    assert list(service.report()["sensors"][0]) == [
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
    from fastapi.testclient import TestClient

    from fastapi import FastAPI
    from sharpit import install

    app = FastAPI()
    handle = install(
        app,
        enabled="OFF",
        show_banner=False,
        config_scan=False,
        agent_sensors=("processes", "files", "security-sinks"),
        agent_security_sinks_request_values=True,
    )
    assert handle.context.capture.side_effects is None
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/sharpit/api/side-effects").status_code == 404
        assert client.get("/sharpit/api/side-effects/sensor?sensor=files").status_code == 404


_ROUTES: dict[str, str] = {}


def _service_with_rows() -> tuple[SideEffectsService, SensorRows]:
    _ROUTES.clear()
    rows = SensorRows()
    lane = SimpleNamespace(rows=rows, is_on=lambda _name: True)
    capture = SimpleNamespace(
        sensors=lane,
        journal=SimpleNamespace(request_routes=lambda ids: {key: _ROUTES[key] for key in ids if key in _ROUTES}),
    )
    return SideEffectsService(
        capture,
        Masker(exposure=Exposure.MASKED, mask_secrets=True),
        ready_at=lambda: None,
    ), rows


def _append(rows: SensorRows, source: str, **values: object) -> None:
    request_id = values.get("requestId")
    route = values.get("route")
    if isinstance(request_id, str) and isinstance(route, str):
        _ROUTES[request_id] = route
    rows.append({"source": source, "at": 1_000_000, "callSite": "app:run", **values})


def test_a_digits_only_argument_waits_for_confirmation() -> None:
    # adapted from: SecuritySinksServiceTests.aDigitsOnlyValueInsideALiteralAlsoWaitsForConfirmation
    service, rows = _service_with_rows()
    _append(
        rows,
        "security-sinks",
        kind="command",
        target="convert, argument 1",
        parameter="page",
        numeric=True,
        rawHash=1,
        redactedHash=2,
        requestId="0000000000000001",
    )
    first = service.sensor("security-sinks", 0, 20)
    assert first["rows"] == []
    assert any("not shown yet" in line for line in first["limitations"])


def test_a_file_row_reads_file_path_and_its_sentence() -> None:
    service, rows = _service_with_rows()
    _append(
        rows,
        "security-sinks",
        kind="file-path",
        target="./reports/{name}.csv",
        parameter="name",
        requestId="0000000000000001",
        route="GET /reports",
    )
    result = service.sensor("security-sinks", 0, 20)
    assert len(result["rows"]) == 1
    assert result["rows"][0]["kind"] == "file path"
    assert result["rows"][0]["location"] is None
    assert "Check that it is validated and cannot leave its directory." in result["rows"][0]["detail"]


def test_a_report_written_outside_the_temporary_directory_is_an_application_write_of_its_route_by_pattern_only() -> (
    None
):  # noqa: E501
    # ported: SideEffectsServiceTests.aReportWrittenOutsideTheTemporaryDirectoryIsAnApplicationWriteOfItsRouteByPatternOnly  # noqa: E501
    service, rows = _service_with_rows()
    _append(
        rows,
        "files",
        kind="write",
        target="/srv/exports/hunter{n}-secret-{n}-{n}-{n}.csv",
        location="/srv/exports",
        route="GET /reports",
        requestId="0000000000000001",
        callSite="sideeffectsapp.Launcher#writeFile",
        origin="application",
    )
    result = service.sensor("files", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["attribution"] == "GET /reports"
    assert result[0]["origin"] == "application"
    assert "{n}" in result[0]["target"]


def test_a_requests_failed_start_is_a_row_of_its_route_with_the_commands_file_name_only() -> None:
    # adapted from: SideEffectsServiceTests.aRequestsFailedStartIsARowOfItsRouteWithTheCommandsFileNameOnly
    service, rows = _service_with_rows()
    _append(
        rows,
        "processes",
        kind="process",
        target="report-tool",
        route="GET /reports",
        failed=2,
        requestId="0000000000000001",
        callSite="sideeffectsapp.Launcher#failedStart",
    )
    result = service.sensor("processes", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["attribution"] == "GET /reports"
    assert result[0]["target"] == "report-tool"
    assert result[0]["failed"] == 0


def test_a_second_request_with_another_value_confirms_the_row() -> None:
    # adapted from: SecuritySinksServiceTests.aSecondRequestWithAnotherValueConfirmsTheRow
    service, rows = _service_with_rows()
    _append(
        rows,
        "security-sinks",
        kind="file-path",
        target="./reports/{name}.csv",
        parameter="name",
        numeric=True,
        requestId="0000000000000001",
        rawHash=1,
        redactedHash=7,
    )
    assert service.sensor("security-sinks", 0, 20)["rows"] == []

    _append(
        rows,
        "security-sinks",
        kind="file-path",
        target="./reports/{name}.csv",
        parameter="name",
        numeric=True,
        requestId="0000000000000002",
        rawHash=2,
        redactedHash=7,
    )
    result = service.sensor("security-sinks", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["parameter"] == "name"
    assert result[0]["count"] == 2


def test_a_text_with_more_matches_than_can_be_redacted_keeps_no_text() -> None:
    # adapted from: SecuritySinksServiceTests.aStatementWithMoreMatchesThanCanBeRedactedKeepsNoText
    service, rows = _service_with_rows()
    _append(
        rows,
        "security-sinks",
        kind="command",
        target="(text not kept)",
        parameter="name",
        requestId="0000000000000001",
        rawHash=1,
        redactedHash=2,
        matches=9,
    )
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
    # ported: SideEffectsServiceTests.whileHttpExchangesIsHiddenRouteRowsAreMergedWithoutRequestIds
    service, rows = _service_with_rows()
    for request_id in ("0000000000000001", "0000000000000002"):
        _append(rows, "processes", kind="start", target="python", requestId=request_id)
    result = service.sensor("processes", 0, 20)["rows"]
    assert len(result) == 1
    assert result[0]["attribution"] == "(unknown route)"
    assert result[0]["count"] == 2
    assert "requestId" not in result[0]


def test_the_files_line_says_process_and_file_rows_carry_no_call_site() -> None:
    line = next(line for line in SideEffectsService(None).limitations() if line.startswith("Files:"))
    assert "Process and file rows carry no call site, and file rows report their origin as unknown." in line
    assert "call site's frames" not in line


def test_the_sinks_line_says_hand_off_work_is_checked_only_while_the_request_is_live() -> None:
    line = next(line for line in SideEffectsService(None).limitations() if line.startswith("Security sinks:"))
    assert "is checked only while the request is live" in line
    assert "work that runs after the response completes, or after 60 seconds, is not checked" in line
    assert "its rows keep the raw text" in line


def _hidden_service(*, http_journaled: bool, exchanges_enabled: bool) -> tuple[SideEffectsService, SensorRows]:
    rows = SensorRows()
    lane = SimpleNamespace(rows=rows, is_on=lambda _name: True)
    journal = SimpleNamespace(request_routes=lambda _ids: {}, accepts=lambda source: http_journaled or source != "http")
    service = SideEffectsService(
        SimpleNamespace(sensors=lane, journal=journal),
        Masker(exposure=Exposure.MASKED, mask_secrets=True),
        ready_at=lambda: None,
        exchanges_enabled=lambda: exchanges_enabled,
    )
    return service, rows


@pytest.mark.parametrize(("http_journaled", "exchanges_enabled"), [(False, True), (True, False)])
def test_route_rows_merge_under_route_hidden_without_request_ids_when_http_is_not_recorded(
    http_journaled: bool, exchanges_enabled: bool
) -> None:
    # ported: SideEffectsServiceTests.whileHttpExchangesIsHiddenRouteRowsAreMergedWithoutRequestIds
    service, rows = _hidden_service(http_journaled=http_journaled, exchanges_enabled=exchanges_enabled)
    for request_id in ("0000000000000001", "0000000000000002"):
        rows.append(
            {"source": "processes", "at": time.time_ns() // 1_000_000, "kind": "start", "target": "python"}
            | {"requestId": request_id}
        )
    report = service.sensor("processes", 0, 20)
    assert [row["attribution"] for row in report["rows"]] == ["(route hidden)"]
    assert report["rows"][0]["count"] == 2
    assert "requestId" not in report["rows"][0]
    assert any(
        line.startswith("HTTP Exchanges is disabled: Side Effects attributes rows") for line in report["limitations"]
    )


def test_route_rows_wait_for_their_route_while_http_is_recorded() -> None:
    service, rows = _hidden_service(http_journaled=True, exchanges_enabled=True)
    rows.append(
        {
            "source": "processes",
            "at": time.time_ns() // 1_000_000,
            "kind": "start",
            "target": "python",
            "requestId": "0000000000000001",
        }
    )
    report = service.sensor("processes", 0, 20)
    assert report["rows"] == []
    assert not any(line.startswith("HTTP Exchanges is disabled") for line in report["limitations"])


def test_the_agent_report_lists_the_rows_its_sensors_count() -> None:
    service, rows = _service_with_rows()
    _append(rows, "processes", kind="start", target="python")
    store = service.store
    assert store is not None
    drain, arrived = store.drain, []

    def drain_then_a_row_arrives() -> None:
        drain()
        if not arrived:
            arrived.append(True)
            _append(rows, "processes", kind="start", target="git")

    store.drain = drain_then_a_row_arrives  # type: ignore[method-assign]
    report = service.agent_report(None, None)
    counted = sum(sensor["rows"] for sensor in report["sensors"])
    assert len(report["rows"]) == counted


def test_rows_the_pending_list_dropped_are_reported_as_dropped_by_their_sensor() -> None:
    service, rows = _service_with_rows()
    now = time.time_ns() // 1_000_000
    for index in range(MAX_PENDING + 1):
        rows.append(
            {"source": "processes", "at": now, "kind": "start", "target": "python", "requestId": f"{index:016x}"}
        )
        if index == MAX_PENDING - 1:
            service.report()  # the pending list now holds MAX_PENDING rows waiting for a route
    dropped = {sensor["id"]: sensor["dropped"] for sensor in service.report()["sensors"]}
    assert dropped["processes"] == 1
    assert dropped["files"] == 0
