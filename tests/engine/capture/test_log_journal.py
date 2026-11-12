"""W5a P-log: one ``log`` journal event per WARN-or-above log record the log handler sees (BootUI
``RuntimeJournalLogAppender.append`` offers a ``LogPayload`` event): logger, level, the unformatted template, the
exception class; never the formatted message or an argument."""

from __future__ import annotations

import json
import logging
import sys
import tracemalloc
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import otel
from sharpit.engine.capture import logtail
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, internal
from sharpit.engine.capture.logtail import SharpitLogHandler
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.kinds import errors_behind_2xx
from sharpit.engine.collectors.insights.service import insights_service
from sharpit.engine.masking import Masker

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


@pytest.mark.parametrize("exposure", ["MASKED", "FULL", "METADATA_ONLY"])
def test_log_journal_an_f_string_message_is_the_template_shown_masked_or_full_and_withheld_at_metadata_only(
    exposure: str, installed: list[Any]
) -> None:
    handle = _install(installed, expose_values=exposure)
    _emit(handle, f"retry for {ARG_CANARY}")  # an f-string is msg: its formatted text IS the template (LogPayload)
    (event,) = _records(handle)
    assert (ARG_CANARY in str(event["template"])) == (exposure != "METADATA_ONLY")
    assert (event["template"] is None) == (exposure == "METADATA_ONLY")


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


class _Calls:
    """The texts that go through ``logtail.error_text``, the masking the log tail and the template share."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.texts: list[str] = []
        real = logtail.error_text

        def counting(masker: Any, text: Any, dialect: Any) -> Any:
            self.texts.append(str(text))
            return real(masker, text, dialect)

        monkeypatch.setattr(logtail, "error_text", counting)


def _cache_size(handle: Any) -> int:
    cache = getattr(_handler(handle), "template_cache", None)
    assert cache is not None, "the handler has no template cache"
    return cache.cache_info().currsize


def _journal_only(installed: list[Any], **options: Any) -> Any:
    """Both log panels off: only the journal's ``log`` source needs the handler, so no tail line is built."""
    return _install(installed, panels={"log-tail": {"enabled": False}, "exceptions": {"enabled": False}}, **options)


def test_log_journal_handler_is_installed_for_the_log_source_with_both_log_panels_off(installed: list[Any]) -> None:
    handle = _journal_only(installed)
    assert handle.context.capture.log_tail is None
    _emit(handle, "warned with no log panel enabled")
    assert [r["template"] for r in _records(handle)] == ["warned with no log panel enabled"]


def test_log_journal_no_handler_when_log_is_not_an_enabled_source_and_both_log_panels_are_off(
    installed: list[Any],
) -> None:
    handle = _journal_only(installed, sources=("http",))
    assert handle.context.capture.wiring.log_handler is None
    kept = _install(installed, sources=("http",), panels={"exceptions": {"enabled": False}})  # a log panel: installed
    assert kept.context.capture.wiring.log_handler is not None


def test_errors_behind_2xx_real_install_with_both_log_panels_off_journals_the_error_but_hides_it(
    installed: list[Any],
) -> None:
    """BootUI ``InsightsSnapshot.visible(LOG)``: LOG belongs to the log-tail panel (``JournalSourcePanels``), so with it
    off the producer still journals the event (as BootUI's appender) but insights do not count it (W5c I-visible)."""
    assert "log" in snapshot_module.PRODUCED_SOURCES  # W5a P-log
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        panels={
            "log-tail": {"enabled": False},
            "exceptions": {"enabled": False},
            "transactions": {"enabled": False},  # W5a P-transaction: the transaction source is evidence too
        },
    )
    installed.append(handle)

    @app.get("/pay")
    def pay() -> dict[str, bool]:  # the 2xx hides a logged ERROR
        logging.getLogger(ORDERS).error("payment failed for %s", ARG_CANARY)
        return {"ok": True}

    handle.context.capture.wiring._attach_logging()  # pyright: ignore[reportPrivateUsage]
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/pay").status_code == 200
    assert [r["level"] for r in _records(handle)] == ["ERROR"] * 3  # journaled
    report = insights_service(handle.context).report()
    check = next(c for c in report["checks"] if c["kind"] == "errors-behind-2xx")
    assert check["status"] == "NOT_APPLICABLE"  # hidden: no evidence source is visible
    assert check["reason"] == errors_behind_2xx.NOT_APPLICABLE  # BootUI ErrorsBehind2xx.notApplicable, whole text
    assert [o for o in report["observations"] if o["kind"] == "errors-behind-2xx"] == []
    assert ARG_CANARY not in json.dumps(report)


