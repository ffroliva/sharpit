"""The ``sharpit_http_observed`` fixture: the one way a host test hands an app to the HTTP security observer."""

from __future__ import annotations

from collections.abc import Callable

import pytest


@pytest.fixture
def sharpit_http_observed(request: pytest.FixtureRequest) -> Callable[[object], object]:
    """A factory: ``client = TestClient(sharpit_http_observed(app))``; observation is off unless opted in."""
    del request

    def observe(app: object) -> object:
        return app

    return observe
