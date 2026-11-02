"""The swallowed-handler predicate (spec 0.4.0 §5.5 F1): broad catch, no re-raise, no logger/warnings call."""

from __future__ import annotations

import textwrap

from sharpit.engine.testsession import swallowed
from sharpit.engine.testsession.swallowed import handler_swallows, is_programming_error


def _src(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


def _line_of(source: str, needle: str) -> int:
    return next(number for number, line in enumerate(source.splitlines(), 1) if needle in line)


def test_detects_bare_and_broad_catches() -> None:
    source = _src(
        """
        def a():
            try:
                pass
            except Exception:
                return 0

        def b():
            try:
                pass
            except BaseException:
                pass

        def c():
            try:
                pass
            except:
                return None

        def d():
            try:
                pass
            except (KeyError, Exception) as exc:
                return 0
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception:")) is True
    assert handler_swallows(source, _line_of(source, "except BaseException:")) is True
    assert handler_swallows(source, _line_of(source, "except:")) is True
    assert handler_swallows(source, _line_of(source, "except (KeyError, Exception)")) is True


def test_programming_error_types() -> None:
    assert is_programming_error(AttributeError("x")) is True
    assert is_programming_error(ModuleNotFoundError("x")) is True  # an ImportError, matched with isinstance
    assert is_programming_error(UnboundLocalError("x")) is True
    assert is_programming_error(ValueError("x")) is False
    assert (AttributeError, TypeError, NameError, ImportError, UnboundLocalError) == swallowed.PROGRAMMING_ERRORS
