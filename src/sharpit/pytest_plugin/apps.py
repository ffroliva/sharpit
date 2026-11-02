"""Application loading and advisor assessment for the pytest adapter."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Sequence
from types import ModuleType
from typing import Any, cast

from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.engine.advisors.rules import Severity
from sharpit.engine.collectors.restapi.rules import application_routes
from sharpit.engine.collectors.restapi.service import assess
from sharpit.engine.spi import ApiModel
from sharpit.engine.testsession.sink import report_masker
from sharpit.fastapi.introspector import FastApiIntrospector

__all__ = [
    "NO_APP_REASON",
    "autodetect_apps",
    "load_app",
    "model_of",
    "run_advisors",
    "reconcile_workers",
    "select_app",
    "_load_app",
    "_model_of",
    "_run_advisors",
]


_APP_CLASSES = frozenset({"fastapi.applications.FastAPI", "starlette.applications.Starlette"})
NO_APP_REASON = "no application found; rest-api skipped (pass --sharpit-app module:attr)"
_SEVERAL = "several apps found ("


def _is_app(value: object) -> bool:
    # type() and the MRO never run instance code (no __class__ property, no __getattr__)
    return any(f"{cls.__module__}.{cls.__qualname__}" in _APP_CLASSES for cls in type(value).__mro__)


def _mounted(app: object) -> list[int]:
    try:
        routes = list(cast("Any", app).routes)
    except Exception:  # noqa: BLE001 - introspection is defensive
        return []
    # shortcut: one mount level only; nested mounts inside a mounted app would still count as candidates
    return [id(route.app) for route in routes if type(route).__name__ == "Mount" and hasattr(route, "app")]


def autodetect_apps() -> tuple[tuple[str, object], ...]:
    """FastAPI/Starlette instances in already-loaded module globals; imports nothing, runs no module hook."""
    found: dict[int, tuple[str, object]] = {}
    for module_name, module in list(sys.modules.items()):
        if type(module) is not ModuleType or module_name.partition(".")[0] == "sharpit":
            continue
        for attr, value in list(vars(module).items()):
            if _is_app(value):
                found.setdefault(id(value), (f"{module_name}:{attr}", value))  # first-defined name wins
    mounted = {child for _, app in found.values() for child in _mounted(app)}
    return tuple(sorted((c for key, c in found.items() if key not in mounted), key=lambda c: c[0]))


def select_app(explicit: str | None, candidates: Sequence[tuple[str, object]]) -> tuple[str, object] | None:
    """An explicit app wins over candidates; otherwise only a unique candidate is used."""
    return candidates[0] if len(candidates) == 1 else None


def no_app_run(names: Sequence[str], require_app: bool) -> AdvisorRun | None:
    """The rest-api run when autodetect chose no app; None keeps the 0.3.0 no-application unknown."""
    if not names:
        return None if require_app else AdvisorRun("rest-api", "SKIPPED", (), {}, NO_APP_REASON, None)
    if len(names) == 1:
        return None
    reason = f"{_SEVERAL}{', '.join(names)}); pass --sharpit-app module:attr"
    return AdvisorRun("rest-api", "UNKNOWN" if require_app else "SKIPPED", (), {}, reason, None)


def _placeholder(run: AdvisorRun) -> bool:
    reason = run.reason or ""
    return run.app is None and (reason == NO_APP_REASON or reason.startswith(_SEVERAL))


def reconcile_workers(parts: Sequence[Any], names: Sequence[str], require_app: bool) -> None:
    """xdist controller: uniqueness is decided over the union of worker candidates, not per worker."""
    ambiguous = len(names) > 1
    for part in parts:
        part.advisor_runs[:] = [
            r for r in part.advisor_runs if not _placeholder(r) and not (ambiguous and r.app in names)
        ]
    if any(r.advisor == "rest-api" for part in parts for r in part.advisor_runs):
        return
    if parts and (run := no_app_run(names, require_app)) is not None:
        parts[0].advisor_runs.append(run)


def load_app(spec: str) -> tuple[str, object]:
    module_name, separator, attr = spec.partition(":")
    if not separator:
        raise ValueError("--sharpit-app must be MOD:ATTR")
    app = getattr(importlib.import_module(module_name), attr)
    return spec, app() if callable(app) and not hasattr(app, "router") else app


def model_of(app: object) -> ApiModel:
    return FastApiIntrospector(app).api_model()


def run_advisors(
    state: Any,
    *,
    load_app: Callable[[str], tuple[str, object]] | None = None,
    assess_fn: Callable[..., AdvisorRun] | None = None,
) -> None:
    if not state.options.advisors:
        return
    models = state.sink.app_snapshots()
    if state.options.app:
        try:
            name, app = (load_app or _load_app)(state.options.app)
            models = [(name, FastApiIntrospector(app).api_model())]
        except Exception as exc:  # noqa: BLE001
            state.sink.facts.advisor_runs.append(
                AdvisorRun(
                    "rest-api",
                    "UNKNOWN",
                    (),
                    {},
                    f"application could not load ({type(exc).__name__})",
                    state.options.app,
                )
            )
            return
    elif not models:
        candidates = autodetect_apps()
        state.autodetected = [name for name, _ in candidates]
        chosen = select_app(None, candidates)
        if chosen is None:
            if (run := no_app_run(state.autodetected, False)) is not None:
                state.sink.facts.advisor_runs.append(run)
            return
        models = [(chosen[0], FastApiIntrospector(chosen[1]).api_model())]
    for name, model in models:
        if not application_routes(model.routes) and not state.options.app:
            state.sink.facts.advisor_runs.append(
                AdvisorRun("rest-api", "UNKNOWN", (), {}, "no routes seen after install", name)
            )
        else:
            state.sink.facts.advisor_runs.append(
                (assess_fn or assess)(
                    model,
                    report_masker(),
                    fail_on=cast("Severity", state.options.fail_on),
                    app=name,
                    dismissed=state.dismissed,
                )
            )


_load_app = load_app
_model_of = model_of
_run_advisors = run_advisors
