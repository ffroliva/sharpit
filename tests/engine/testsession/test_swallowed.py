"""The swallowed-handler predicate (spec 0.4.0 §5.5 F1): broad catch, no re-raise, no logger/warnings call."""

from __future__ import annotations

import dis
import textwrap
from types import CodeType

import pytest

from sharpit.engine.testsession import swallowed
from sharpit.engine.testsession.swallowed import handler_swallows, handler_swallows_code, is_programming_error


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


def _handler_offsets(code: CodeType) -> list[int]:
    return [i.offset for i in dis.get_instructions(code) if i.opname == "PUSH_EXC_INFO"]


def test_ignores_narrow_catch() -> None:
    source = _src(
        """
        def a():
            try:
                pass
            except ValueError:
                return 0
        """
    )
    assert handler_swallows(source, _line_of(source, "except ValueError:")) is False


def test_ignores_reraise() -> None:
    source = _src(
        """
        def a():
            try:
                pass
            except Exception:
                raise

        def b():
            try:
                pass
            except Exception as exc:
                raise RuntimeError("wrapped") from exc
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception:")) is False
    assert handler_swallows(source, _line_of(source, "except Exception as exc:")) is False


def test_ignores_logger_and_warnings_calls() -> None:
    source = _src(
        """
        def a():
            try:
                pass
            except Exception:
                logger.exception("failed")
                return 0

        def b():
            try:
                pass
            except BaseException:
                logging.error("failed")

        def c():
            try:
                pass
            except:
                warnings.warn("failed")
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception:")) is False
    assert handler_swallows(source, _line_of(source, "except BaseException:")) is False
    assert handler_swallows(source, _line_of(source, "except:")) is False


def test_ignores_unexecuted_nested_raise_and_logger() -> None:
    source = _src(
        """
        def a():
            try:
                pass
            except Exception:
                def unused():
                    raise
                return 0

        def b():
            try:
                pass
            except BaseException:
                async def unused():
                    logger.exception("failed")
                return 0

        def c():
            try:
                pass
            except:
                report = lambda: logger.exception("failed")
                return 0

        def d():
            try:
                pass
            except (Exception, KeyError):
                class Unused:
                    def method(self):
                        raise
                return 0

        def e():
            try:
                pass
            except (KeyError, Exception):
                def helper():
                    return 0
                raise
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception:")) is True, "nested def raise"
    assert handler_swallows(source, _line_of(source, "except BaseException:")) is True, "nested async def logger"
    assert handler_swallows(source, _line_of(source, "except:")) is True, "lambda logger"
    assert handler_swallows(source, _line_of(source, "except (Exception, KeyError):")) is True, "class method raise"
    assert handler_swallows(source, _line_of(source, "except (KeyError, Exception):")) is False, "direct raise"


def test_called_nested_scopes_are_followed() -> None:
    source = _src(
        """
        def a():
            try:
                pass
            except Exception:
                def helper():
                    raise
                helper()

        def b():
            try:
                pass
            except BaseException:
                def helper():
                    logger.exception("failed")
                helper()
                return 0

        async def c():
            try:
                pass
            except:
                async def helper():
                    raise
                await helper()

        def d():
            try:
                pass
            except (Exception, KeyError):
                report = lambda: logger.exception("failed")
                report()
                return 0

        def e():
            try:
                pass
            except (KeyError, Exception):
                (lambda: logger.exception("failed"))()
                return 0

        def f():
            try:
                pass
            except (Exception, ValueError):
                def helper():
                    raise
                def other():
                    return 0
                other()
                return 0
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception:")) is False, "called helper raises"
    assert handler_swallows(source, _line_of(source, "except BaseException:")) is False, "called helper logs"
    assert handler_swallows(source, _line_of(source, "except:")) is False, "awaited async helper raises"
    assert handler_swallows(source, _line_of(source, "except (Exception, KeyError):")) is False, "called lambda"
    assert handler_swallows(source, _line_of(source, "except (KeyError, Exception):")) is False, "inline lambda"
    assert handler_swallows(source, _line_of(source, "except (Exception, ValueError):")) is True, "uncalled raise"


def _nested() -> int:
    try:
        try:
            return {}["missing"]
        except KeyError:
            raise
    except Exception:
        return 0


def test_nested_handler_uses_handled_location() -> None:
    inner, outer = _handler_offsets(_nested.__code__)[:2]
    error = KeyError("missing")

    assert handler_swallows_code(_nested.__code__, inner, error) is False  # narrow and re-raises
    assert handler_swallows_code(_nested.__code__, outer, error) is True  # broad, returns a default


def _first_match(value: object) -> int:
    try:
        return int(value)  # type: ignore[call-overload]
    except ValueError:
        return -1
    except Exception:
        return 0


def test_first_matching_clause_decides() -> None:
    offset = _handler_offsets(_first_match.__code__)[0]

    assert (
        handler_swallows_code(_first_match.__code__, offset, ValueError("x")) is False
    )  # the narrow clause handles it
    assert handler_swallows_code(_first_match.__code__, offset, TypeError("x")) is True


class _Custom(Exception):
    pass


def _unresolvable() -> int:
    try:
        return 1
    except _Custom:
        return -1
    except Exception:
        return 0


def test_unresolvable_clause_is_never_flagged() -> None:
    offset = _handler_offsets(_unresolvable.__code__)[0]

    # ``_Custom`` is not a builtin: it may match, so no finding (never a false positive)
    assert handler_swallows_code(_unresolvable.__code__, offset, _Custom()) is False


def test_cleanup_offset_is_not_a_handler() -> None:
    cleanup = [i.offset for i in dis.get_instructions(_nested.__code__) if i.opname == "COPY"]

    assert [handler_swallows_code(_nested.__code__, o, KeyError("x")) for o in cleanup] == [False] * len(cleanup)


def test_ast_cache_is_per_code_object(monkeypatch: pytest.MonkeyPatch) -> None:
    swallowed.clear_cache()
    parses: list[str] = []
    real_parse = swallowed.ast.parse
    monkeypatch.setattr(
        swallowed.ast, "parse", lambda source, *a, **k: parses.append("x") or real_parse(source, *a, **k)
    )
    outer = _handler_offsets(_nested.__code__)[1]

    for _ in range(3):
        handler_swallows_code(_nested.__code__, outer, KeyError("x"))

    assert len(parses) == 1
