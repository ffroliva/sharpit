"""The ``sharpit_http_observed`` fixture: the one way a host test hands an app to the HTTP security observer."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Iterator

import pytest

from sharpit.pytest_plugin.http_security_asgi import ObservedASGI

Record = Callable[[str, str, str, int, Iterable[str]], None]


def _is_asgi(app: object) -> bool:
    return inspect.iscoroutinefunction(app) or inspect.iscoroutinefunction(type(app).__call__)


def _is_flask(app: object) -> bool:
    return hasattr(app, "wsgi_app") and hasattr(app, "url_map")


def observe_app(app: object, record: Record, restores: list[Callable[[], None]]) -> object:
    """The app to hand the test client: Flask is patched in place, an ASGI app wrapped, anything else left unseen."""
    if _is_flask(app):
        from sharpit.pytest_plugin.http_security_flask import observe_flask  # lazy: Flask is never imported at load

        restores.append(observe_flask(app, record))
        return app
    if _is_asgi(app):
        return ObservedASGI(app, record)
    return app  # an opaque wrapper: nothing is observed, so a configured expectation stays UNKNOWN


@pytest.fixture
def sharpit_http_observed(request: pytest.FixtureRequest) -> Iterator[Callable[[object], object]]:
    """A factory: ``client = TestClient(sharpit_http_observed(app))``; observation is off unless opted in.

    Off, it returns the app itself. On, only requests made through the returned app are observed: an ASGI app is
    wrapped (the same wrapper for the same app within a test), a Flask app is patched in place and restored at teardown.
    """
    from sharpit import pytest_plugin  # lazy: the facade imports this module

    state = pytest_plugin._state(request.config)  # pyright: ignore[reportPrivateUsage]
    if state is None or not state.options.http_security_enabled:
        yield lambda app: app
        return
    seen: dict[int, tuple[object, object]] = {}
    restores: list[Callable[[], None]] = []

    def observe(app: object) -> object:
        cached = seen.get(id(app))
        if cached is None or cached[0] is not app:
            cached = seen[id(app)] = (app, observe_app(app, state.sink.on_http, restores))
        return cached[1]

    try:
        yield observe
    finally:
        for restore in reversed(restores):
            restore()
