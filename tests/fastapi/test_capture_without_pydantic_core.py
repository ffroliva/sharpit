from __future__ import annotations

import logging
import sys
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError

import sharpit
from fastapi import FastAPI
from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.fastapi import capture


def _raised(call: Any) -> BaseException | None:
    try:
        call()
    except BaseException as exc:  # noqa: BLE001 - the test asserts on what the hook let escape
        return exc
    return None


@pytest.fixture
def no_pydantic_core(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("pydantic_core", "pydantic_core.core_schema"):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, "sharpit.fastapi.binding_diagnostics", raising=False)


@pytest.fixture
def store() -> ExceptionStore:
    handle = sharpit.install(FastAPI(), enabled="ON", show_banner=False)
    assert handle.context.capture.exceptions is not None
    return handle.context.capture.exceptions


def test_host_exception_is_recorded_when_pydantic_core_is_unavailable(
    no_pydantic_core: None, store: ExceptionStore
) -> None:
    exc = RuntimeError("host failure")

    raised = _raised(lambda: capture._record_exception(store, exc, "handler", None, None, None, None))  # pyright: ignore[reportPrivateUsage]

    assert raised is None

    groups = store.report()["groups"]
    assert len(groups) == 1
    group = groups[0]
    assert group["exceptionClassName"] == "RuntimeError"
    assert group["message"] == "host failure"
    assert group["lastSource"] == "handler"


def test_validation_error_is_recorded_without_diagnostics_when_pydantic_core_is_unavailable(
    no_pydantic_core: None, store: ExceptionStore
) -> None:
    exc = RequestValidationError([])

    raised = _raised(lambda: capture._record_exception(store, exc, "handler", None, None, None, None))  # pyright: ignore[reportPrivateUsage]

    assert raised is None

    groups = store.report()["groups"]
    assert len(groups) == 1
    group = groups[0]
    assert group["exceptionClassName"] == "fastapi.exceptions.RequestValidationError"
    assert group["message"] is None
    assert group["lastSource"] == "handler"


def test_logged_exception_is_recorded_when_pydantic_core_is_unavailable(
    no_pydantic_core: None, store: ExceptionStore
) -> None:
    exc = RuntimeError("logged failure")
    record = logging.LogRecord("host", logging.ERROR, __file__, 1, "boom", None, (RuntimeError, exc, None))

    raised = _raised(lambda: capture._record_logged(store, record))  # pyright: ignore[reportPrivateUsage]

    assert raised is None

    groups = store.report()["groups"]
    assert len(groups) == 1
    group = groups[0]
    assert group["exceptionClassName"] == "RuntimeError"
    assert group["message"] == "logged failure"
    assert group["lastSource"] == "log"
