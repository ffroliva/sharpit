"""Declaration-only discovery of FastAPI and Starlette exception handlers."""

from __future__ import annotations

import functools
import inspect
import types
from typing import Any, cast

from starlette.applications import Starlette
from starlette.routing import Host, Mount, Router

from sharpit.engine.spi import ErrorHandlerInfo
from sharpit.fastapi.capture import WrappingHandlers
from sharpit.fastapi.introspection_common import MAX_DEPTH, attrs


def _handler_name(handler: object) -> tuple[str, bool]:
    values = attrs(handler)
    original = values.get("__sharpit_original__")
    if original is not None:
        handler = original
    is_partial = type(handler) is functools.partial
    while type(handler) is functools.partial:
        handler = cast(Any, handler).func
    if type(handler) is types.MethodType:
        handler = cast(Any, handler).__func__
    if type(handler) not in (types.FunctionType, types.BuiltinFunctionType, type):
        handler = type(handler)
    if type(handler) is types.FunctionType:
        function = cast(types.FunctionType, inspect.unwrap(handler))
        return f"{function.__module__}.{function.__qualname__}", is_partial
    handler_type = cast(type[Any], handler)
    module = type.__getattribute__(handler_type, "__module__")
    qualname = type.__getattribute__(handler_type, "__qualname__")
    return f"{module if type(module) is str else '?'}.{qualname if type(qualname) is str else '?'}", is_partial


def _key(key: object) -> tuple[str | None, int | None]:
    if type(key) is int:
        return None, key
    if type(key) is type:
        return (
            f"{type.__getattribute__(key, '__module__')}.{type.__getattribute__(key, '__qualname__')}",
            None,
        )
    return None, None


def _handlers(app: object, scope: str, target: str | None) -> tuple[list[ErrorHandlerInfo], list[str]]:
    values = attrs(app)
    handlers = values.get("exception_handlers")
    try:
        known_capture_wrapper = type(handlers) is WrappingHandlers
        if type(handlers) is not dict and not known_capture_wrapper:
            return [], [f"Exception handlers at {target or '/'} could not be inspected."]
        rows: list[ErrorHandlerInfo] = []
        limitations: list[str] = []
        handler_map = cast(dict[object, object], handlers)
        for key, handler in handler_map.items():
            try:
                key_type, key_status = _key(key)
                row_scope = "SCOPED" if key_status is not None else scope
                row_target = f"status={key_status}" if key_status is not None else target
                name, is_partial = _handler_name(handler)
                rows.append(ErrorHandlerInfo(key_type, key_status, name, row_scope, row_target, is_partial))
            except Exception:  # noqa: BLE001 - one opaque host handler must not hide its siblings
                limitations.append(f"An exception handler at {target or '/'} could not be inspected.")
        return rows, limitations
    except Exception:  # noqa: BLE001 - framework drift must not break the host app
        return [], [f"Exception handlers at {target or '/'} could not be inspected."]


def _mounted_apps(
    app: object, target: str | None, excluded: str, depth: int
) -> tuple[list[tuple[object, str]], list[str]]:
    router = attrs(app).get("router", app)
    routes = attrs(router).get("routes") if router is not None else None
    if type(routes) is not list:
        return [], [f"Mounted routes at {target or '/'} could not be inspected."]
    route_items = cast(list[object], routes)
    if depth >= MAX_DEPTH:
        found = any(issubclass(type(route), Mount) for route in route_items)
        note = [f"Mounted exception handlers beyond depth {MAX_DEPTH} were not inspected."] if found else []
        return [], note
    children: list[tuple[object, str]] = []
    limitations: list[str] = []
    for route in route_items:
        if issubclass(type(route), Host):
            limitations.append(f"Host routes at {target or '/'} were not inspected.")
            continue
        if not issubclass(type(route), Mount):
            continue
        mount = attrs(route)
        path = mount.get("path")
        child = mount.get("_base_app")
        if child is None:
            child = mount.get("app")
        if type(path) is not str or child is None:
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
    is_app = issubclass(type(app), Starlette)
    is_router = issubclass(type(app), Router)
    if not is_app and not is_router:
        return  # an opaque ASGI mount declares no Starlette handlers; the route scan already notes it
    if is_app:
        found, notes = _handlers(app, scope, target)
        rows.extend(found)
        limitations.extend(notes)
    children, notes = _mounted_apps(app, target, excluded, depth)
    limitations.extend(notes)
    for child, path in children:
        _walk(child, "SCOPED", path, depth + 1, excluded, visited | {id(app)}, rows, limitations)


def error_handler_infos(
    app: object, exclude_mount: str | None = None
) -> tuple[tuple[ErrorHandlerInfo, ...], tuple[str, ...]]:
    """Read handler dictionaries and mounted app route tables using instance storage only."""
    rows: list[ErrorHandlerInfo] = []
    limitations: list[str] = []
    _walk(app, "GLOBAL", None, 0, (exclude_mount or "").rstrip("/"), set(), rows, limitations)
    rows.sort(key=lambda row: (row.scope, row.scope_target or "", row.key_type or "", row.key_status or -1))
    return tuple(rows), tuple(dict.fromkeys(limitations))
