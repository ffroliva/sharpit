"""A shared class-method wrap helper for capture integrations.

``wrap`` replaces ``owner.__dict__[name]`` (a plain function, ``staticmethod`` or ``classmethod``) with the function
``make`` builds around it, and returns a remover. It reads the raw ``__dict__`` entry (``getattr`` would bind or run a
descriptor), never raises into the host, and is independent of the capture-hook registry: callers that need
suspend/resume check their own flag inside ``make``'s wrapper, as ``fastapi/capture.py`` does.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

_TAG = "__sharpit_tag__"
_SELF = "__sharpit_wrapper__"  # the wrapper itself: functools.wraps copies the attribute, not the identity
_LOCK = threading.RLock()


def _inner(entry: Any) -> Any:
    func: Any = entry.__func__ if type(entry) in (staticmethod, classmethod) else entry
    return func


def _ours(entry: Any, tag: str | None = None) -> bool:
    inner = _inner(entry)
    owner_of_mark: Any = getattr(inner, _SELF, None)
    mark_tag: Any = getattr(inner, _TAG, None)
    return owner_of_mark is inner and (tag is None or mark_tag == tag)


def wrap(
    owner: type,
    name: str,
    make: Callable[[Callable[..., Any]], Callable[..., Any]],
    *,
    tag: str,
) -> Callable[[], bool] | None:
    """Wrap ``owner.name``; answer a remover, or ``None`` when nothing was wrapped.

    ``None`` means: the entry is missing from ``owner.__dict__`` (including an inherited one), is not a function,
    ``staticmethod`` or ``classmethod``, is already this ``tag``'s wrapper, or the wrap failed (``make`` raised, the
    owner refuses ``setattr``); the owner is then unchanged. The remover restores the original only while
    ``owner.__dict__[name]`` is still this wrapper and answers whether it did, so a second call or a foreign wrapper
    installed after ours makes it a no-op that answers ``False``.
    """
    with _LOCK:
        try:
            entry: Any = owner.__dict__.get(name)
            func = _inner(entry)
            if not callable(func) or isinstance(entry, type) or _ours(entry, tag):
                return None
            wrapped = make(func)
            wrapped.__sharpit_original__ = func  # type: ignore[attr-defined]
            setattr(wrapped, _TAG, tag)
            setattr(wrapped, _SELF, wrapped)
            new: Any = type(entry)(wrapped) if type(entry) in (staticmethod, classmethod) else wrapped
            setattr(owner, name, new)
        except Exception:  # noqa: BLE001 - a failed wrap never reaches the host
            return None

    def remove() -> bool:
        with _LOCK:
            try:
                if owner.__dict__.get(name) is not new:
                    return False
                setattr(owner, name, entry)
            except Exception:  # noqa: BLE001
                return False
            return True

    return remove