def test_log_journal_a_record_of_a_source_not_accepted_is_counted_without_masking_or_building(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _install(installed, sources=("http",))  # the log tail stays on: the handler is installed for it
    handler = _handler(handle)
    built: list[bool] = []
    real_build = handler._journal_event  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(handler, "_journal_event", lambda record: built.append(True) or real_build(record))
    calls = _Calls(monkeypatch)
    _emit(handle, "not accepted %s", 1)
    assert built == []
    assert len(calls.texts) == 1  # the log tail line only
    assert handle.context.capture.journal.status()["dropped"] == {"log": 1}


def test_log_journal_a_16_kb_message_masks_only_the_head(monkeypatch: pytest.MonkeyPatch, installed: list[Any]) -> None:
    handle = _journal_only(installed)
    calls = _Calls(monkeypatch)
    _emit(handle, "x" * 16_000)
    (event,) = _records(handle)
    assert event["template"] == "x" * 500
    assert [len(t) <= 500 + 4_096 for t in calls.texts] == [True]


@pytest.mark.parametrize("secret_at", [470, 485, 495, 499])
def test_log_journal_a_secret_straddling_the_cut_is_masked(
    secret_at: int, monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _journal_only(installed)
    offered = _offered_by(handle, monkeypatch)  # as built, before the read-time mask
    _emit(handle, "a" * secret_at + f" password={SECRET_CANARY}-{'z' * 600}")
    (event,) = offered
    assert len(str(event["template"])) <= 500
    assert SECRET_CANARY[:8] not in str(event["template"])


def test_log_journal_a_warn_logged_inside_the_build_is_one_event_and_one_counted_drop(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _journal_only(installed)
    handler = _handler(handle)
    real_build = handler._journal_event  # pyright: ignore[reportPrivateUsage]
    built: list[str] = []

    def logging_build(record: logging.LogRecord) -> Any:
        built.append(str(record.msg))
        if len(built) == 1:
            _emit(handle, "logged from inside the build")
        return real_build(record)

    monkeypatch.setattr(handler, "_journal_event", logging_build)
    _emit(handle, "outer")
    assert built == ["outer"]  # the nested record was not built
    assert [r["template"] for r in _records(handle)] == ["outer"]
    assert handle.context.capture.journal.status()["dropped"] == {"reentrant": 1}


def test_log_journal_a_nested_record_is_counted_without_building_an_event(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _journal_only(installed)
    journal = handle.context.capture.journal
    handler = _handler(handle)
    real_build = handler._journal_event  # pyright: ignore[reportPrivateUsage]
    real_append = journal._append  # pyright: ignore[reportPrivateUsage]
    built: list[str] = []

    def logging_append(event: Any, store: Any) -> bool:
        _emit(handle, "from inside the offer")
        return real_append(event, store)

    monkeypatch.setattr(handler, "_journal_event", lambda r: built.append(str(r.msg)) or real_build(r))
    monkeypatch.setattr(journal, "_append", logging_append)
    _emit(handle, "outer")
    assert built == ["outer"]
    assert journal.status()["dropped"] == {"reentrant": 1}


def test_log_journal_a_template_with_arguments_is_masked_once(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _journal_only(installed)
    calls = _Calls(monkeypatch)
    for number in range(3):
        _emit(handle, "Payment for order %s retried", number)
    assert calls.texts == ["Payment for order %s retried"]  # a hit masks nothing new
    assert [r["template"] for r in _records(handle)] == ["Payment for order %s retried"] * 3


def test_log_journal_a_template_without_arguments_is_never_cached(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _journal_only(installed)
    calls = _Calls(monkeypatch)
    for _ in range(2):
        _emit(handle, f"order {ARG_CANARY} failed")  # an f-string: unmasked text must not be held in memory
    assert len(calls.texts) == 2
    assert _cache_size(handle) == 0


def test_log_journal_the_template_cache_is_capped(installed: list[Any]) -> None:
    handle = _journal_only(installed)
    for number in range(300):
        _emit(handle, f"call site {number} failed with %s", 1)
    assert len(_records(handle)) == 300
    assert _cache_size(handle) <= 256


def test_log_journal_a_cached_template_follows_the_maskers_never_shown_set(
    monkeypatch: pytest.MonkeyPatch, installed: list[Any]
) -> None:
    handle = _journal_only(installed)
    offered = _offered_by(handle, monkeypatch)  # as built: the journal masks again at read time
    template = "found zq-identity-key-text-61 in %s"
    _emit(handle, template, 1)
    handle.context.masker.identity_key = b"zq-identity-key-text-61"  # set after install, as install() does
    _emit(handle, template, 1)
    shown, hidden = offered
    assert shown["template"] == template
    assert "zq-identity-key-text-61" not in str(hidden["template"])


def test_log_journal_the_template_cache_does_not_keep_the_whole_text_alive(installed: list[Any]) -> None:
    handle = _journal_only(installed)
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for number in range(256):
            _emit(handle, f"call site {number:04d} " + "x" * 1_000_000 + " %s", 1)
        retained = tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()
    assert retained < 20_000_000  # the masked window of 256 templates, not 256 one-megabyte texts


def test_masker_has_no_public_exposure_property() -> None:
    assert not hasattr(Masker, "exposure")
