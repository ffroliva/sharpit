"""Whether the running code is the current request's own endpoint or dependency (security-sinks plan, D1)."""

from __future__ import annotations

import contextlib
import functools
import sys
import weakref
from collections.abc import Mapping
from types import CodeType, FrameType
from typing import Any, cast

from starlette.endpoints import HTTPEndpoint

from sharpit.engine.capture.frames import call_site_label, is_application_frame

_CACHE_LIMIT = 1024
type _CacheValue = frozenset[CodeType] | dict[str, frozenset[CodeType]]
_CACHE: dict[int, tuple[weakref.ReferenceType[Any], tuple[int, ...], _CacheValue]] = {}


def _overrides_snapshot(scope: Mapping[str, Any]) -> tuple[int, ...]:
    """The identities of the app's dependency overrides: a cached code set is valid only for the set that built it."""
    try:
        overrides = getattr(scope.get("app"), "dependency_overrides", None)
        if not isinstance(overrides, Mapping) or not overrides:
            return ()
        return tuple(id(part) for pair in tuple(cast("Mapping[Any, Any]", overrides).items()) for part in pair)
    except Exception:  # noqa: BLE001 - this module never raises; an odd app gives the uncached-overrides answer
        return ()


def _method_name(scope: Mapping[str, Any]) -> str:
    raw = scope.get("method")
    return raw.lower() if isinstance(raw, str) else ""


def _unwrap_class(target: type[Any], *, is_dependency: bool, method: str) -> tuple[Any, bool]:
    if not is_dependency and issubclass(target, HTTPEndpoint):
        name = "get" if method == "head" and not hasattr(target, "head") else method
        return (getattr(target, name, None) if name else None), True
    if is_dependency:
        return getattr(target, "__init__", None), False
    return None, False


def _next_target(target: Any, *, is_dependency: bool, method: str, out: set[CodeType]) -> tuple[Any, bool]:
    if isinstance(target, functools.partial):
        return target.func, False
    if (func := getattr(target, "__func__", None)) is not None and func is not target:
        return func, False
    if isinstance(target, type):
        return _unwrap_class(target, is_dependency=is_dependency, method=method)
    code = getattr(target, "__code__", None)
    if isinstance(code, CodeType):
        out.add(code)
    if (wrapped := getattr(target, "__wrapped__", None)) is not None and wrapped is not target:
        return wrapped, False
    if isinstance(code, CodeType):
        return None, False
    if is_dependency and callable(target):
        call_attr = type(target).__call__
        if call_attr is not target:
            return call_attr, False
    return None, False


def _unwrap_into(target: Any, *, is_dependency: bool, method: str, out: set[CodeType]) -> bool:
    used_method = False
    current: Any = target
    for _ in range(16):
        if current is None:
            break
        current, class_used_method = _next_target(current, is_dependency=is_dependency, method=method, out=out)
        used_method = used_method or class_used_method
    return used_method


def _resolve_call(call: Any, overrides: Mapping[Any, Any] | None) -> Any:
    if call is None or overrides is None:
        return call
    with contextlib.suppress(TypeError):
        return overrides.get(call, call)
    return call


def _walk_dependencies(
    root: Any,
    overrides: Mapping[Any, Any] | None,
    method: str,
    out: set[CodeType],
    seen: set[int],
) -> None:
    stack = list(getattr(root, "dependencies", ()) or ())
    seen_deps: set[int] = set()
    while stack:
        dep = stack.pop()
        if id(dep) in seen_deps:
            continue
        seen_deps.add(id(dep))
        call = _resolve_call(getattr(dep, "call", None), overrides)
        if call is not None and id(call) not in seen:
            seen.add(id(call))
            _unwrap_into(call, is_dependency=True, method=method, out=out)
        children = getattr(dep, "dependencies", None)
        if children:
            stack.extend(children)


