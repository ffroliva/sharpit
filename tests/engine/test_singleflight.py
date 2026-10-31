import threading

import pytest

from sharpit.engine.singleflight import ActionBusy, SingleFlight


def _hold(sf: SingleFlight, operation: str) -> tuple[threading.Event, threading.Thread]:
    """Run ``operation`` on a thread until the returned event is set."""
    entered, release = threading.Event(), threading.Event()

    def fn() -> None:
        entered.set()
        release.wait(5)

    thread = threading.Thread(target=sf.run, args=(operation, fn))
    thread.start()
    assert entered.wait(5)
    return release, thread


def test_second_call_busy_409_body():
    sf = SingleFlight()
    release, thread = _hold(sf, "scan")
    try:
        with pytest.raises(ActionBusy) as ei:
            sf.run("dismiss", lambda: None)
    finally:
        release.set()
        thread.join(5)
    assert ei.value.body() == {
        "error": "BootUI action already in progress".replace("BootUI", "sharpit"),
        "operation": "dismiss",
        "activeOperation": "scan",
        "message": "Operation 'dismiss' cannot start while 'scan' is in progress.",
    }


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


def test_lock_held_until_the_call_finishes():
    sf = SingleFlight()
    release, thread = _hold(sf, "slow")
    with pytest.raises(ActionBusy):
        sf.run("other", lambda: None)
    release.set()
    thread.join(5)
    assert sf.run("other", lambda: "done") == "done"
