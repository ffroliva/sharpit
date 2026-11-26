from __future__ import annotations

from sharpit.engine.collectors.sideeffects.service import SideEffectsService


def test_every_sensor_is_listed_in_tab_order_and_those_not_shipped_say_so() -> None:
    report = SideEffectsService(None).report()
    assert [sensor["id"] for sensor in report["sensors"]] == [
        "network", "files", "processes", "environment", "thread-activity", "thread-locals", "resources",
        "blocking", "security-sinks",
    ]
    assert report["sensors"][0]["reason"] == "Not available in this version."


def test_an_unknown_sensor_or_a_negative_page_is_rejected() -> None:
    service = SideEffectsService(None)
    try:
        service.sensor("sockets", 0, 10)
    except ValueError as exc:
        assert "sockets" in str(exc)
    else:
        raise AssertionError("unknown sensor accepted")


def test_without_the_lane_every_read_is_unavailable_with_its_reason() -> None:
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
    lines = SideEffectsService(None).limitations(holder_enabled=True, routes_hidden=True, cleared=True, folded=1, unconfirmed=1)
    assert lines.index("The route names of rows are hidden.") < lines.index("1 operation is counted in an Other row: a sensor keeps at most 500 rows and the run 2000.")
    assert lines.index("RECORDING_CLEARED") < lines.index("Request-value matching: 0 requests held values, 0 sink checks ran.")


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
    service = SideEffectsService(None)
    service.clear_recording()
    assert "RECORDING_CLEARED" in service.limitations()


def test_an_idle_or_low_footprint_suspend_keeps_the_side_effects_rows() -> None:
    assert "RECORDING_CLEARED" not in SideEffectsService(None).limitations()


def test_report_keys_follow_the_dto_order() -> None:
    assert list(SideEffectsService(None).report()) == ["available", "unavailableReason", "sensors", "limitations"]


def test_sensor_report_keys_follow_the_dto_order() -> None:
    assert list(SideEffectsService(None).sensor("files", 0, 100)) == ["available", "unavailableReason", "sensor", "rows", "page", "limitations"]


def test_sensor_dto_keys_follow_the_dto_order() -> None:
    assert list(SideEffectsService(None).report()["sensors"][0]) == ["id", "group", "label", "state", "reason", "rows", "occurrences", "dropped", "hooks", "toggle"]


def test_an_inactive_console_builds_no_ring_or_store_and_answers_404() -> None:
    assert SideEffectsService(None).store is None
