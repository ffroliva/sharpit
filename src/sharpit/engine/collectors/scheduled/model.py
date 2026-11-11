"""The scheduled-task DTO, the discovery result and the helpers each scheduler gatekeeper shares.

Readers never call a method on an unknown object: ``type()`` and ``vars()`` find things, and attributes are read
only on library classes matched by type (see each gatekeeper).
"""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from types import BuiltinFunctionType, FunctionType, MethodType
from typing import Any, cast


@dataclass
class Discovery:
    present: bool
    tasks: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    limitations: list[str] = field(default_factory=list[str])


Reader = Callable[[str, object], Discovery | None]  # (label, module global) -> what it found; None: not its type


def task(
    runnable: str | None,
    trigger_type: str,
    expression: str | None = None,
    initial_delay_ms: int | None = None,
    time_unit: str | None = None,
) -> dict[str, Any]:
    """``ScheduledTaskDto``: every key, nulls included."""
    return {
        "runnable": runnable,
        "triggerType": trigger_type,
        "expression": expression,
        "initialDelayMs": initial_delay_ms,
        "timeUnit": time_unit,
    }


def interval_unit(interval_ms: int | None, initial_delay_ms: int | None) -> str:
    """``ScheduledTimeUnits.intervalUnit``: ``s`` when both values are whole seconds (or null), else ``ms``."""
    return "s" if all(v is None or v % 1000 == 0 for v in (interval_ms, initial_delay_ms)) else "ms"


def fixed_rate(runnable: str | None, interval_ms: int) -> dict[str, Any]:
    return task(runnable, "FIXED_RATE", str(interval_ms), None, interval_unit(interval_ms, None))


def as_list(value: Any) -> list[Any]:
    """A copy of ``value`` when it is exactly a list or tuple (a subclass could run code on iteration), else empty."""
    return list(cast("list[Any]", value)) if type(value) in (list, tuple) else []


def as_dict(value: Any) -> dict[Any, Any]:
    """A copy of ``value`` when it is exactly a dict, else empty."""
    return dict(cast("dict[Any, Any]", value)) if type(value) is dict else {}


def _order(item: int | str) -> tuple[bool, int, str]:
    return (type(item) is str, item if type(item) is int else 0, str(item))


def cron_field(value: Any) -> str:
    """One cron field from a library's literal: ``*`` when unset, the value, or a sorted comma list; else ``?``."""
    if value is None:
        return "*"
    if type(value) in (int, str):
        return str(value)
    items: list[Any] = list(value) if type(value) in (set, frozenset, list, tuple, range) else [None]
    if all(type(item) in (int, str) for item in items):
        return ",".join(str(item) for item in sorted(items, key=_order))
    return "?"


def library_class(module: str, name: str) -> type | None:
    """A class of an already-loaded library, read from ``sys.modules`` with ``vars()``: never imported, no hook."""
    loaded = sys.modules.get(module)
    found = vars(loaded).get(name) if loaded is not None else None
    return found if found is not None and type in type(found).__mro__ else None  # a class, whatever its metaclass


def is_a(value: object, cls: type | None) -> bool:
    """``isinstance`` without ``__class__``: a lazy proxy is judged by its own type and never evaluated."""
    return cls is not None and cls in type(value).__mro__


def attrs(value: object) -> dict[str, Any]:
    """``vars(value)``: the instance namespace, read without ``__getattr__`` or a property."""
    return vars(value)


def exact(value: object, cls: type | None) -> bool:
    """``type(value) is cls``: a library class only, never a host subclass that could run code on attribute access."""
    return cls is not None and type(value) is cls


def qualified_name(fn: Any) -> str | None:
    """``module.qualname`` of a plain function; a callable object is named by its class, never by its repr."""
    if fn is None:
        return None
    if type(fn) is functools.partial:
        fn = fn.func
    if type(fn) is MethodType:
        fn = fn.__func__
    if type(fn) in (FunctionType, BuiltinFunctionType):
        return f"{fn.__module__}.{fn.__qualname__}"
    return f"{type(fn).__module__}.{type(fn).__qualname__}"
