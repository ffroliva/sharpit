"""Application loading and advisor assessment for the pytest adapter."""

from __future__ import annotations

import importlib
import os
import sys
import sysconfig
from collections.abc import Callable, Sequence
from fnmatch import fnmatch
from pathlib import Path
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
    "AUTODETECT",
    "TEST_FILES",
    "autodetect_apps",
    "bare_app_run",
    "no_app_run",
    "skip_reason",
    "load_app",
    "model_of",
    "run_advisors",
    "reconcile_workers",
    "select_app",
    "_load_app",
    "_model_of",
    "_run_advisors",
]


_HINT = "pass --sharpit-app module:attr"
AUTODETECT = "autodetect"  # evidence key that marks the runs autodetect made (placeholders and bare apps)
TEST_FILES = ("test_*.py", "*_test.py")  # pytest's python_files default


def skip_reason(names: Sequence[str], bare: str | None = None) -> str:
    """The one text for an autodetect skip: the report reason and the terminal line."""
    if bare is not None:
        return f"app {bare} has no application routes; rest-api skipped ({_HINT})"
    if names:
        return f"several apps found ({', '.join(names)}); {_HINT}"
    return f"no application found; rest-api skipped ({_HINT})"


def _classes(module: str, *names: str) -> frozenset[type]:
    found = sys.modules.get(module)
    if type(found) is not ModuleType:
        return frozenset()
    return frozenset(c for c in (vars(found).get(name) for name in names) if isinstance(c, type))


def _project_module(name: str, module: ModuleType, test_files: Sequence[str], skip_roots: tuple[str, ...]) -> bool:
    if name.partition(".")[0] == "sharpit" or name.rpartition(".")[2] == "conftest":
        return False
    file = vars(module).get("__file__")
    if not isinstance(file, str):
        return True  # built in memory: nothing says it is a library
    path = os.path.normcase(os.path.abspath(file))
    if {"site-packages", "dist-packages"} & set(Path(path).parts):
        return False
    base = os.path.basename(path)
    return not path.startswith(skip_roots) and not any(fnmatch(base, pattern) for pattern in test_files)


def _unwrap(app: object) -> list[int]:
    ids: list[int] = []
    for _ in range(16):  # middleware chains are short; the bound stops a cycle
        if app is None:
            break
        ids.append(id(app))
        try:
            app = vars(app).get("app")
        except TypeError:
            break
    return ids


def _mounted(app: object, mounts: frozenset[type]) -> list[int]:
    """Apps reachable through the candidate's Mount/Host routes (subclasses, middleware wrappers included)."""
    try:
        routes = list(cast("Any", app).routes)
    except Exception:  # noqa: BLE001 - introspection is defensive
        return []
    # shortcut: one route level; a mount nested inside a mounted app is not followed
    return [i for r in routes if not mounts.isdisjoint(type(r).__mro__) for i in _unwrap(getattr(r, "app", None))]


def autodetect_apps(test_files: Sequence[str] = TEST_FILES) -> tuple[tuple[str, object], ...]:
    """FastAPI/Starlette instances in loaded project-module globals; imports nothing, runs no module hook."""
    apps = _classes("starlette.applications", "Starlette") | _classes("fastapi.applications", "FastAPI")
    if not apps:
        return ()
    paths = sysconfig.get_paths()
    roots = tuple(os.path.normcase(os.path.abspath(paths[k])) for k in ("stdlib", "platstdlib") if k in paths)
    best: dict[int, tuple[tuple[int, str, int], str, object]] = {}
    for module_name, module in tuple(sys.modules.items()):
        if type(module) is not ModuleType or not _project_module(module_name, module, test_files, roots):
            continue
        for order, (attr, value) in enumerate(tuple(vars(module).items())):
            # type() and its MRO never run instance code; classes compare by identity
            if apps.isdisjoint(type(value).__mro__):
                continue
            key = (len(module_name), module_name, order)  # the same app gets the same name in every worker
            if id(value) not in best or key < best[id(value)][0]:
                best[id(value)] = (key, f"{module_name}:{attr}", value)
    mounts = _classes("starlette.routing", "Mount", "Host")
    mounted = {child for _, _, app in best.values() for child in _mounted(app, mounts)}
    return tuple(sorted(((n, v) for key, (_, n, v) in best.items() if key not in mounted), key=lambda c: c[0]))


