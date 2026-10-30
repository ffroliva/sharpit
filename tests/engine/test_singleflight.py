import time

import pytest

from sharpit.engine.singleflight import ActionBusy, SingleFlight, WaitTimeout


def test_second_call_busy_409_body():
    sf = SingleFlight()
    with pytest.raises(WaitTimeout):
        sf.run("scan", lambda: time.sleep(0.3), wait_timeout=0.02)
    with pytest.raises(ActionBusy) as ei:
        sf.run("dismiss", lambda: None)
    assert ei.value.body() == {
        "error": "BootUI action already in progress".replace("BootUI", "sharpit"),
        "operation": "dismiss",
        "activeOperation": "scan",
        "message": "Operation 'dismiss' cannot start while 'scan' is in progress.",
    }
    time.sleep(0.4)


def test_returns_value_and_propagates_exception():
    sf = SingleFlight()
    assert sf.run("a", lambda: 7) == 7

    def boom() -> None:
        raise ValueError("x")

    with pytest.raises(ValueError):
        sf.run("a", boom)


def test_lock_released_after_exception():
    sf = SingleFlight()

    def boom() -> None:
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        sf.run("a", boom)
    assert sf.run("b", lambda: "ok") == "ok"


def test_lock_held_until_worker_finishes():
    sf = SingleFlight()
    with pytest.raises(WaitTimeout):
        sf.run("slow", lambda: time.sleep(0.5), wait_timeout=0.05)
    with pytest.raises(ActionBusy):
        sf.run("other", lambda: None)
    time.sleep(0.6)
    assert sf.run("other", lambda: "done") == "done"
