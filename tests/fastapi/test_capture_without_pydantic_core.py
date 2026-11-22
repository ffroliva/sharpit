from __future__ import annotations

import logging
import sys
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError

from sharpit.fastapi import capture


class _Store:
    def __init__(self) -> None:
        self.recorded: list[tuple[BaseException, str]] = []

    def record(self, exc: BaseException, source: str, *_args: Any, **_kwargs: Any) -> None:
        self.recorded.append((exc, source))


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


def test_host_exception_is_recorded_when_pydantic_core_is_unavailable(no_pydantic_core: None) -> None:
    store = _Store()
    exc = RuntimeError("host failure")

    raised = _raised(lambda: capture._record_exception(store, exc, "handler", None, None, None, None))  # pyright: ignore[reportArgumentType,reportPrivateUsage]

    assert raised is None

    assert store.recorded == [(exc, "handler")]


def test_validation_error_is_recorded_without_diagnostics_when_pydantic_core_is_unavailable(
    no_pydantic_core: None,
) -> None:
    store = _Store()
    exc = RequestValidationError([])

    raised = _raised(lambda: capture._record_exception(store, exc, "handler", None, None, None, None))  # pyright: ignore[reportArgumentType,reportPrivateUsage]

    assert raised is None

    assert store.recorded == [(exc, "handler")]


def test_logged_exception_is_recorded_when_pydantic_core_is_unavailable(no_pydantic_core: None) -> None:
    store = _Store()
    exc = RuntimeError("logged failure")
    record = logging.LogRecord("host", logging.ERROR, __file__, 1, "boom", None, (RuntimeError, exc, None))

    raised = _raised(lambda: capture._record_logged(store, record))  # pyright: ignore[reportArgumentType,reportPrivateUsage]

    assert raised is None

    assert store.recorded == [(exc, "log")]