def _build_codes(scope: Mapping[str, Any], route: Any, endpoint: Any) -> tuple[frozenset[CodeType], bool]:
    dependant = getattr(route, "dependant", None) if route is not None else None
    app = scope.get("app")
    raw_overrides = getattr(app, "dependency_overrides", None) if app is not None else None
    overrides = cast("Mapping[Any, Any]", raw_overrides) if isinstance(raw_overrides, Mapping) else None
    method = _method_name(scope)
    codes: set[CodeType] = set()
    seen: set[int] = set()
    used_method = False
    candidates = (
        endpoint,
        getattr(route, "endpoint", None) if route is not None else None,
        getattr(dependant, "call", None) if dependant is not None else None,
    )
    for target in candidates:
        if target is not None and id(target) not in seen:
            seen.add(id(target))
            used_method = _unwrap_into(target, is_dependency=False, method=method, out=codes) or used_method
    if dependant is not None:
        _walk_dependencies(dependant, overrides, method, codes, seen)
    return frozenset(codes), used_method


def _store_cached(
    key: Any, method: str, codes: frozenset[CodeType], snapshot: tuple[int, ...], *, used_method: bool
) -> None:
    try:
        ref = weakref.ref(key)
    except TypeError:
        return
    key_id = id(key)
    if used_method:
        existing = _CACHE.get(key_id)
        if existing is not None and existing[0]() is key and existing[1] == snapshot and isinstance(existing[2], dict):
            existing[2][method] = codes
            return
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[key_id] = (ref, snapshot, {method: codes})
        return
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key_id] = (ref, snapshot, codes)


def _codes_for(scope: Mapping[str, Any]) -> frozenset[CodeType]:
    route = scope.get("route")
    endpoint = scope.get("endpoint")
    key = route if route is not None else endpoint
    if key is None:
        return frozenset()
    method = _method_name(scope)
    snapshot = _overrides_snapshot(scope)
    cached = _CACHE.get(id(key))
    if cached is not None and cached[0]() is key and cached[1] == snapshot:
        value = cached[2]
        if isinstance(value, frozenset):
            return value
        if method in value:
            return value[method]
    codes, used_method = _build_codes(scope, route, endpoint)
    _store_cached(key, method, codes, snapshot, used_method=used_method)
    return codes


def _frame_owner(
    frame: FrameType | None, codes: frozenset[CodeType], first_app: str | None = None
) -> tuple[str | None, str | None]:
    try:
        while frame is not None:
            code = frame.f_code
            if first_app is None and is_application_frame(code.co_filename):
                first_app = call_site_label(frame)
            if code in codes:
                return (first_app if first_app is not None else call_site_label(frame)), first_app
            frame = frame.f_back
        return None, first_app
    finally:
        frame = None


def _greenlet_owner(codes: frozenset[CodeType], first_app: str | None) -> str | None:
    greenlet = sys.modules.get("greenlet")
    getcurrent = getattr(greenlet, "getcurrent", None) if greenlet is not None else None
    if not callable(getcurrent):
        return None
    current: Any = getcurrent()
    try:
        for _ in range(8):
            current = getattr(current, "parent", None)
            if current is None:
                return None
            found, first_app = _frame_owner(getattr(current, "gr_frame", None), codes, first_app)
            if found is not None:
                return found
        return None
    finally:
        current = None


def owner(scope: Mapping[str, Any]) -> str | None:
    """The call site (``module:qualname``) when the current stack or a parent greenlet's stack runs the request's own
    endpoint or dependency, else None."""
    try:
        codes = _codes_for(scope)
        if not codes:
            return None
        found, first_app = _frame_owner(sys._getframe(1), codes)  # pyright: ignore[reportPrivateUsage]
        return found if found is not None else _greenlet_owner(codes, first_app)
    except Exception:
        return None


def owned(scope: Mapping[str, Any]) -> bool:
    """Whether the current stack, or a parent greenlet's stack, runs the request's own endpoint or dependency."""
    return owner(scope) is not None