def select_app(candidates: Sequence[tuple[str, object]]) -> tuple[str, object] | None:
    """Only a unique candidate is used (an explicit --sharpit-app never reaches autodetect)."""
    return candidates[0] if len(candidates) == 1 else None


def _marked(names: Sequence[str], require_app: bool, app: str | None = None, bare: str | None = None) -> AdvisorRun:
    status = "UNKNOWN" if require_app else "SKIPPED"
    return AdvisorRun("rest-api", status, (), {AUTODETECT: True}, skip_reason(names, bare), app)


def no_app_run(names: Sequence[str], require_app: bool) -> AdvisorRun | None:
    """The rest-api run when autodetect chose no app; None keeps the 0.3.0 no-application unknown."""
    if len(names) == 1 or (not names and require_app):
        return None
    return _marked(names, require_app)


def bare_app_run(name: str, require_app: bool) -> AdvisorRun:
    """An autodetected app with no application routes: skipped, not the install path's unknown."""
    return _marked((), require_app, app=name, bare=name)


def _placeholder(run: AdvisorRun) -> bool:
    return run.app is None and run.evidence.get(AUTODETECT) is True


def reconcile_workers(parts: Sequence[Any], names: Sequence[str], require_app: bool, snapshot: bool = False) -> None:
    """xdist controller: the union of worker candidates decides; an installed-app snapshot suppresses autodetect."""
    dropped = set(names) if snapshot or len(names) > 1 else set[str]()
    for part in parts:
        part.advisor_runs[:] = [r for r in part.advisor_runs if not _placeholder(r) and r.app not in dropped]
    if snapshot or any(r.advisor == "rest-api" for part in parts for r in part.advisor_runs):
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


def _configured_models(
    state: Any, load_app: Callable[[str], tuple[str, object]] | None
) -> list[tuple[str, ApiModel]] | None:
    try:
        name, app = (load_app or _load_app)(state.options.app)
        return [(name, FastApiIntrospector(app).api_model())]
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
        return None


def _discovered_models(state: Any) -> list[tuple[str, ApiModel]] | None:
    candidates = autodetect_apps(getattr(state, "test_files", TEST_FILES))
    state.autodetected = [name for name, _ in candidates]
    chosen = select_app(candidates)
    if chosen is None:
        if (run := no_app_run(state.autodetected, state.options.require_app)) is not None:
            state.sink.facts.advisor_runs.append(run)
        return None
    model = FastApiIntrospector(chosen[1]).api_model()
    if not application_routes(model.routes):
        state.sink.facts.advisor_runs.append(bare_app_run(chosen[0], state.options.require_app))
        return None
    return [(chosen[0], model)]


def _models_to_assess(
    state: Any, load_app: Callable[[str], tuple[str, object]] | None
) -> list[tuple[str, ApiModel]] | None:
    models = state.sink.app_snapshots()
    if state.options.app:
        return _configured_models(state, load_app)
    return models or _discovered_models(state)


def run_advisors(
    state: Any,
    *,
    load_app: Callable[[str], tuple[str, object]] | None = None,
    assess_fn: Callable[..., AdvisorRun] | None = None,
) -> None:
    if not state.options.advisors:
        return
    models = _models_to_assess(state, load_app)
    if models is None:
        return
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
                    **_assessment_options(state),
                )
            )


def _assessment_options(state: Any) -> dict[str, Any]:
    options: dict[str, Any] = {}
    pairs: set[tuple[str, str]] = getattr(state, "dismissed_pairs", set())
    if pairs:
        options["dismissed_pairs"] = pairs
    baseline: dict[str, int | None] | None = getattr(state, "baseline_observed", None)
    if baseline is not None:
        options["baseline"] = baseline
    return options


_load_app = load_app
_model_of = model_of
_run_advisors = run_advisors
