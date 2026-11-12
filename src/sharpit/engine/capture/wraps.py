"""A shared class-method wrap helper for capture integrations.

``wrap`` replaces ``owner.__dict__[name]`` (a plain function, ``staticmethod`` or ``classmethod``) with the function
``make`` builds around it, and returns a remover. It reads the raw ``__dict__`` entry (``getattr`` would bind or run a
descriptor), never raises into the host, and is independent of the capture-hook registry: callers that need
suspend/resume check their own flag inside ``make``'s wrapper, as ``fastapi/capture.py`` does.

Only exact ``types.FunctionType`` objects are wrapped. A ``unittest.mock`` object, a ``wrapt`` wrapper, a builtin, a
``functools.partial``, a callable instance or a ``staticmethod``/``classmethod`` subclass answers ``None`` and is left
untouched: wrapping it in a plain function would bind ``self`` and change the host's call. The classifier uses
``type(x) is ...`` and ``__dict__`` reads only, so no host ``__class__``, ``__getattr__`` or ``__eq__`` ever runs.

Stacking and removal contract:

* ``make``'s wrapper must check its own detached flag. A remover whose wrapper is no longer the current entry answers
  ``False`` and leaves it in the chain, so the wrapper stays live and must go quiet by itself.
* Callers remove their wraps in reverse order (LIFO). Removing the inner wrap first answers ``False`` and keeps the
  outer wrap intact.
* A foreign wrapper installed over ours, followed by a second ``install()``, stacks a second layer (our marker is no
  longer the current entry); the caller keeps its own installed flag to avoid that.
"""

from __future__ import annotations

import threading
import types
from collections.abc import Callable
from typing import Any

_TAG = "__sharpit_tag__"
_SELF = "__sharpit_wrapper__"  # the wrapper itself: functools.wraps copies the attribute, not the identity
_LOCK = threading.RLock()


def _descriptor(entry: Any) -> bool:
    # identity only: `type(entry) in (staticmethod, classmethod)` would run a metaclass __eq__
    return type(entry) is staticmethod or type(entry) is classmethod


def _inner(entry: Any) -> types.FunctionType | None:
    """The plain function inside a raw ``__dict__`` entry, or ``None`` for anything else (the single classifier)."""
    func: Any = entry.__func__ if _descriptor(entry) else entry
    return func if type(func) is types.FunctionType else None


def _ours(func: types.FunctionType, tag: str) -> bool:
    attrs = func.__dict__
    return attrs.get(_SELF) is func and attrs.get(_TAG) == tag


def wrap(
    owner: type,
    name: str,
    make: Callable[[Callable[..., Any]], Callable[..., Any]],
    *,
    tag: str,
) -> Callable[[], bool] | None:
    """Wrap ``owner.name``; answer a remover, or ``None`` when nothing was wrapped.

    ``None`` means: the entry is missing from ``owner.__dict__`` (including an inherited one), is not a plain function
    or an exact ``staticmethod``/``classmethod`` around one, is already this ``tag``'s wrapper, or the wrap failed
    (``make`` raised or returned the function itself or a non-function, the owner refuses ``setattr``); the owner is
    then unchanged. The remover restores the original only while ``owner.__dict__[name]`` is still this wrapper and
    answers whether it did, so a second call or a foreign wrapper installed after ours makes it a no-op that answers
    ``False``.
    """
    with _LOCK:
        try:
            entry: Any = owner.__dict__.get(name)
            func = _inner(entry)
            if func is None or _ours(func, tag):
                return None
            wrapped = make(func)
            if wrapped is func or type(wrapped) is not types.FunctionType:
                return None
            wrapped.__sharpit_original__ = func  # type: ignore[attr-defined]
            setattr(wrapped, _TAG, tag)
            setattr(wrapped, _SELF, wrapped)
            new: Any = type(entry)(wrapped) if _descriptor(entry) else wrapped
            setattr(owner, name, new)
            if owner.__dict__.get(name) is not new:  # a metaclass __setattr__ that ignored or transformed the value
                if owner.__dict__.get(name) is not entry:
                    setattr(owner, name, entry)
                return None
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
