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


def _safe_unwrap(handler: object) -> tuple[object, bool]:
    orig = inspect.getattr_static(handler, "__sharpit_original__", None)
    if orig is not None:
        handler = orig
    is_partial = False
    seen: set[int] = {id(handler)}
    for _ in range(MAX_DEPTH):
        if type(handler) is functools.partial:
            is_partial = True
            handler = cast(Any, handler).func
            if id(handler) in seen:
                raise ValueError("wrapper loop")
            seen.add(id(handler))
            continue
        if type(handler) is types.MethodType:
            handler = cast(Any, handler).__func__
            if id(handler) in seen:
                raise ValueError("wrapper loop")
            seen.add(id(handler))
            continue
        wrapped = inspect.getattr_static(handler, "__wrapped__", None)
        if wrapped is not None:
            if id(wrapped) in seen:
                raise ValueError("wrapper loop")
            if type(wrapped) in (types.FunctionType, types.MethodType, functools.partial):
                seen.add(id(wrapped))
                handler = wrapped
                continue
        break
    return handler, is_partial


def _handler_name(handler: object) -> tuple[str, bool]:
    handler, is_partial = _safe_unwrap(handler)
    if type(handler) in (types.FunctionType, types.BuiltinFunctionType):
        func = cast(Any, handler)
        module = getattr(func, "__module__", None)
        qualname = getattr(func, "__qualname__", None)
        mod_str = module if type(module) is str else "?"
        qual_str = qualname if type(qualname) is str else "?"
        return f"{mod_str}.{qual_str}", is_partial
    if type(handler) not in (types.FunctionType, types.BuiltinFunctionType, type):
        handler = type(handler)
    if isinstance(handler, type):
        try:
            module = type.__getattribute__(handler, "__module__")
            qualname = type.__getattribute__(handler, "__qualname__")
            mod_str = module if type(module) is str else "?"
            qual_str = qualname if type(qualname) is str else "?"
            return f"{mod_str}.{qual_str}", is_partial
        except Exception:
            return "UNRESOLVED", is_partial
    return "UNRESOLVED", is_partial


def _key(key: object) -> tuple[str | None, int | None]:
    if type(key) is int:
        return None, key
    if type(key) is type:
        try:
            module = type.__getattribute__(key, "__module__")
            qualname = type.__getattribute__(key, "__qualname__")
            if type(module) is str and type(qualname) is str:
                name = qualname if module == "builtins" else f"{module}.{qualname}"
                return name, None
        except Exception:
            return None, None
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
                if key_type is None and key_status is None:
                    limitations.append(f"An exception handler at {target or '/'} could not be inspected.")
                row_scope = "SCOPED" if key_status is not None else scope
                row_target = (
                    target if target is not None else (f"status={key_status}" if key_status is not None else None)
                )
                name, is_partial = _handler_name(handler)
                rows.append(ErrorHandlerInfo(key_type, key_status, name, row_scope, row_target, is_partial))
            except Exception:  # noqa: BLE001 - one opaque host handler must not hide its siblings
                limitations.append(f"An exception handler at {target or '/'} could not be inspected.")
        return rows, limitations
    except Exception:  # noqa: BLE001 - framework drift must not break the host app
        return [], [f"Exception handlers at {target or '/'} could not be inspected."]


def _mount_entry(route: object, target: str | None, excluded: str) -> tuple[tuple[object, str] | None, str | None]:
    if issubclass(type(route), Host):
        return None, f"Host routes at {target or '/'} were not inspected."
    if not issubclass(type(route), Mount):
        return None, None
    mount = attrs(route)
    path = mount.get("path")
    child = mount.get("_base_app") or mount.get("app")
    if type(path) is not str or child is None:
        return None, "A mounted application's exception handlers could not be inspected."
    full_path = f"{target or ''}{path}"
    if not excluded or full_path.rstrip("/") != excluded:
        return (child, full_path or "/"), None
    return None, None


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
        entry, note = _mount_entry(route, target, excluded)
        if note is not None:
            limitations.append(note)
        if entry is not None:
            children.append(entry)
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
