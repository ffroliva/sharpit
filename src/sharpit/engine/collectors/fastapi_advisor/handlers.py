"""The static route handler index (spec §5.6): which route endpoints are plain functions defined in the app package.

Nothing here calls user code or runs a descriptor: a route's attributes are read with ``inspect.getattr_static``, a
decorator chain is followed through ``vars(fn)["__wrapped__"]`` (depth 8) and only ``type(fn) is FunctionType`` is
analysed. Callable instances, ``functools.partial`` objects, builtins, methods and functions defined outside the app
package are skipped with a limitation naming the route.
"""

from __future__ import annotations

import ast
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


def resolve_handler(endpoint: object) -> FunctionType | None:
    """The plain function behind ``endpoint`` after unwrapping ``functools.wraps`` decorators, else None."""
    return None


def index_handlers(endpoints: Sequence[Endpoint], index: SourceIndex) -> tuple[list[Handler], list[str]]:
    """The analysable handlers among ``endpoints`` and one limitation per skipped route."""
    return [], []
