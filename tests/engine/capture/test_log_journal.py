"""W5a P-log: one ``log`` journal event per WARN-or-above log record the log handler sees (BootUI
``RuntimeJournalLogAppender.append`` offers a ``LogPayload`` event): logger, level, the unformatted template, the
exception class; never the formatted message or an argument."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import otel
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, internal
from sharpit.engine.capture.logtail import SharpitLogHandler

ARG_CANARY = "zq-arg-canary-31"
OBJECT_CANARY = "zq-object-canary-43"
SECRET_CANARY = "zq-secret-canary-57"
ENVELOPE = {"source", "epochMillis", "durationNanos", "traceId", "thread", "requestId", "failedOrSlow"}
PAYLOAD = {"logger", "level", "template", "exceptionClass"}
ORDERS = "com.example.orders.OrderService"


class Teapot(Exception):
    pass


class Opaque:
    def __str__(self) -> str:
        return OBJECT_CANARY


@pytest.fixture
def installed() -> Iterator[list[Any]]:
    handles: list[Any] = []
    yield handles
    for handle in handles:
        handle.uninstall_capture()


def _install(handles: list[Any], sources: tuple[str, ...] = ("log",), **options: Any) -> Any:
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=sources, **options
    )
    handles.append(handle)
    return handle


def _handler(handle: Any) -> SharpitLogHandler:
    handler = handle.context.capture.wiring.log_handler
    assert handler is not None
    return handler


def _emit(
    handle: Any,
    msg: object,
    *args: object,
    level: int = logging.WARNING,
    name: str = ORDERS,
    exc_info: Any = None,
) -> None:
    record = logging.LogRecord(name, level, __file__, 1, msg, args or None, exc_info)
    _handler(handle).handle(record)


def _records(handle: Any) -> tuple[dict[str, object], ...]:
    journal = handle.context.capture.journal
    assert journal is not None
    return journal.records("log")


def _info(handle: Any, request_id: str) -> RequestInfo:
    return RequestInfo(request_id, handle.context.context_id, "GET", "/x", None, 0, None)


def _offered_by(handle: Any, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Every event the producer built, as built, before any read-time masking."""
    journal = handle.context.capture.journal
    offered: list[dict[str, object]] = []
    real_offer = journal.offer_flat

    def spy(event: dict[str, object]) -> bool:
        offered.append(dict(event))
        return real_offer(event)

    monkeypatch.setattr(journal, "offer_flat", spy)
    return offered


# ported: RuntimeJournalLogAppenderTests.recordsWarningsAndErrorsWithTheirTemplateAndRequestButNeverTheirArguments
def test_log_journal_event_offered_once_per_record_with_bootui_fields(installed: list[Any]) -> None:
    handle = _install(installed)
    token = REQUEST.set(_info(handle, "0123456789abcdef"))
    try:
        _emit(handle, "Order %s placed", 42, level=logging.INFO)  # below WARN: BootUI records WARN and above only
        _emit(handle, "Payment for order %s retried with code %s", 42, "secret-code")
        try:
            raise Teapot("boom")
        except Teapot:
            _emit(handle, "Order %s failed", 43, level=logging.ERROR, exc_info=sys.exc_info())
    finally:
        REQUEST.reset(token)
    assert len(_records(handle)) == 2  # the INFO record is not offered
    warned, errored = _records(handle)
    assert set(warned) == ENVELOPE | PAYLOAD
    assert warned["source"] == "log"
    assert warned["logger"] == ORDERS
    assert warned["level"] == "WARN"
    assert warned["template"] == "Payment for order %s retried with code %s"
    assert warned["exceptionClass"] is None
    assert warned["requestId"] == "0123456789abcdef"
    assert warned["durationNanos"] == -1
    assert warned["failedOrSlow"] is False
    assert isinstance(warned["thread"], str)
    assert errored["level"] == "ERROR"
    assert errored["exceptionClass"] == f"{__name__}.Teapot"
    assert errored["failedOrSlow"] is True


