"""Shared route metadata helpers for REST API rule families."""

from __future__ import annotations

import collections.abc as abc
import re
import types
import typing
from collections.abc import Callable, Iterator, Sequence
from typing import Any, NamedTuple

from sharpit.engine.spi import ApiRouteInfo

FRAMEWORK_MODULES = frozenset({"fastapi", "starlette", "sharpit"})
MUTATING = ("POST", "PUT", "PATCH", "DELETE")
VERBS = frozenset(
    [
        "get",
        "create",
        "update",
        "delete",
        "remove",
        "save",
        "add",
        "fetch",
        "insert",
        "modify",
        "post",
        "put",
        "patch",
        "read",
    ]
)
VERB_STANDALONE = frozenset(["get", "create", "update", "delete", "remove", "save", "add", "fetch", "insert", "modify"])
CREATION_PREFIXES = frozenset(["create", "add", "save", "insert", "register", "new"])
STATE_CHANGING_PREFIXES = frozenset(
    [
        "create",
        "update",
        "delete",
        "remove",
        "save",
        "add",
        "insert",
        "modify",
        "patch",
        "put",
        "post",
        "register",
        "edit",
    ]
)
NON_MUTATING_PREFIXES = ("postprocess", "putaside", "patchversion")
IRREGULAR_PLURALS = frozenset(
    [
        "people",
        "children",
        "men",
        "women",
        "media",
        "data",
        "criteria",
        "indices",
        "vertices",
        "feet",
        "teeth",
        "geese",
        "mice",
        "series",
        "species",
    ]
)
UNCOUNTABLE = frozenset(
    [
        "history",
        "inventory",
        "staff",
        "info",
        "information",
        "search",
        "news",
        "status",
        "metadata",
        "feedback",
        "content",
        "equipment",
        "software",
        "hardware",
        "analytics",
        "reporting",
        "billing",
        "processing",
        "shipping",
        "access",
    ]
)
NON_API_SEGMENTS = frozenset(
    [
        "health",
        "info",
        "ready",
        "readiness",
        "live",
        "liveness",
        "metrics",
        "prometheus",
        "error",
        "login",
        "logout",
        "oauth",
        "oauth2",
        "token",
        "docs",
        "redoc",
        "openapi.json",
        "swagger-ui",
        "swagger",
        "api-docs",
        "favicon.ico",
        "static",
    ]
)
VERSION = re.compile(r"v\d+", re.IGNORECASE)
DOUBLE_SLASH = re.compile(r"//")
CATCH_ALL = re.compile(r"\{[^}]*:path\}")
WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")
PAGING_PARAMS = frozenset({"limit", "offset", "page", "cursor", "size"})
COLLECTIONS: tuple[object, ...] = (
    list,
    tuple,
    set,
    frozenset,
    abc.Sequence,
    abc.MutableSequence,
    abc.Set,
    abc.MutableSet,
    abc.Collection,
    abc.Iterable,
    abc.Iterator,
)
UNTYPED: tuple[object, ...] = (Any, object, dict, abc.Mapping, abc.MutableMapping)
NONE = type(None)
MAX_TYPE_DEPTH = 8


def shared_is_framework(route: ApiRouteInfo) -> bool:
    return route.handler.partition(":")[0].partition(".")[0] in FRAMEWORK_MODULES


def shared_route_target(route: ApiRouteInfo) -> str:
    """``"<METHOD> <path> <module:qualname>"``; several methods are each named, sorted and joined with ``" | "``.

    The handler keeps two handlers on one method and path apart (a fingerprint dismisses one finding)."""
    return " | ".join(f"{method} {route.path}" for method in sorted(route.methods)) + f" {route.handler}"


def shared_describe(route: ApiRouteInfo, suffix: str | None = None) -> str:
    base = f"{route.handler} [{' '.join(route.methods)} {route.path}]"
    return f"{base} — {suffix}" if suffix else base


def shared_function(route: ApiRouteInfo) -> str:
    return route.handler.rpartition(":")[2].rpartition(".")[2]


def shared_words(name: str) -> list[str]:
    return [w.lower() for w in WORDS.findall(name)]


def shared_first_word(name: str) -> str | None:
    words = shared_words(name)
    return words[0] if words else None


def shared_segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def shared_is_variable(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def shared_static(path: str) -> list[str]:
    return [s for s in shared_segments(path) if not shared_is_variable(s)]


def shared_unwrap(tp: object) -> object:
    """``Optional[X]``, ``X | None`` and ``Annotated[X, ...]`` -> ``X``."""
    for _ in range(MAX_TYPE_DEPTH):
        origin = typing.get_origin(tp)
        if origin is typing.Annotated:
            tp = typing.get_args(tp)[0]
        elif origin is typing.Union or origin is types.UnionType:
            args = [a for a in typing.get_args(tp) if a is not NONE]
            if len(args) != 1:
                return tp
            tp = args[0]
        else:
            return tp
    return tp


def shared_origin(tp: object) -> object:
    tp = shared_unwrap(tp)
    return typing.get_origin(tp) or tp


def shared_response_type(route: ApiRouteInfo) -> object | None:
    return route.response_model if route.response_model is not None else route.return_annotation


def shared_is_collection(route: ApiRouteInfo) -> bool:
    tp = shared_response_type(route)
    return tp is not None and any(shared_origin(tp) is c for c in COLLECTIONS)


def shared_all_types(tp: object, depth: int = 0) -> Iterator[object]:
    yield tp
    if depth < MAX_TYPE_DEPTH:
        for arg in typing.get_args(tp):
            yield from shared_all_types(arg, depth + 1)


def shared_persistence_class(route: ApiRouteInfo) -> type | None:
    for root in (route.response_model, route.return_annotation):
        for tp in shared_all_types(root):
            if isinstance(tp, type) and (hasattr(tp, "__table__") or hasattr(tp, "__mapper__")):
                return tp
    return None


def shared_has_body_type(route: ApiRouteInfo) -> bool:
    return route.response_model is not None or route.return_annotation not in (None, NONE)


APPLICATION = "application"


class Violation(NamedTuple):
    """One rule occurrence and its display strings."""

    target: str
    message: str


Check = Callable[[Sequence[ApiRouteInfo], Sequence[str]], list[Violation]]


def each(predicate: Callable[[ApiRouteInfo], str | None]) -> Check:
    def check(routes: Sequence[ApiRouteInfo], _handlers: Sequence[str]) -> list[Violation]:
        out: list[Violation] = []
        for route in routes:
            suffix = predicate(route)
            if suffix is not None:
                out.append(Violation(shared_route_target(route), shared_describe(route, suffix)))
        return out

    return check
