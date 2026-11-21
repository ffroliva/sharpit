"""A swallowed exception raised by a test double is named as such (issue 68), without keeping its message."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from sharpit.engine.testsession.doubles import raised_by_test_double


def _caught(call: Callable[[], object]) -> BaseException:
    try:
        call()
    except Exception as exc:  # noqa: BLE001
        return exc
    raise AssertionError("nothing was raised")


async def _await_a_magic_mock() -> None:
    await MagicMock()  # type: ignore[misc]


async def _await_a_missing_key() -> None:
    await {}["missing"]


def test_awaiting_a_magic_mock_is_a_test_double() -> None:
    exc = _caught(lambda: asyncio.run(_await_a_magic_mock()))

    assert raised_by_test_double(exc) is True


def test_a_mock_that_raises_through_its_own_frames_is_a_test_double() -> None:
    mock = Mock(side_effect=ValueError("no help from the message"))

    exc = _caught(mock)

    assert raised_by_test_double(exc) is True


def test_an_async_mock_side_effect_is_a_test_double() -> None:
    mock = AsyncMock(side_effect=KeyError("plain"))

    exc = _caught(lambda: asyncio.run(mock()))

    assert raised_by_test_double(exc) is True


@pytest.mark.parametrize("message", ["Mock object has no attribute 'x'", "'AsyncMock' object is not iterable"])
def test_a_message_naming_a_double_is_a_test_double(message: str) -> None:
    assert raised_by_test_double(AttributeError(message)) is True


def test_an_application_error_is_not_a_test_double() -> None:
    exc = _caught(lambda: asyncio.run(_await_a_missing_key()))

    assert raised_by_test_double(exc) is False


@pytest.mark.parametrize("message", ["'int' object is not callable", "a mockup of the page", "Mocked!"])
def test_a_message_that_only_resembles_a_double_is_not_one(message: str) -> None:
    assert raised_by_test_double(TypeError(message)) is False


def test_an_exception_with_no_text_arguments_is_not_a_test_double() -> None:
    assert raised_by_test_double(OSError(2, "No such file")) is False
