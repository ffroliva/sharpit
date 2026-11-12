"""W5a P-exception: one ``exception`` journal event per captured exception occurrence (BootUI ``ExceptionStore.record``
offers ``RuntimeEvent.of(JournalSource.EXCEPTION, ..., ExceptionPayload)``): class, group, signature, types; never text."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, internal

MESSAGE_CANARY = "zq-message-canary-17"
ARGS_CANARY = "zq-args-canary-29"
ENVELOPE = {"source", "epochMillis", "durationNanos", "traceId", "thread", "requestId"}
PAYLOAD = {"groupId", "exceptionClass", "signature", "types", "logged"}


class Teapot(Exception):
    pass


class Brewing(Teapot):
    pass


def _install(sources: tuple[str, ...] = ("exception",), **options: Any) -> Any:
    app = FastAPI()

    @app.get("/boom")
    async def boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise Brewing(f"{MESSAGE_CANARY} {ARGS_CANARY}", ARGS_CANARY)

    @app.get("/rethrow")
    async def rethrow() -> None:  # pyright: ignore[reportUnusedFunction]
        raise Brewing(MESSAGE_CANARY)

    @app.exception_handler(Brewing)
    async def reraise(_request: Any, exc: Brewing) -> None:  # pyright: ignore[reportUnusedFunction]
        raise exc

    handle = install(
        app, enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=sources, **options
    )
    return TestClient(app, raise_server_exceptions=False), handle


def _records(handle: Any) -> tuple[dict[str, object], ...]:
    journal = handle.context.capture.journal
    assert journal is not None
    return journal.records("exception")


def _raised(exc: Exception) -> Exception:
    try:
        raise exc
    except Exception as caught:  # noqa: BLE001
        return caught


def _info(handle: Any, request_id: str) -> RequestInfo:
    return RequestInfo(request_id, handle.context.context_id, "GET", "/x", None, 0, None)


# ported: ExceptionStoreTests.publishesEachRecordedExceptionToTheJournalWithItsClassGroupAndSignatureButNoMessage
def test_exception_journal_event_offered_once_per_captured_exception_with_bootui_fields() -> None:
    handle = _install()[1]
    store = handle.context.capture.exceptions
    store.record(_raised(Brewing("x")), "handler", _info(handle, "r1"), "worker")
    records = _records(handle)
    assert len(records) == 1
    record = records[0]
    assert set(record) == ENVELOPE | PAYLOAD
    assert record["source"] == "exception"
    assert record["exceptionClass"] == f"{__name__}.Brewing"
    assert record["groupId"] == store.report()["groups"][0]["id"]
    assert record["types"] == [f"{__name__}.Brewing", f"{__name__}.Teapot"]
    assert record["logged"] is False
    assert record["thread"] == "worker"
    assert record["requestId"] == "r1"
    assert record["durationNanos"] == -1
    assert isinstance(record["signature"], str)
    assert len(str(record["signature"])) == 16


def test_exception_journal_signature_ignores_line_numbers_and_the_log_source_is_logged() -> None:
    handle = _install()[1]
    store = handle.context.capture.exceptions

    def fail(n: int) -> Exception:
        try:
            if n:
                raise Brewing("a")
            raise Brewing("b")
        except Exception as caught:  # noqa: BLE001
            return caught

    store.record(fail(1), "log", None, "t")
    store.record(fail(0), "handler", None, "t")
    first, second = _records(handle)
    assert first["signature"] == second["signature"]
    assert first["groupId"] != second["groupId"]
    assert first["logged"] is True
    assert second["logged"] is False


# ported: ExceptionStoreTests.theJournalEventNeverCarriesTheMessage
@pytest.mark.parametrize("exposure", ["MASKED", "FULL", "METADATA_ONLY"])
def test_exception_journal_message_and_args_canary_never_reaches_the_journal(exposure: str) -> None:
    client, handle = _install(expose_values=exposure)
    assert client.get("/boom").status_code == 500
    records = _records(handle)
    assert len(records) == 1
    assert MESSAGE_CANARY not in json.dumps(records)
    assert ARGS_CANARY not in json.dumps(records)


def test_exception_journal_event_not_offered_for_sharpit_internal_work() -> None:
    handle = _install()[1]
    with internal():
        handle.context.capture.exceptions.record(_raised(Brewing("x")), "handler", None, "t")
    assert _records(handle) == ()
    handle.context.capture.exceptions.record(_raised(Brewing("y")), "handler", None, "t")  # control: outside, offered
    assert len(_records(handle)) == 1


def test_exception_journal_event_not_offered_when_source_disabled() -> None:
    handle = _install(sources=("http",))[1]
    handle.context.capture.exceptions.record(_raised(Brewing("x")), "handler", None, "t")
    assert _records(handle) == ()
    assert handle.context.capture.exceptions.report()["totalExceptions"] == 1
    assert handle.context.capture.journal.status()["dropped"] == {"exception": 1}


def test_exception_journal_event_carries_the_request_id_of_this_install_only() -> None:
    ours, theirs = _install()[1], _install()[1]
    store = ours.context.capture.exceptions
    token = REQUEST.set(_info(theirs, "r-theirs"))
    try:
        store.record(_raised(Brewing("x")), "log", REQUEST.get(), "t")
    finally:
        REQUEST.reset(token)
    store.record(_raised(Brewing("y")), "log", _info(ours, "r-ours"), "t")
    assert [r["requestId"] for r in _records(ours)] == [None, "r-ours"]


def test_exception_journal_event_not_offered_twice_for_a_reraising_handler() -> None:
    client, handle = _install()
    assert client.get("/rethrow").status_code == 500
    assert len(_records(handle)) == 1
    assert handle.context.capture.exceptions.report()["totalExceptions"] == 1