@pytest.mark.parametrize("exposure", ["MASKED", "FULL", "METADATA_ONLY"])
def test_log_journal_template_is_the_unformatted_msg_and_an_argument_canary_never_reaches_the_journal(
    exposure: str, monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _install(installed, expose_values=exposure)
    offered = _offered_by(handle, monkeypatch)
    _emit(handle, "retry %s for %s", ARG_CANARY, Opaque())
    _emit(handle, Opaque(), ARG_CANARY)  # an object as msg: its class, never its str()
    assert len(offered) == 2
    dumped = json.dumps(offered) + json.dumps(_records(handle))
    assert ARG_CANARY not in dumped
    assert OBJECT_CANARY not in dumped
    withheld = exposure == "METADATA_ONLY"  # the text is withheld, as the log tail's messageOmitted
    assert offered[1]["template"] == (None if withheld else "Opaque")
    assert offered[0]["template"] == (None if withheld else "retry %s for %s")


def test_log_journal_template_secret_is_masked_before_offer(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _install(installed)
    offered = _offered_by(handle, monkeypatch)
    _emit(handle, f"login failed password={SECRET_CANARY} for %s", "u")
    assert len(offered) == 1
    assert SECRET_CANARY not in json.dumps(offered)


def test_log_journal_template_is_as_visible_as_the_log_tail_line_at_full(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _install(installed, expose_values="FULL")
    offered = _offered_by(handle, monkeypatch)
    _emit(handle, "disk %s almost full")
    assert len(offered) == 1
    assert handle.context.capture.log_tail.recent()[0]["message"] == offered[0]["template"]


def test_log_journal_template_cut_at_500(installed: list[Any]) -> None:
    handle = _install(installed)
    _emit(handle, "x" * 800)
    _emit(handle, "y" * 500)
    assert len(_records(handle)) == 2
    cut, whole = _records(handle)
    assert cut["template"] == "x" * 500  # LogPayload.MAX_TEMPLATE_LENGTH
    assert whole["template"] == "y" * 500


def test_log_journal_warning_is_warn_and_critical_is_error(installed: list[Any]) -> None:
    handle = _install(installed)
    for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL):
        _emit(handle, "m", level=level)
    assert [(r["level"], r["failedOrSlow"]) for r in _records(handle)] == [
        ("WARN", False),
        ("ERROR", True),
        ("ERROR", True),
    ]


def test_log_journal_exception_class_from_exc_info(installed: list[Any]) -> None:
    handle = _install(installed)
    _emit(handle, "a", exc_info=(None, None, None))
    _emit(handle, "b", exc_info=(Teapot, Teapot("secret-text"), None))
    assert len(_records(handle)) == 2
    plain, classed = _records(handle)
    assert plain["exceptionClass"] is None
    assert classed["exceptionClass"] == f"{__name__}.Teapot"
    assert "secret-text" not in json.dumps(classed)


def test_log_journal_not_offered_for_sharpit_internal_work_or_sharpit_loggers(installed: list[Any]) -> None:
    handle = _install(installed)
    with internal():
        _emit(handle, "internal work")
    _emit(handle, "own logger", name="sharpit.engine.thing")
    _emit(handle, "own root", name="sharpit")
    assert _records(handle) == ()
    _emit(handle, "control, outside")
    _emit(handle, "other", name="sharpitx.app")  # a name that merely starts with sharpit: the application's
    assert len(_records(handle)) == 2


def test_log_journal_not_offered_when_source_disabled(installed: list[Any]) -> None:
    disabled = _install(installed, sources=("http",))
    _emit(disabled, "dropped")
    assert _records(disabled) == ()
    assert disabled.context.capture.journal.status()["dropped"] == {"log": 1}
    enabled = _install(installed)  # control: the same record is offered when enabled
    _emit(enabled, "kept")
    assert len(_records(enabled)) == 1


def test_log_journal_not_offered_when_journal_disabled(installed: list[Any]) -> None:
    handle = _install(installed, runtime_journal_enabled=False)
    _emit(handle, "nothing to offer to")
    assert handle.context.capture.journal is None
    control = _install(installed)  # the same record is offered when the journal is on
    _emit(control, "nothing to offer to")
    assert len(_records(control)) == 1
    assert [line["message"] for line in handle.context.capture.log_tail.recent()] == ["nothing to offer to"]


def test_log_journal_carries_the_request_id_of_this_install_only(installed: list[Any]) -> None:
    ours, theirs = _install(installed), _install(installed)
    token = REQUEST.set(_info(theirs, "r-theirs"))
    try:
        _emit(ours, "inside another install's request")
    finally:
        REQUEST.reset(token)
    token = REQUEST.set(_info(ours, "r-ours"))
    try:
        _emit(ours, "inside ours")
    finally:
        REQUEST.reset(token)
    _emit(ours, "outside any request")
    assert [r["requestId"] for r in _records(ours)] == [None, "r-ours", None]


def test_log_journal_event_carries_the_trace_id_in_flight(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _install(installed)
    monkeypatch.setattr(otel, "current_trace_id", lambda: "0af7651916cd43dd8448eb211c80319c")
    _emit(handle, "traced")
    assert len(_records(handle)) == 1
    assert _records(handle)[0]["traceId"] == "0af7651916cd43dd8448eb211c80319c"


def test_log_journal_reentrant_log_is_dropped_and_counted(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _install(installed)
    journal = handle.context.capture.journal
    real_append = journal._append  # pyright: ignore[reportPrivateUsage]
    fired: list[bool] = []

    def logging_append(event: Any, store: Any) -> bool:
        if not fired:
            fired.append(True)
            _emit(handle, "logged from inside the offer")  # a record raised while the journal appends
        return real_append(event, store)

    monkeypatch.setattr(journal, "_append", logging_append)
    _emit(handle, "outer")
    assert [r["template"] for r in _records(handle)] == ["outer"]
    assert journal.status()["dropped"] == {"reentrant": 1}


def test_log_journal_a_failing_build_never_reaches_the_host(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _install(installed)

    def broken() -> str | None:
        raise RuntimeError("build failed")

    monkeypatch.setattr(otel, "current_trace_id", broken)
    escaped: list[Exception] = []
    try:
        _emit(handle, "host log call")
    except Exception as error:  # noqa: BLE001 - the defect: a broken build reaches the host
        escaped.append(error)
    assert escaped == []
    assert _records(handle) == ()
    assert [line["message"] for line in handle.context.capture.log_tail.recent()] == ["host log call"]
    monkeypatch.undo()
    _emit(handle, "control")  # the handler and journal still work
    assert [r["template"] for r in _records(handle)] == ["control"]


def test_log_journal_a_failing_offer_never_reaches_the_host(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _install(installed)

    def refuse(_event: dict[str, object]) -> bool:
        raise RuntimeError("journal down")

    journal = handle.context.capture.journal
    real_offer = journal.offer_flat
    monkeypatch.setattr(journal, "offer_flat", refuse)
    _emit(handle, "host log call")
    assert len(handle.context.capture.log_tail.recent()) == 1
    monkeypatch.setattr(journal, "offer_flat", real_offer)
    _emit(handle, "control")
    assert len(_records(handle)) == 1


def test_log_journal_a_real_logger_call_is_offered_once(installed: list[Any]) -> None:
    handle = _install(installed)
    handle.context.capture.wiring._attach_logging()  # pyright: ignore[reportPrivateUsage]
    logging.getLogger("com.example.real").warning("real %s", ARG_CANARY)
    assert [(r["logger"], r["template"]) for r in _records(handle)] == [("com.example.real", "real %s")]
