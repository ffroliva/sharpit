"""Which stack frames are the host application's own code (spec §7.2): a file-path rule, cached per file name."""

from __future__ import annotations

import functools
import os
import sys
import sysconfig
from types import FrameType
from typing import Any

_STDLIB = tuple(
    dict.fromkeys(  # ordered de-duplication: stdlib and platstdlib are often the same directory
        os.path.normcase(os.path.abspath(p)) + os.sep
        for k in ("stdlib", "platstdlib")
        if (p := sysconfig.get_paths().get(k))
    )
)
_SHARPIT = os.path.normcase(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))) + os.sep  # sharpit/
_PACKAGE_DIRS = {"site-packages", "dist-packages"}


@functools.lru_cache(maxsize=4096)
def is_application_frame(filename: str) -> bool:
    """False for installed packages, the standard library, sharpit itself and synthetic files (``<frozen ...>``)."""
    if not filename or filename.startswith("<"):
        return False
    path = os.path.normcase(os.path.abspath(filename))
    if _PACKAGE_DIRS & set(path.split(os.sep)):
        return False
    return not path.startswith((*_STDLIB, _SHARPIT))


def _greenlet_parent() -> Any:
    """The current greenlet's parent, or None when greenlet is not loaded or the current greenlet has none."""
    greenlet_module = sys.modules.get("greenlet")
    if greenlet_module is None:
        return None
    return getattr(greenlet_module.getcurrent(), "parent", None)


def first_application_frame(frame: FrameType | None, limit: int = 64) -> FrameType | None:
    """The first application frame, walking f_back and then the greenlet parent's gr_frame chain;
    keeps no frame reference after return."""
    current = frame
    parent: Any = None
    greenlet_checked = False
    try:
        for _ in range(limit):
            if current is None:
                if not greenlet_checked:
                    parent = _greenlet_parent()
                    greenlet_checked = True
                if parent is None:
                    return None
                current, parent = parent.gr_frame, getattr(parent, "parent", None)
                if current is None:
                    return None
            if is_application_frame(current.f_code.co_filename):
                return current
            current = current.f_back
        return None
    finally:
        current = None
        parent = None


def call_site_label(frame: FrameType) -> str:
    """A call site formatted as ``module:qualname``, without a line number."""
    return f"{frame.f_globals.get('__name__', '?')}:{frame.f_code.co_qualname}"
