"""``SensorLane.holder_status``: the request-value holder's counters, or None while the setting is off."""

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.sensors.lane import build_lane


def test_holder_status_is_none_with_the_setting_off() -> None:
    lane = build_lane(("processes",), RuntimeJournal(), lambda p: p)
    assert lane is not None
    assert lane.holder_status() is None


def test_holder_status_returns_counts_with_the_setting_on() -> None:
    lane = build_lane(("processes",), RuntimeJournal(), lambda p: p, request_values=True)
    assert lane is not None
    status = lane.holder_status()
    assert status is not None
    assert status["requests"] == 0
