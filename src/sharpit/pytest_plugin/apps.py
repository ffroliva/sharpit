"""Application loading and advisor assessment for the pytest adapter."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any, cast

from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.engine.advisors.rules import Severity
from sharpit.engine.collectors.restapi.rules import application_routes
from sharpit.engine.collectors.restapi.service import assess
from sharpit.engine.spi import ApiModel
from sharpit.engine.testsession.sink import report_masker
from sharpit.fastapi.introspector import FastApiIntrospector

__all__ = ["load_app", "model_of", "run_advisors", "_load_app", "_model_of", "_run_advisors"]


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
    if not models:
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
                )
            )


_load_app = load_app
_model_of = model_of
_run_advisors = run_advisors
