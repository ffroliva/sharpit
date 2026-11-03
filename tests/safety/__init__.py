"""Per-lane safety rows (council C5): each panel lane documents its routes in tests/safety/test_<lane>_safety.py.

A lane file may export ``PANEL`` (a sharpit panel id with a per-panel module: a 0.4 id or ``sql-trace``),
``GET_ROWS`` (every GET route path format the panel adds), ``WRITE_ROWS`` (every POST/PUT/PATCH/DELETE route as
``(method, path format)``) and ``PATH_PARAMS`` (sample values for new path parameters). ``tests/test_safety_matrix.py``
feeds the rows of implemented panels into the same sweeps as its base rows (route-table completeness, disabled-panel
denial, read-only denial), so no lane edits the shared matrix. See README.md.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_CONVERTOR = re.compile(r"\{(\w+):[^}]+\}")


@dataclass(frozen=True)
class Lane:
    file: str
    panel: str
    gets: tuple[str, ...]  # GET path formats, Starlette convertors stripped
    writes: tuple[tuple[str, str], ...]  # (method, path format)
    params: dict[str, str] = field(default_factory=dict[str, str])  # PATH_PARAMS: samples for this lane's rows only
    cli_actions: tuple[str, ...] = ()  # CLI_ACTIONS: the lane's CLI-only action tools (never on MCP)


@dataclass(frozen=True)
class Lanes:
    implemented: tuple[Lane, ...]  # lane files whose PANEL is implemented
    invalid: tuple[str, ...]  # "<file>: <problem>" (bad PANEL or row shape): the route-table tests fail on these
    unimportable: tuple[str, ...]  # "<file>: <exception>": no rows; reported when the live table is not covered
    params: dict[str, str]  # PATH_PARAMS of every importable lane file (informational: never applied to base rows)


def _strip(fmt: str) -> str:
    return _CONVERTOR.sub(r"{\1}", fmt)


def _is_write_row(row: object) -> bool:
    return (
        isinstance(row, tuple)
        and len(row) == 2  # pyright: ignore[reportUnknownArgumentType]
        and row[0] in WRITE_METHODS
        and isinstance(row[1], str)
        and row[1].startswith("/sharpit")
    )


def _problems(module: Any) -> list[str]:
    problems: list[str] = []
    gets = getattr(module, "GET_ROWS", [])
    if not isinstance(gets, list | tuple) or not all(isinstance(g, str) and g.startswith("/sharpit") for g in gets):
        problems.append("GET_ROWS must be a list of path formats starting with /sharpit")
    writes = getattr(module, "WRITE_ROWS", [])
    if not isinstance(writes, list | tuple) or not all(_is_write_row(w) for w in writes):
        problems.append("WRITE_ROWS must be a list of (method, path format) tuples, method POST/PUT/PATCH/DELETE")
    params = getattr(module, "PATH_PARAMS", {})
    if not isinstance(params, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in params.items()):
        problems.append("PATH_PARAMS must map parameter names to sample strings")
    return problems


def load(package: str = "safety") -> Lanes:
    """Import every ``test_*_safety.py`` of ``package`` as ``<package>.<stem>`` (pytest's own import, cached)."""
    from sharpit.engine import panels04

    root = Path(next(iter(importlib.import_module(package).__path__)))
    implemented: list[Lane] = []
    invalid: list[str] = []
    unimportable: list[str] = []
    params: dict[str, str] = {}
    for path in sorted(root.glob("test_*_safety.py")):
        try:
            module = importlib.import_module(f"{package}.{path.stem}")
        except (Exception, pytest.skip.Exception) as exc:  # a module-level skip must not skip the shared tests
            unimportable.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        if problems := _problems(module):
            invalid += [f"{path.name}: {problem}" for problem in problems]
            continue
        params.update(getattr(module, "PATH_PARAMS", {}))
        panel = getattr(module, "PANEL", None)
        if panel is None:  # a safety file for base routes (e.g. D1) adds tests, no rows
            continue
        if panel not in panels04.MODULE_PANEL_IDS:
            invalid.append(f"{path.name}: PANEL {panel!r} is not one of {panels04.MODULE_PANEL_IDS}")
            continue
        if panels04.module_implemented(panel):
            gets = tuple(_strip(g) for g in getattr(module, "GET_ROWS", []))
            writes = tuple((m, _strip(p)) for m, p in getattr(module, "WRITE_ROWS", []))
            implemented.append(Lane(path.name, panel, gets, writes, dict(getattr(module, "PATH_PARAMS", {}))))
    return Lanes(tuple(implemented), tuple(invalid), tuple(unimportable), params)


def write_cases(
    base: list[tuple[str, str, str, Any]], lanes: Lanes, params: dict[str, str]
) -> list[tuple[str, str, str, Any]]:
    """The read-only sweep's ``(panel, method, concrete path, body)`` cases: the base rows plus every lane write."""
    lane_cases = [
        (lane.panel, m, p.format(**{**params, **lane.params}), None)
        for lane in lanes.implemented
        for m, p in lane.writes
    ]
    return [*base, *lane_cases]


def get_rows(lanes: Lanes, params: dict[str, str]) -> set[str]:
    """Concrete GET paths of the implemented lanes (``{param}`` filled from ``params``)."""
    return {g.format(**{**params, **lane.params}) for lane in lanes.implemented for g in lane.gets}


def write_rows(lanes: Lanes) -> set[tuple[str, str]]:
    return {w for lane in lanes.implemented for w in lane.writes}


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


def sample_params(path_format: str, lanes: Lanes, base: dict[str, str]) -> dict[str, str]:
    """Samples for one route format: the base samples, plus a lane's PATH_PARAMS only when the route is that lane's."""
    owner = next(
        (
            lane
            for lane in lanes.implemented
            if path_format in lane.gets or any(path_format == p for _m, p in lane.writes)
        ),
        None,
    )
    return {**base, **(owner.params if owner is not None else {})}
