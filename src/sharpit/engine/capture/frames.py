"""Which stack frames are the host application's own code (spec §7.2): a file-path rule, cached per file name."""

from __future__ import annotations

import functools
import os
import sysconfig

_STDLIB = tuple(
    {
        os.path.normcase(os.path.abspath(p)) + os.sep
        for k in ("stdlib", "platstdlib")
        if (p := sysconfig.get_paths().get(k))
    }
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
