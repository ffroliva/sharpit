"""Tests for frame inspection and call-site labels (Plan 2 Task 1)."""

from __future__ import annotations

import functools
import os
import sys
from types import FrameType
from typing import cast

import pytest

from sharpit.engine.capture import frames, sqltrace
from sharpit.engine.capture.frames import call_site_label, first_application_frame


class _FakeFrame:
    """A fake frame to simulate stack frames in tests."""

    def __init__(
        self,
        filename: str,
        back: object | None = None,
        module: str = "some_module",
        name: str = "some_func",
        lineno: int = 42,
    ) -> None:
        self.f_code = type("Code", (), {"co_filename": filename, "co_name": name, "co_qualname": name})()
        self.f_globals = {"__name__": module}
        self.f_lineno = lineno
        self.f_back = back


class Outer:
    class Inner:
        def method(self) -> str:
            frame = sys._getframe()
            return call_site_label(frame)


def test_the_first_application_frame_skips_the_stdlib_installed_packages_and_sharpit() -> None:
    app_frame = sys._getframe()
    sharpit_frame = _FakeFrame(frames.__file__, app_frame)
    pkg_frame = _FakeFrame("/venv/lib/site-packages/somepkg/mod.py", sharpit_frame)
    stdlib_frame = _FakeFrame(os.__file__, pkg_frame)

    result = first_application_frame(cast(FrameType, stdlib_frame))
    assert result is app_frame


def test_the_call_site_label_is_module_and_qualname_without_a_line() -> None:
    import tests.engine.capture.test_frames as tf

    label = tf.Outer.Inner().method()
    assert label == "tests.engine.capture.test_frames:Outer.Inner.method"


def test_an_async_session_statement_finds_its_frame_in_the_parent_greenlet() -> None:
    greenlet = pytest.importorskip("greenlet")

    def in_child() -> FrameType | None:
        lib_frame = _FakeFrame("/venv/lib/site-packages/sqlalchemy/orm/session.py", None)
        return first_application_frame(cast(FrameType, lib_frame))

    parent_frame = greenlet.greenlet(in_child).switch()
    assert parent_frame is not None
    assert parent_frame.f_code.co_name == "test_an_async_session_statement_finds_its_frame_in_the_parent_greenlet"


def _stack_1_helper() -> tuple[str | None, int]:
    frame = sys._getframe()
    return sqltrace.call_site(frame), frame.f_lineno


def _stack_2_helper() -> tuple[str | None, int]:
    frame = sys._getframe()
    wrapped = _FakeFrame("/venv/lib/site-packages/sqlalchemy/engine/base.py", frame)
    return sqltrace.call_site(cast(FrameType, wrapped)), frame.f_lineno


def test_sql_call_site_output_is_unchanged() -> None:
    greenlet = pytest.importorskip("greenlet")

    site1, line1 = _stack_1_helper()
    site2, line2 = _stack_2_helper()
    site3 = greenlet.greenlet(functools.partial(sqltrace.call_site, None)).switch()

    expected1 = f"{__name__}:_stack_1_helper:{line1}"
    expected2 = f"{__name__}:_stack_2_helper:{line2}"

    assert site1 == expected1
    assert site2 == expected2
    assert site3 is not None
    assert site3.startswith(f"{__name__}:test_sql_call_site_output_is_unchanged:")
