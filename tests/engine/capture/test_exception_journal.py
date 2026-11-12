"""W5a P-exception: one ``exception`` journal event per captured exception occurrence (BootUI ``ExceptionStore.record``
offers an ``ExceptionPayload`` event): class, group, signature, types; no text."""

from __future__ import annotations

import json
from typing import Any

from sharpit.engine.capture import exceptions as exceptions_module

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, internal

MESSAGE_CANARY = "zq-message-canary-17"
ARGS_CANARY = "zq-args-canary-29"
ENVELOPE = {"source", "epochMillis", "durationNanos", "traceId", "thread", "requestId", "failedOrSlow"}
PAYLOAD = {"groupId", "exceptionClass", "signature", "types", "logged"}


class Teapot(Exception):
    pass


class Brewing(Teapot):
    pass


class PoolTimeout(Brewing):
    pass


def _with_cause(outer: Exception, inner: Exception) -> Exception:
    outer.__cause__ = inner
    return _raised(outer)


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


# ported: RecorderPublishingTests.exceptionOccurrencesPublishTheirGroupAndClassButNeverTheirMessage
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
    assert record["failedOrSlow"] is True  # BootUI offers every exception event with failedOrSlow=true
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


# ported: RecorderPublishingTests.exceptionOccurrencesPublishTheirGroupAndClassButNeverTheirMessage (the message part)
@pytest.mark.parametrize("exposure", ["MASKED", "FULL", "METADATA_ONLY"])
def test_exception_journal_message_and_args_canary_never_reaches_the_journal(
    exposure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, handle = _install(expose_values=exposure)
    journal = handle.context.capture.journal
    offered: list[dict[str, object]] = []
    real_offer = journal.offer

    def spy(event: dict[str, object]) -> None:
        offered.append(dict(event))  # the event as the producer built it, before any read-time masking
        real_offer(event)

    monkeypatch.setattr(journal, "offer", spy)
    assert client.get("/boom").status_code == 500
    assert len(offered) == 1
    assert MESSAGE_CANARY not in json.dumps(offered)
    assert ARGS_CANARY not in json.dumps(offered)
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


# ported: RecorderPublishingTests.exceptionMetadataIncludesDeepCausesAndSuperclassNamesWithoutMessages
def test_exception_journal_types_list_the_deepest_cause_first_with_superclasses_and_no_messages() -> None:
    handle = _install()[1]
    exc = _with_cause(RuntimeError("secret-wrapper"), PoolTimeout("secret-cause"))
    handle.context.capture.exceptions.record(exc, "handler", None, "worker")
    record = _records(handle)[0]
    assert record["types"] == [f"{__name__}.PoolTimeout", f"{__name__}.Brewing", f"{__name__}.Teapot", "RuntimeError"]
    assert record["exceptionClass"] == "RuntimeError"
    assert "secret" not in json.dumps(record)


def test_exception_journal_types_are_capped_at_sixteen() -> None:
    handle = _install()[1]
    base: type[Exception] = Exception
    for depth in range(20):
        base = type(f"Level{depth}", (base,), {})
    handle.context.capture.exceptions.record(_raised(base("x")), "handler", None, "t")
    types = _records(handle)[0]["types"]
    assert isinstance(types, list)
    assert len(types) == 16  # ExceptionPayload.MAX_TYPES
    assert types[0].endswith("Level19")


def test_exception_journal_types_walk_at_most_eight_causes() -> None:
    handle = _install()[1]
    classes = [type(f"Chain{i}", (Exception,), {}) for i in range(12)]
    exc: Exception = _raised(classes[11]("x"))
    for cls in reversed(classes[:11]):  # Chain0 is the outermost, each one's cause is the next
        exc = _with_cause(cls("x"), exc)
    handle.context.capture.exceptions.record(exc, "handler", None, "t")
    types = _records(handle)[0]["types"]
    assert types == [f"{__name__}.Chain{i}" for i in range(8, -1, -1)]  # root and 8 causes, deepest of those first


def test_exception_journal_exception_group_types_come_from_the_first_leaf_chain() -> None:
    handle = _install()[1]
    group = _raised(ExceptionGroup("g", [_with_cause(RuntimeError("a"), PoolTimeout("b")), KeyError("k")]))
    handle.context.capture.exceptions.record(group, "handler", None, "t")
    record = _records(handle)[0]
    assert record["types"] == [f"{__name__}.PoolTimeout", f"{__name__}.Brewing", f"{__name__}.Teapot", "RuntimeError"]


def test_exception_journal_a_failing_event_build_keeps_the_stores_record(monkeypatch: pytest.MonkeyPatch) -> None:
    handle = _install()[1]
    store = handle.context.capture.exceptions

    def broken(*_args: object) -> list[str]:
        raise RuntimeError("build failed")

    monkeypatch.setattr(exceptions_module, "_types", broken)
    store.record(_raised(Brewing("x")), "handler", None, "t")  # nothing escapes to the host
    assert store.report()["totalExceptions"] == 1
    assert _records(handle) == ()
    monkeypatch.undo()
    store.record(_raised(Teapot("y")), "handler", None, "t")  # control: the store and journal still work
    assert store.report()["totalExceptions"] == 2
    assert len(_records(handle)) == 1


def test_exception_journal_a_failing_offer_keeps_the_stores_record(monkeypatch: pytest.MonkeyPatch) -> None:
    handle = _install()[1]
    store = handle.context.capture.exceptions

    def refuse(_event: dict[str, object]) -> None:
        raise RuntimeError("journal down")

    monkeypatch.setattr(handle.context.capture.journal, "offer", refuse)
    store.record(_raised(Brewing("x")), "handler", None, "t")
    assert store.report()["totalExceptions"] == 1
