"""The static route handler index (spec §5.6): decorators unwrapped, user objects never asked for attributes."""

from __future__ import annotations

import functools
import os
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sharpit.engine.collectors.fastapi_advisor.handlers import Endpoint, index_handlers

from .support import load_app


def traced(fn: Callable[..., Any]) -> Callable[..., Any]:
    """A decorator defined in this file: an unresolved wrapper would point here, not at the app."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return wrapper


def test_decorated_handler_resolved_to_inner_function(tmp_path: Path) -> None:
    namespace, root, index = load_app(
        tmp_path,
        """
        def read_items():
            return []
        """,
    )
    handler = traced(namespace["read_items"])
    assert handler.__code__.co_filename == os.path.realpath(__file__)  # the endpoint FastAPI holds is the wrapper
    handlers, limitations = index_handlers([Endpoint("GET /items", handler)], index)
    assert limitations == []
    assert [h.qualname for h in handlers] == ["app_pkg.main:read_items"]
    assert os.path.realpath(handlers[0].module.path) == os.path.realpath(root / "main.py")


class _Counting:
    """A callable instance whose ``__getattr__`` counts every attribute it is asked for."""

    def __init__(self) -> None:
        object.__setattr__(self, "asked", [])

    def __call__(self) -> str:
        raise AssertionError("an endpoint was called")

    def __getattr__(self, name: str) -> Any:
        object.__getattribute__(self, "asked").append(name)
        raise AttributeError(name)


def test_callable_instance_endpoint_skipped_without_getattr(tmp_path: Path) -> None:
    _, _, index = load_app(tmp_path, "X = 1\n")
    endpoint = _Counting()
    handlers, limitations = index_handlers([Endpoint("GET /c", endpoint)], index)
    assert object.__getattribute__(endpoint, "asked") == []
    assert handlers == []
    assert [line for line in limitations if "GET /c" in line] != []


def test_partial_and_library_handlers_skipped_with_limitation(tmp_path: Path) -> None:
    namespace, _, index = load_app(
        tmp_path,
        """
        def greet(name):
            return name
        """,
    )
    endpoints = [
        Endpoint("GET /partial", functools.partial(namespace["greet"], "x")),
        Endpoint("GET /library", textwrap.dedent),
    ]
    handlers, limitations = index_handlers(endpoints, index)
    assert handlers == []
    assert len([line for line in limitations if "GET /partial" in line]) == 1
    assert len([line for line in limitations if "GET /library" in line]) == 1
