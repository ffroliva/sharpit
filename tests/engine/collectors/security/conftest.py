"""Fixtures for the security advisor's rule tests: one rule over a real FastAPI app, read statically."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine import appsource
from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.collectors.security import Inputs, View
from sharpit.engine.collectors.security.report import SecurityService, check
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.fastapi.introspector import FastApiIntrospector

RuleRun = Callable[..., list[tuple[str, str]]]


def inputs_for(app: Any, source: Path | None = None, view: View | None = None) -> Inputs:
    introspector = FastApiIntrospector(app)
    index = appsource.build_index(source, thread=False) if source is not None else None
    return Inputs(introspector.security_model(), introspector.security_facts(), index, view or View())


@pytest.fixture
def inputs_of() -> Callable[..., Inputs]:
    """``inputs_of(app, source=None, view=None)``: the scan inputs for ``app``, read statically."""
    return inputs_for


@pytest.fixture
def run_rule() -> RuleRun:
    """``run_rule(rule_id, app, source=None, view=None)`` -> that rule's ``(target, message)`` pairs."""

    def run(rule_id: str, app: Any, source: Path | None = None, view: View | None = None) -> list[tuple[str, str]]:
        return [(v.target, v.message) for v in check(rule_id, inputs_for(app, source, view))]

    return run


@pytest.fixture
def service_for(tmp_path: Path) -> Callable[[Callable[[], Inputs]], SecurityService]:
    def make(inputs: Callable[[], Inputs]) -> SecurityService:
        masker = Masker(Exposure.MASKED, True)
        return SecurityService(inputs, DismissalStore(tmp_path), masker, SingleFlight(), max_retained=10000)

    return make
