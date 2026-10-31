import threading

import pytest

from sharpit.engine.singleflight import ActionBusy, Flight, SingleFlight


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


def test_try_acquire_busy_returns_none():
    sf = SingleFlight()
    release = sf.try_acquire("health-check")
    assert release is not None
    assert sf.try_acquire("health-check") is None
    with pytest.raises(ActionBusy) as ei:  # run() sees the same flight
        sf.run("other", lambda: None)
    assert ei.value.active == "health-check"
    release()


def test_release_frees_operation():
    sf = SingleFlight()
    release = sf.try_acquire("a")
    assert release is not None
    release()
    release()  # idempotent: a second call never frees a later flight
    again = sf.try_acquire("b")
    assert again is not None
    release()
    assert sf.try_acquire("c") is None
    again()


def test_operations_independent():
    # one instance per operation (ctx.lazy("singleflight:<op>")): a stuck health check never blocks a refresh
    health, alembic = SingleFlight(), SingleFlight()
    held = health.try_acquire("health-check")
    assert held is not None and alembic.try_acquire("alembic-refresh") is not None


def test_flight_held_until_every_worker_is_done():
    sf = SingleFlight()
    release = sf.try_acquire("op")
    assert release is not None
    flight = Flight(release)
    first, second = flight.worker(), flight.worker()
    flight.done()  # the awaiting coroutine gave up
    first()
    assert sf.try_acquire("x") is None  # one worker still running
    second()
    assert sf.try_acquire("x") is not None
