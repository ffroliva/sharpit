"""Request correlation (spec §9): the current request, as the capture middleware set it, and sharpit's own marker."""

from __future__ import annotations

import secrets
from collections.abc import Generator, Mapping, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs


@dataclass(frozen=True)
class PagingContext:
    route: str
    parameter_names: frozenset[str]
    page_size: int | None


def paging_of(scope: Mapping[str, Any]) -> PagingContext | None:
    route = scope.get("route")
    path = getattr(route, "path", None)
    dependant = getattr(route, "dependant", None)
    query_params = getattr(dependant, "query_params", ())
    names = frozenset(
        name for param in query_params if isinstance((name := getattr(param, "alias", None)), str)
    )
    if not isinstance(path, str) or not names.intersection({"skip", "limit", "offset", "page", "page_size"}):
        return None
    raw_query = scope.get("query_string", b"")
    query = raw_query.decode("latin-1") if isinstance(raw_query, bytes) else str(raw_query)
    values = parse_qs(query, keep_blank_values=True)
    size: int | None = None
    for name in ("limit", "page_size"):
        if name not in names or name not in values or len(values[name]) != 1:
            continue
        try:
            candidate = int(values[name][0])
        except (TypeError, ValueError):
            continue
        if candidate > 0:
            size = candidate
            break
    return PagingContext(path, names, size)


@dataclass
class RequestInfo:
    id: str
    context_id: str  # the installed sharpit context whose middleware created it (spec §6.2)
    method: str
    path: str  # masked
    endpoint: str | None
    started_ns: int
    finished_ns: int | None
    scope: MutableMapping[str, Any] | None = None
    paging: PagingContext | None = None
    loads: dict[int, Any] = field(default_factory=dict)


REQUEST: ContextVar[RequestInfo | None] = ContextVar("sharpit_request", default=None)
# the running test as the pytest plugin tags it: (nodeid, attempt, phase); None outside a test (spec 0.3.0 §6.4)
TEST: ContextVar[tuple[str, int, str] | None] = ContextVar("sharpit_test", default=None)
INTERNAL: ContextVar[bool] = ContextVar("sharpit_internal", default=False)


def new_request_id() -> str:
    return secrets.token_hex(8)


@contextmanager
def internal() -> Generator[None]:
    """Mark sharpit's own work (health checks, migration reads) so the SQL listener skips it."""
    token = INTERNAL.set(True)
    try:
        yield
    finally:
        INTERNAL.reset(token)
