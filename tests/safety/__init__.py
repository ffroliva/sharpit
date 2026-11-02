"""Per-lane safety rows (council C5): each panel lane documents its routes in tests/safety/test_<lane>_safety.py.

A lane file exports ``PANEL`` (the sharpit panel id), ``GET_ROWS`` (every GET route path format it adds, e.g.
``"/sharpit/api/data/{name}"``) and ``WRITE_ROWS`` (every POST/DELETE route as ``(method, path format)``). The shared
``tests/test_safety_matrix.py`` route-table tests add those rows only while the panel is implemented, so no lane edits
the shared matrix. See README.md.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent


def lane_rows(root: Path = HERE) -> tuple[set[str], set[tuple[str, str]]]:
    """``(GET path formats, (method, path format) writes)`` exported by the lane files of implemented panels."""
    from sharpit.engine.panels import panel_is_implemented

    gets: set[str] = set()
    writes: set[tuple[str, str]] = set()
    for path in sorted(root.glob("test_*_safety.py")):
        spec = importlib.util.spec_from_file_location(f"_sharpit_lane_rows_{path.stem}", path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if panel_is_implemented(module.PANEL):
            gets |= set(getattr(module, "GET_ROWS", ()))
            writes |= {(method, fmt) for method, fmt in getattr(module, "WRITE_ROWS", ())}
    return gets, writes


def route_formats(app: Any, methods: frozenset[str]) -> set[tuple[str, str]]:
    """``(method, "/sharpit" + path format)`` of every sharpit sub-app route answering one of ``methods``."""
    from sharpit.fastapi.adapter import SharpitMount

    mount = next(r for r in app.router.routes if isinstance(r, SharpitMount))
    return {
        (method, "/sharpit" + route.path_format)
        for route in mount.routes
        for method in methods & set(getattr(route, "methods", None) or ())
    }
