"""The static route handler index (spec §5.6): which route endpoints are plain functions defined in the app package.

Nothing here calls user code or runs a descriptor: a route's attributes are read with ``inspect.getattr_static``, a
decorator chain is followed through ``vars(fn)["__wrapped__"]`` (depth 8) and only ``type(fn) is FunctionType`` is
analysed. Callable instances, ``functools.partial`` objects, builtins, methods and functions defined outside the app
package are skipped with a limitation naming the route.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Sequence
from dataclasses import dataclass
from types import FunctionType

from sharpit.engine.appsource import ModuleInfo, SourceIndex


@dataclass(frozen=True)
class Endpoint:
    """One route as the adapter hands it over (read with ``getattr_static``, never called)."""

    label: str  # "GET /items"
    endpoint: object
    response_model: object = None


@dataclass(frozen=True)
class Handler:
    """A route handler the rules analyse: its function's AST in the app's source index."""

    label: str
    qualname: str  # module:qualname of the analysed (unwrapped) function
    is_async: bool
    module: ModuleInfo
    node: ast.FunctionDef | ast.AsyncFunctionDef
    response_model: object = None

    @property
    def where(self) -> str:
        return f"{self.label} ({self.qualname})"


MAX_UNWRAP = 8


def resolve_handler(endpoint: object) -> FunctionType | None:
    """The plain function behind ``endpoint`` after unwrapping ``functools.wraps`` decorators, else None."""
    if type(endpoint) is not FunctionType:  # type(), never isinstance: a __class__ property is user code
        return None
    fn = endpoint
    for _ in range(MAX_UNWRAP):
        inner = vars(fn).get("__wrapped__")
        if type(inner) is not FunctionType:
            break
        fn = inner
    return fn


def _function_node(module: ModuleInfo, fn: FunctionType) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    code = fn.__code__
    for node in ast.walk(module.tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == code.co_name:
            first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            if code.co_firstlineno in (first, node.lineno):
                return node
    return None


def index_handlers(endpoints: Sequence[Endpoint], index: SourceIndex) -> tuple[list[Handler], list[str]]:
    """The analysable handlers among ``endpoints`` and one limitation per skipped route."""
    by_file = {os.path.realpath(m.path): m for m in index.modules.values()}
    handlers: list[Handler] = []
    limitations: list[str] = []
    for route in endpoints:
        fn = resolve_handler(route.endpoint)
        if fn is None:
            limitations.append(f"{route.label}: the endpoint is not a plain function (not analysed).")
            continue
        code = fn.__code__
        module = by_file.get(os.path.realpath(code.co_filename))
        node = _function_node(module, fn) if module is not None else None
        if module is None or node is None:
            limitations.append(f"{route.label}: the handler is defined outside the application package (not analysed).")
            continue
        is_async = isinstance(node, ast.AsyncFunctionDef)
        handlers.append(
            Handler(route.label, f"{module.name}:{code.co_qualname}", is_async, module, node, route.response_model)
        )
    return handlers, limitations
