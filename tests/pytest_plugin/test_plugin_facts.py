from __future__ import annotations

import gc
import logging
from types import SimpleNamespace

import pytest

from engine.testsession.tsfakes import LockProbe
from sharpit import pytest_plugin
from sharpit.engine.capture.correlation import TEST
from sharpit.engine.sources import dispatch
from sharpit.engine.testsession.sink import TestSessionSink

CAPTURE_STOPPED = "sharpit capture stopped before the session ended (another pytest run in this process?)"


def test_worker_and_controller_collect_the_same_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(pytest_plugin.sys.modules, "asyncpg", object())
    gc.collect()  # engines are found through gc.get_objects(): drop dead ones so both calls see the same set
    worker = SimpleNamespace(sink=TestSessionSink("gw0"), sqlite_attached=False)
    controller = SimpleNamespace(sink=TestSessionSink("master"), sqlite_attached=False)

    pytest_plugin._final_facts(worker)  # type: ignore[arg-type]
    pytest_plugin._final_facts(controller)  # type: ignore[arg-type]

    assert worker.sink.facts.untraced_drivers == controller.sink.facts.untraced_drivers
    assert worker.sink.facts.engine_drivers == controller.sink.facts.engine_drivers
    assert worker.sink.facts.sources == controller.sink.facts.sources


def _plugin_reasons(sink: TestSessionSink) -> list[str | None]:
    return [source["reason"] for source in sink.facts.sources if source["name"] == "pytest-plugin"]


@pytest.mark.parametrize("another_sink", [False, True], ids=["detached", "another-sink"])
def test_capture_detached_before_the_session_ended_makes_the_run_unknown(another_sink: bool) -> None:
    """A nested in-process pytest run detaches or replaces the outer session's capture: the run is `unknown`."""
    state = SimpleNamespace(sink=TestSessionSink("master"), sqlite_attached=False)
    previous = dispatch.session_sink()
    dispatch.set_session_sink(TestSessionSink("master") if another_sink else None)
    try:
        pytest_plugin._final_facts(state)  # type: ignore[arg-type]
    finally:
        dispatch.set_session_sink(previous)
    assert _plugin_reasons(state.sink) == [CAPTURE_STOPPED]


def test_capture_still_attached_at_the_end_adds_no_plugin_source() -> None:
    state = SimpleNamespace(sink=TestSessionSink("master"), sqlite_attached=False)
    previous = dispatch.session_sink()
    dispatch.set_session_sink(state.sink)
    try:
        pytest_plugin._final_facts(state)  # type: ignore[arg-type]
    finally:
        dispatch.set_session_sink(previous)
    assert _plugin_reasons(state.sink) == []


def _emit(handler: logging.Handler, record: logging.LogRecord) -> BaseException | None:
    try:
        handler.emit(record)
    except Exception as exc:  # noqa: BLE001
        return exc
    return None


@pytest.mark.parametrize(
    "exc_info",
    [
        pytest.param((ValueError, "not an exception", None), id="value-not-an-exception"),
        pytest.param(True, id="flag-not-a-tuple"),
        pytest.param((), id="empty-tuple"),
        pytest.param((ValueError,), id="short-tuple"),
    ],
)
def test_a_log_record_without_an_exception_object_is_ignored(exc_info: object) -> None:
    """No exception object means nothing to capture: neither a hook failure nor an error in the host's log call."""
    sink = TestSessionSink("master")
    handler = pytest_plugin._ExceptionHandler(sink)  # pyright: ignore[reportPrivateUsage]
    record = logging.makeLogRecord({"msg": "logged", "exc_info": exc_info, "exc_text": "cached"})
    attempt = sink.begin_test("test_x.py::test_logs")
    token = TEST.set(("test_x.py::test_logs", attempt, "call"))
    try:
        raised = _emit(handler, record)
    finally:
        TEST.reset(token)
    assert raised is None
    assert sink.facts.warnings == []


def test_a_log_record_with_its_exception_in_a_list_is_counted() -> None:
    """A record built by hand may hold ``exc_info`` as a list: its exception is captured as from a tuple."""
    sink = TestSessionSink("master")
    handler = pytest_plugin._ExceptionHandler(sink)  # pyright: ignore[reportPrivateUsage]
    record = logging.makeLogRecord({"msg": "logged", "exc_info": [ValueError, ValueError("x"), None]})
    attempt = sink.begin_test("test_x.py::test_logs")
    token = TEST.set(("test_x.py::test_logs", attempt, "call"))
    try:
        _emit(handler, record)
    finally:
        TEST.reset(token)
    assert sink.current_test is not None
    phase = sink.current_test.phases.get("call")
    assert (phase.exceptions if phase is not None else 0) == 1


def test_an_adapter_hook_failure_is_recorded_under_the_sink_lock() -> None:
    """The adapter's hooks record through the sink, under its lock, like the sink's own."""
    sink = TestSessionSink("master")
    probe = LockProbe(sink._lock)  # pyright: ignore[reportPrivateUsage]
    sink.facts.sources = probe  # type: ignore[assignment]
    pytest_plugin._record_hook_failure(sink, RuntimeError("x"))  # pyright: ignore[reportPrivateUsage]
    assert probe.held == [True]
