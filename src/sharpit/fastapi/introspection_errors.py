"""Declaration-only discovery of FastAPI and Starlette exception handlers."""

from __future__ import annotations

import functools
import inspect
import types
from collections.abc import Mapping
from typing import Any, cast

from starlette.applications import Starlette
from starlette.routing import Mount

from sharpit.engine.spi import ErrorHandlerInfo
from sharpit.fastapi.introspection_common import MAX_DEPTH, attrs


def _handler_name(handler: object) -> str:
    while isinstance(handler, functools.partial):
        handler = handler.func
    if type(handler) is types.MethodType:
        handler = cast(Any, handler).__func__
    if type(handler) not in (types.FunctionType, types.BuiltinFunctionType) and not isinstance(handler, type):
        handler = type(handler)
    values = attrs(handler)
    original = values.get("__sharpit_original__")
    if original is not None:
        handler = original
        values = attrs(handler)
    if type(handler) is types.FunctionType:
        function = cast(types.FunctionType, inspect.unwrap(handler))
        return f"{function.__module__}:{function.__qualname__}"
    handler_type = cast(type[Any], handler)
    module = type.__getattribute__(handler_type, "__module__")
    qualname = type.__getattribute__(handler_type, "__qualname__")
    return f"{module if isinstance(module, str) else '?'}:{qualname if isinstance(qualname, str) else '?'}"


def _key(key: object) -> tuple[str | None, int | None]:
    if type(key) is int:
        return None, key
    if isinstance(key, type):
        return (
            f"{type.__getattribute__(key, '__module__')}:{type.__getattribute__(key, '__qualname__')}",
            None,
        )
    return None, None


def _handlers(app: object, scope: str, target: str | None) -> tuple[list[ErrorHandlerInfo], list[str]]:
    values = attrs(app)
    handlers = values.get("exception_handlers")
    try:
        if not isinstance(handlers, Mapping):
            return [], [f"Exception handlers at {target or '/'} could not be inspected."]
        handler_map = cast(Mapping[object, object], handlers)
        rows = [
            ErrorHandlerInfo(*_key(key), _handler_name(handler), scope, target)
            for key, handler in tuple(handler_map.items())
        ]
        return rows, []
    except Exception:  # noqa: BLE001 - a custom handler mapping may not be safely readable
        return [], [f"Exception handlers at {target or '/'} could not be inspected."]


def _mounted_apps(
    app: object, target: str | None, excluded: str, depth: int
) -> tuple[list[tuple[object, str]], list[str]]:
    router = attrs(app).get("router")
    routes = attrs(router).get("routes") if router is not None else None
    if not isinstance(routes, list):
        return [], [f"Mounted routes at {target or '/'} could not be inspected."]
    route_items = cast(list[object], routes)
    if depth >= MAX_DEPTH:
        found = any(issubclass(type(route), Mount) for route in route_items)
        note = [f"Mounted exception handlers beyond depth {MAX_DEPTH} were not inspected."] if found else []
        return [], note
    children: list[tuple[object, str]] = []
    limitations: list[str] = []
    for route in route_items:
        if not issubclass(type(route), Mount):
            continue
        mount = attrs(route)
        path = mount.get("path")
        child = mount.get("_base_app")
        if child is None:
            child = mount.get("app")
        if not isinstance(path, str) or child is None:
            limitations.append("A mounted application's exception handlers could not be inspected.")
            continue
        full_path = f"{target or ''}{path}"
        if not excluded or full_path.rstrip("/") != excluded:
            children.append((child, full_path or "/"))
    return children, limitations


def _walk(
    app: object,
    scope: str,
    target: str | None,
    depth: int,
    excluded: str,
    visited: set[int],
    rows: list[ErrorHandlerInfo],
    limitations: list[str],
) -> None:
    if id(app) in visited:
        return
    visited.add(id(app))
    if not issubclass(type(app), Starlette):
        return  # an opaque ASGI mount declares no Starlette handlers; the route scan already notes it
    found, notes = _handlers(app, scope, target)
    rows.extend(found)
    limitations.extend(notes)
    children, notes = _mounted_apps(app, target, excluded, depth)
    limitations.extend(notes)
    for child, path in children:
        _walk(child, "SCOPED", path, depth + 1, excluded, visited, rows, limitations)


def error_handler_infos(
    app: object, exclude_mount: str | None = None
) -> tuple[tuple[ErrorHandlerInfo, ...], tuple[str, ...]]:
    """Read handler dictionaries and mounted app route tables using instance storage only."""
    rows: list[ErrorHandlerInfo] = []
    limitations: list[str] = []
    _walk(app, "GLOBAL", None, 0, (exclude_mount or "").rstrip("/"), set(), rows, limitations)
    rows.sort(key=lambda row: (row.scope, row.scope_target or "", row.key_type or "", row.key_status or -1))
    return tuple(rows), tuple(dict.fromkeys(limitations))
