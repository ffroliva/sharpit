"""Static helpers shared by the FastAPI introspection responsibilities."""

from __future__ import annotations

import types
from typing import cast

MAX_DEPTH = 32
OWN_MODULE_PREFIX = "sharpit."


def attrs(obj: object) -> dict[str, object]:
    """``obj``'s own attributes, read statically; ``{}`` for an object without ``__dict__``.

    ``object.__getattribute__`` skips a user ``__getattribute__`` and never falls back to ``__getattr__`` (``vars()``
    does both).
    """
    try:
        values = object.__getattribute__(obj, "__dict__")
    except Exception:  # noqa: BLE001 - slots, built-ins, and framework drift degrade to no attributes
        return {}
    return cast(dict[str, object], values) if isinstance(values, dict | types.MappingProxyType) else {}


def dotted(cls: object) -> str:
    return f"{getattr(cls, '__module__', None) or '?'}.{getattr(cls, '__qualname__', '?')}"


def as_objects(value: object) -> tuple[object, ...]:
    if isinstance(value, list):
        return tuple(cast(list[object], value))
    if isinstance(value, tuple):
        return cast(tuple[object, ...], value)
    return ()
