"""Per-lane safety rows (council C5): each panel lane documents its routes in tests/safety/test_<lane>_safety.py.

A lane file exports ``PANEL`` (the sharpit panel id), ``GET_ROWS`` (every GET route path format it adds, e.g.
``"/sharpit/api/data/{name}"``) and ``WRITE_ROWS`` (every POST/DELETE route as ``(method, path format)``). The shared
``tests/test_safety_matrix.py`` route-table tests add those rows only while the panel is implemented, so no lane edits
the shared matrix. See README.md.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
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


# --- round 1 API (stubs until the fix) ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Lane:
    file: str
    panel: str
    gets: tuple[str, ...]  # GET path formats, Starlette convertors stripped
    writes: tuple[tuple[str, str], ...]  # (method, path format)


@dataclass(frozen=True)
class Lanes:
    implemented: tuple[Lane, ...]  # lane files whose PANEL is implemented
    invalid: tuple[str, ...]  # "<file>: <problem>" (bad PANEL or row shape): the route-table tests fail on these
    unimportable: tuple[str, ...]  # "<file>: <exception>": no rows; reported when the live table is not covered
    params: dict[str, str]  # PATH_PARAMS from every importable lane file


def load(package: str = "safety") -> Lanes:
    return Lanes((), (), (), {})


def write_cases(
    base: list[tuple[str, str, str, Any]], lanes: Lanes, params: dict[str, str]
) -> list[tuple[str, str, str, Any]]:
    return list(base)


def get_rows(lanes: Lanes, params: dict[str, str]) -> set[str]:
    return set()


def write_rows(lanes: Lanes) -> set[tuple[str, str]]:
    return set()


def live_write_routes(app: Any, exempt: tuple[str, ...]) -> set[tuple[str, str]]:
    """(method, "/sharpit" + path format) of every write route of the installed sub-app, minus ``exempt`` prefixes."""
    from sharpit.fastapi.adapter import SharpitMount

    mount = next(r for r in app.router.routes if isinstance(r, SharpitMount))
    found: set[tuple[str, str]] = set()
    for route in mount.routes:
        path = "/sharpit" + getattr(route, "path_format", "")
        if any(path == "/sharpit" + s or path.startswith("/sharpit" + s.rstrip("/") + "/") for s in exempt):
            continue
        found |= {(m, path) for m in WRITE_METHODS & set(getattr(route, "methods", None) or ())}
    return found


WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
