"""The swallowed-handler predicate (spec 0.4.0 §5.5 F1): broad catch, no re-raise, no logger/warnings call."""

from __future__ import annotations

import dis
import re
import textwrap
from pathlib import Path
from types import CodeType, FunctionType

import pytest

from sharpit.engine.testsession import swallowed
from sharpit.engine.testsession.swallowed import (
    handler_swallows,
    handler_swallows_code,
    is_programming_error,
    site_identity,
    swallowing_lines,
    swallowing_site,
    swallowing_sites,
)


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
    expected = (AttributeError, TypeError, NameError, ImportError, UnboundLocalError)
    actual = swallowed.PROGRAMMING_ERRORS
    assert actual == expected


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


# --- 0.5.0 T-swallowed-2: the two suspected AST edges ----------------------------------------------------------------


def test_helper_that_logs_is_not_a_swallow() -> None:
    source = _src(
        """
        class Service:
            def run(self):
                try:
                    pass
                except Exception as e:
                    self._report(e)
                    return 0
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception as e:")) is False


def test_non_logger_error_call_is_not_logging() -> None:
    source = _src(
        """
        def a(response):
            try:
                pass
            except Exception:
                response.error("x")
                return 0
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception:")) is True


def test_logger_receivers_still_count_as_logging() -> None:
    source = _src(
        """
        import logging
        import structlog
        _audit = logging.getLogger("audit")
        events: structlog.BoundLogger = structlog.get_logger()

        class Service:
            def a(self):
                try:
                    pass
                except Exception:
                    self.logger.error("failed")
            def b(self):
                try:
                    pass
                except BaseException:
                    _audit.error("failed")
            def c(self):
                try:
                    pass
                except:
                    logging.getLogger(__name__).exception("failed")
            def d(self):
                try:
                    pass
                except (Exception, KeyError):
                    events.warning("failed")
            def e(self):
                try:
                    pass
                except (KeyError, Exception):
                    log.bind(order=1).warning("failed")
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception:")) is False, "self.logger"
    assert handler_swallows(source, _line_of(source, "except BaseException:")) is False, "module logger"
    assert handler_swallows(source, _line_of(source, "except:")) is False, "getLogger(...) receiver"
    assert handler_swallows(source, _line_of(source, "except (Exception, KeyError):")) is False, "annotated logger"
    assert handler_swallows(source, _line_of(source, "except (KeyError, Exception):")) is False, "bound logger"


# --- 0.5.0 T-swallowed-2 fix 1: a call handles the exception only when its target is a recognised sink --------------


def _handler(body: str, prelude: str = "") -> tuple[str, int]:
    source = _src(prelude) + _src(
        f"""
        class Service:
            def run(self, errors, obj, name):
                try:
                    pass
                except Exception as e:
                    {body}
                    return 200
        """
    )
    return source, _line_of(source, "except Exception as e:")


def test_appending_the_error_is_a_swallow() -> None:
    assert handler_swallows(*_handler("errors.append(e)")) is True


@pytest.mark.parametrize(
    "body",
    [
        "str(e)",
        "repr(e)",
        "print(e)",
        "isinstance(e, ValueError)",
        'json.dumps({"err": str(e)})',
        'setattr(obj, "err", e)',
    ],
)
def test_builtin_use_of_the_error_is_a_swallow(body: str) -> None:
    assert handler_swallows(*_handler(body, "import json\n")) is True


def test_helper_that_logs_in_this_module_is_not_a_swallow() -> None:
    prelude = """
        import logging
        log = logging.getLogger(__name__)

        def _report(error):
            log.warning("failed: %s", error)

        """
    assert handler_swallows(*_handler("_report(e)", prelude)) is False


def test_method_that_logs_in_this_module_is_not_a_swallow() -> None:
    source = _src(
        """
        class Service:
            def run(self):
                try:
                    pass
                except Exception as e:
                    self._report(e)
                    return 0

            def _report(self, error):
                self.logger.exception("failed")
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception as e:")) is False


def test_method_that_only_stores_is_a_swallow() -> None:
    source = _src(
        """
        class Service:
            def run(self):
                try:
                    pass
                except Exception as e:
                    self._report(e)
                    return 0

            def _report(self, error):
                self.errors.append(error)
        """
    )
    assert handler_swallows(source, _line_of(source, "except Exception as e:")) is True


@pytest.mark.parametrize("body", ["sentry_sdk.capture_exception()", "rollbar.report_exc_info()", "capture_exception()"])
def test_error_tracker_capture_is_not_a_swallow(body: str) -> None:
    assert handler_swallows(*_handler(body)) is False


def test_error_tracker_capture_of_the_error_is_not_a_swallow() -> None:
    assert handler_swallows(*_handler("bugsnag.notify(e)")) is False


@pytest.mark.parametrize(
    "body",
    [
        'return JSONResponse({"detail": "failed"}, status_code=500)',
        "return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)",
    ],
)
def test_returning_an_http_error_response_is_not_a_swallow(body: str) -> None:
    assert handler_swallows(*_handler(body)) is False


def test_returning_a_success_response_is_a_swallow() -> None:
    assert handler_swallows(*_handler('return JSONResponse({"ok": True}, status_code=200)')) is True


def test_dynamic_target_is_not_reported() -> None:
    assert handler_swallows(*_handler("getattr(self, name)(e)")) is False


def test_imported_function_is_not_reported() -> None:
    assert handler_swallows(*_handler("report(e)", "from app.errors import report\n")) is False


# --- #66: a swallowing clause is identified by its scope and its content, never by its line or its place -----------

TWO_FUNCTIONS = _src(
    """
    def first():
        try:
            pass
        except Exception:
            return 0

    def second():
        try:
            pass
        except Exception:
            return 1
    """
)


def _replaced(source: str, old: str, new: str) -> str:
    changed = source.replace(old, new, 1)
    assert changed != source, f"{old!r} is not in the source"
    return changed


def _keys(source: str, type_name: str = "KeyError") -> list[str]:
    return [site_identity("app.py", site, type_name) for site in swallowing_sites(source)]


def _scopes(source: str) -> list[str]:
    return [site.scope for site in swallowing_sites(source)]


def _clause(call: str, result: int, *, log: bool = False) -> str:
    logging = f"        logger.error('{call}')\n" if log else ""
    return f"    try:\n        {call}()\n    except Exception:\n{logging}        return {result}\n"


def _scope(*clauses: str) -> str:
    return "def f():\n" + "".join(clauses)


def test_identity_survives_a_line_added_above_the_function_and_above_the_handler() -> None:
    above = "import os\n\n" + TWO_FUNCTIONS
    first = "    try:\n        pass\n    except Exception:\n        return 0"
    inside = _replaced(TWO_FUNCTIONS, first, "    x = 1\n    y = 2\n" + first)

    assert [s.line for s in swallowing_sites(above)] != [s.line for s in swallowing_sites(TWO_FUNCTIONS)]
    assert _keys(above) == _keys(TWO_FUNCTIONS)
    assert _keys(inside) == _keys(TWO_FUNCTIONS)


def test_the_same_type_in_another_function_has_another_identity() -> None:
    keys = _keys(TWO_FUNCTIONS)

    assert keys[0] != keys[1]
    assert _scopes(TWO_FUNCTIONS) == ["first", "second"]


def test_swapping_two_try_blocks_keeps_each_identity_with_its_own_clause() -> None:
    a, b = _clause("a", 0), _clause("b", 1)

    before = _keys(_scope(a, b))
    after = _keys(_scope(b, a))

    assert after == [before[1], before[0]]


def test_a_log_added_to_one_clause_and_removed_from_another_moves_no_dismissal() -> None:
    a, b, c = _clause("a", 0), _clause("b", 1), _clause("c", 2, log=True)

    before = _keys(_scope(a, b, c))  # a and b swallow; c logs
    after = _keys(_scope(_clause("a", 0, log=True), b, _clause("c", 2)))  # now b and c swallow

    assert len(before) == len(after) == 2
    assert before[0] not in after  # the dismissed clause a no longer swallows: its key matches nothing
    assert before[1] in after  # clause b keeps its own key


@pytest.mark.parametrize(
    ("old", "new"),
    [pytest.param("a()", "a(1)", id="try-body"), pytest.param("return 0", "return 5", id="handler")],
)
def test_editing_the_try_body_or_the_handler_changes_the_identity(old: str, new: str) -> None:
    base = _scope(_clause("a", 0))

    assert _keys(_replaced(base, old, new)) != _keys(base)


def test_byte_identical_clauses_of_one_scope_get_an_occurrence_suffix() -> None:
    same = _clause("a", 0)
    [single] = _keys(_scope(same))

    first, second = _keys(_scope(same, same))

    digest = single.rpartition("#")[2]
    assert re.fullmatch(r"[0-9a-f]{8}", digest)
    assert (first.rpartition("#")[2], second.rpartition("#")[2]) == (f"{digest}.1", f"{digest}.2")


_PROPERTY = _src(
    """
    class Box:
        @property
        def value(self):
            try:
                pass
            except Exception:
                return 0

        @value.setter
        def value(self, item):
            try:
                pass
            except Exception:
                return
    """
)
_REDEFINED = _src(
    """
    if FLAG:
        def f():
            try:
                pass
            except Exception:
                return 1
    else:
        def f():
            try:
                pass
            except Exception:
                return 2
    """
)
_NESTED = _src(
    """
    def outer():
        def inner():
            try:
                pass
            except Exception:
                return 1
        try:
            pass
        except Exception:
            return 2
    """
)
_GLOBAL = _src(
    """
    def outer():
        global inner
        def inner():
            try:
                pass
            except Exception:
                return 1
    """
)
_MODULE = _src(
    """
    try:
        pass
    except Exception:
        pass
    """
)
_CLASS_BODY = _src(
    """
    class C:
        try:
            pass
        except Exception:
            pass
    """
)
_ASYNC = _src(
    """
    class Client:
        async def fetch(self):
            try:
                pass
            except Exception:
                return None
    """
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(_PROPERTY, ["Box.value", "Box.value"], id="property-getter-and-setter"),
        pytest.param(_REDEFINED, ["f", "f"], id="if-else-redefinition"),
        pytest.param(_NESTED, ["outer.<locals>.inner", "outer"], id="nested-function"),
        pytest.param(_GLOBAL, ["inner"], id="nested-function-declared-global"),
        pytest.param(_MODULE, ["<module>"], id="module-level"),
        pytest.param(_CLASS_BODY, ["C"], id="class-body"),
        pytest.param(_ASYNC, ["Client.fetch"], id="async-method"),
    ],
)
def test_a_scope_is_the_qualified_name_of_the_code_that_holds_the_clause(source: str, expected: list[str]) -> None:
    assert _scopes(source) == expected


def test_the_two_clauses_of_a_property_have_two_identities() -> None:
    getter, setter = _keys(_PROPERTY)

    assert getter != setter


def test_except_star_is_not_a_swallowing_clause() -> None:
    source = _src(
        """
        def f():
            try:
                pass
            except* Exception:
                pass
        """
    )

    assert swallowing_lines(source) == []


def _corpus_inner() -> int:
    def inner() -> int:
        try:
            return {}["missing"]
        except Exception:
            return 1

    return inner()


def _corpus_global() -> int:
    global _corpus_declared

    def _corpus_declared() -> int:
        try:
            return {}["missing"]
        except Exception:
            return 2

    return _corpus_declared()


class _Holder:
    def get(self) -> int:
        try:
            return {}["missing"]
        except Exception:
            return 0


def _nested_code(function: FunctionType) -> CodeType:
    return next(c for c in function.__code__.co_consts if isinstance(c, CodeType))


def test_a_handler_seen_at_runtime_is_in_the_static_set_of_its_file() -> None:
    corpus = [
        (_nested.__code__, KeyError),
        (_first_match.__code__, TypeError),
        (_Holder.get.__code__, KeyError),
        (_nested_code(_corpus_inner), KeyError),
        (_nested_code(_corpus_global), KeyError),
    ]
    static = set(swallowing_sites(Path(__file__).read_text("utf-8")))

    for code, exc_type in corpus:
        seen = [site for offset in _handler_offsets(code) if (site := swallowing_site(code, offset, exc_type))]

        assert len(seen) == 1, code.co_qualname
        assert seen[0] in static, code.co_qualname
        assert seen[0].scope == code.co_qualname


def test_the_identity_names_the_path_the_scope_the_type_and_a_content_hash() -> None:
    source = _src(
        """
        class Week:
            def count(self):
                try:
                    return self.week_id
                except Exception:
                    return 0
        """
    )
    [site] = swallowing_sites(source)

    identity = site_identity("src/app/weeks.py", site, "AttributeError")

    assert re.fullmatch(r"src/app/weeks\.py:Week\.count:AttributeError#[0-9a-f]{8}", identity)


def test_a_new_identity_is_never_a_legacy_line_key() -> None:
    [identity] = _keys(_scope(_clause("a", 0)))

    assert re.fullmatch(r".+:\d+:\w+", identity) is None
