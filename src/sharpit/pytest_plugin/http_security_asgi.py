"""The FastAPI/Starlette observer: a separate ASGI callable around the exact app the test supplies (T1).

Every message passes through unchanged and no body is read. What is kept of an exchange is its method, status, the
presence of the configured response headers and the route template of the matched route; nothing the client sent.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, MutableMapping
from typing import Any

from sharpit.engine.advisors.http_security import normalize_route

Record = Callable[[str, str, str, int, Iterable[str]], None]
_MAX_DEPTH = 8  # mounts nest a few levels; the bound stops a cycle


def _find_template(routes: Iterable[Any], target: object, prefix: str = "", depth: int = 0) -> str | None:
    """The full template of ``target`` in the route tree: mount prefixes composed with the route's own format."""
    for route in routes:
        if route is target:
            return normalize_route(prefix + (getattr(route, "path_format", None) or getattr(route, "path", "")))
        children = getattr(route, "routes", None)
        if children and depth < _MAX_DEPTH:
            found = _find_template(children, target, prefix + str(getattr(route, "path", "")), depth + 1)
            if found is not None:
                return found
    return None


class ObservedASGI:
    """``client = TestClient(ObservedASGI(app, sink.on_http))``: the app itself is never touched."""

    def __init__(self, app: Any, record: Record) -> None:
        self.__wrapped__ = app
        self._sharpit_record = record
        self._sharpit_templates: dict[int, tuple[object, str | None]] = {}
        self._sharpit_mounts: tuple[int, tuple[str, ...]] = (-1, ())

    def __getattr__(self, name: str) -> Any:
        if name == "__wrapped__":
            raise AttributeError(name)
        return getattr(self.__wrapped__, name)  # state, router, dependency_overrides: host code inspects the app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http" or self._is_sharpit(scope):  # lifespan and websocket scopes are not exchanges
            await self.__wrapped__(scope, receive, send)
            return
        started: list[tuple[int, list[str]]] = []

        async def watching(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start" and not started:
                names = [bytes(name).decode("latin-1") for name, _ in message.get("headers", ())]
                started.append((int(message["status"]), names))
            await send(message)

        try:
            await self.__wrapped__(scope, receive, watching)
        finally:
            if started:  # no response start, no exchange: it can never satisfy an expectation
                self._observe(scope, *started[0])

    def _is_sharpit(self, scope: MutableMapping[str, Any]) -> bool:
        try:
            routes = getattr(self.__wrapped__, "routes", ())
            if self._sharpit_mounts[0] != len(routes):
                paths = tuple(str(r.path) for r in routes if getattr(r, "sharpit_handle", None) is not None)
                self._sharpit_mounts = (len(routes), paths)
            path = str(scope.get("path", ""))
            return any(path == mount or path.startswith(f"{mount}/") for mount in self._sharpit_mounts[1])
        except Exception:  # noqa: BLE001 - introspection is defensive
            return False

    def _observe(self, scope: MutableMapping[str, Any], status: int, names: list[str]) -> None:
        method = str(scope.get("method", "")).upper()
        route = scope.get("route")
        template = None if route is None else self._template(route)
        if route is None and status == 404:
            self._sharpit_record(method, "not_found", "", status, names)
        elif template is None:
            self._sharpit_record(method, "unobservable", "", status, names)
        else:
            self._sharpit_record(method, "matched", template, status, names)

    def _template(self, route: object) -> str | None:
        cached = self._sharpit_templates.get(id(route))
        if cached is None or cached[0] is not route:
            try:
                found = _find_template(list(getattr(self.__wrapped__, "routes", ())), route)
            except Exception:  # noqa: BLE001 - introspection is defensive
                found = None
            cached = self._sharpit_templates[id(route)] = (route, found)
        return cached[1]
