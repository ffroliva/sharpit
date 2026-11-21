"""The Flask observer: patch the exact app's ``wsgi_app`` in place, resolve the route before the view runs (T1).

``FlaskClient`` needs the real ``Flask`` instance, so the app cannot be wrapped the way an ASGI app is: observation
patches ``app.wsgi_app`` and the returned callable restores it. Flask is never imported here; the route matcher is the
app's own.
"""

from __future__ import annotations

import contextlib
import weakref
from collections.abc import Callable, Iterable
from typing import Any, cast

from sharpit.engine.advisors.http_security import normalize_route

Record = Callable[[str, str, str, int, Iterable[str]], None]
_PATCHED: weakref.WeakSet[Any] = weakref.WeakSet()


def route_of(app: Any, environ: dict[str, Any]) -> tuple[str, str]:
    """``(state, template)`` from a second match on the app's URL map; it runs no view and alters no request.

    Not found is ``not_found``; a redirect, a refused method, a missing matcher or any failure is ``unobservable``:
    nothing the matcher raises reaches the host.
    """
    try:
        from werkzeug.exceptions import NotFound  # lazy: only an observed Flask app reaches here

        url_map = app.url_map
        subdomain = None if getattr(app, "subdomain_matching", False) else (url_map.default_subdomain or None)
        adapter = url_map.bind_to_environ(environ, server_name=app.config.get("SERVER_NAME"), subdomain=subdomain)
        try:
            rule, _ = adapter.match(return_rule=True)
        except NotFound:
            return "not_found", ""
        return "matched", normalize_route(str(rule.rule))
    except Exception:  # noqa: BLE001 - introspection is defensive
        return "unobservable", ""


def observe_flask(app: Any, record: Record) -> Callable[[], None]:
    """Patch ``app.wsgi_app`` once; the returned callable puts back exactly what was there."""
    if app in _PATCHED:
        return lambda: None
    own = cast("dict[str, Any]", vars(app))
    had = "wsgi_app" in own
    original = app.wsgi_app

    def wsgi_app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Any:
        state, template = route_of(app, environ)
        method = str(environ.get("REQUEST_METHOD", "")).upper()
        recorded = False

        def watching(status: str, headers: list[tuple[str, str]], *rest: Any) -> Any:
            nonlocal recorded
            if not recorded:  # the first response start is the exchange; no start, no exchange
                recorded = True
                with contextlib.suppress(Exception):  # observation never costs the host its response
                    record(method, state, template, int(status.split(None, 1)[0]), [name for name, _ in headers])
            return start_response(status, headers, *rest)

        return original(environ, watching)

    def restore() -> None:
        _PATCHED.discard(app)
        if had:
            app.wsgi_app = original
        else:
            own.pop("wsgi_app", None)

    _PATCHED.add(app)
    own["wsgi_app"] = wsgi_app
    return restore
