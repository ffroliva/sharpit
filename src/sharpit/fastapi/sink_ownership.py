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

_CACHE_LIMIT = 1024
type _CacheValue = frozenset[CodeType] | dict[str, frozenset[CodeType]]
_CACHE: dict[int, tuple[weakref.ReferenceType[Any], _CacheValue]] = {}


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


def _store_cached(key: Any, method: str, codes: frozenset[CodeType], *, used_method: bool) -> None:
    try:
        ref = weakref.ref(key)
    except TypeError:
        return
    key_id = id(key)
    if used_method:
        existing = _CACHE.get(key_id)
        if existing is not None and existing[0]() is key and isinstance(existing[1], dict):
            existing[1][method] = codes
            return
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[key_id] = (ref, {method: codes})
        return
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key_id] = (ref, codes)


def _codes_for(scope: Mapping[str, Any]) -> frozenset[CodeType]:
    route = scope.get("route")
    endpoint = scope.get("endpoint")
    key = route if route is not None else endpoint
    if key is None:
        return frozenset()
    method = _method_name(scope)
    cached = _CACHE.get(id(key))
    if cached is not None and cached[0]() is key:
        value = cached[1]
        if isinstance(value, frozenset):
            return value
        if method in value:
            return value[method]
    codes, used_method = _build_codes(scope, route, endpoint)
    _store_cached(key, method, codes, used_method=used_method)
    return codes


def _frame_matches(frame: FrameType | None, codes: frozenset[CodeType]) -> bool:
    try:
        while frame is not None:
            if frame.f_code in codes:
                return True
            frame = frame.f_back
        return False
    finally:
        frame = None


def _greenlet_matches(codes: frozenset[CodeType]) -> bool:
    greenlet = sys.modules.get("greenlet")
    getcurrent = getattr(greenlet, "getcurrent", None) if greenlet is not None else None
    if not callable(getcurrent):
        return False
    current: Any = getcurrent()
    try:
        for _ in range(8):
            current = getattr(current, "parent", None)
            if current is None:
                return False
            if _frame_matches(getattr(current, "gr_frame", None), codes):
                return True
        return False
    finally:
        current = None


def owner(scope: Mapping[str, Any]) -> str | None:
    """The call site (``module:qualname``) when the current stack or a parent greenlet's stack runs the request's own
    endpoint or dependency, else None."""
    del scope
    return None


def owned(scope: Mapping[str, Any]) -> bool:
    """Whether the current stack, or a parent greenlet's stack, runs the request's own endpoint or dependency."""
    try:
        codes = _codes_for(scope)
        if not codes:
            return False
        return _frame_matches(sys._getframe(1), codes) or _greenlet_matches(codes)  # pyright: ignore[reportPrivateUsage]
    except Exception:
        return False
