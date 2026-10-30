"""FastAPI ``AppIntrospector`` (``providers`` lands in Task 10)."""

from __future__ import annotations

import functools
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from starlette.routing import BaseRoute, Host, Mount, WebSocketRoute

from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo


def _version(dist: str) -> str | None:
    try:
        return version(dist)
    except PackageNotFoundError:
        return None


def _qualified(obj: object) -> str:
    """``module.qualname`` of a callable (a class for instances); never ``repr``, which can carry closure values."""
    while isinstance(obj, functools.partial):
        obj = obj.func  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not hasattr(obj, "__qualname__"):
        obj = type(obj)
    return f"{getattr(obj, '__module__', None) or '?'}.{getattr(obj, '__qualname__', '?')}"


def _produces(route: object) -> str | None:
    response_class: Any = getattr(route, "response_class", None)
    response_class = getattr(response_class, "value", response_class)  # FastAPI wraps defaults in DefaultPlaceholder
    media_type = getattr(response_class, "media_type", None)
    return media_type if isinstance(media_type, str) else None


def _consumes(route: object) -> str | None:
    media_type = getattr(getattr(getattr(route, "body_field", None), "field_info", None), "media_type", None)
    return media_type if isinstance(media_type, str) else None


class FastApiIntrospector:
    def __init__(self, app: object, exclude_mount: str | None = None) -> None:
        self.app = app
        self.exclude_mount = exclude_mount  # sharpit's own mount path: its rows are not the host's

    def app_info(self) -> AppInfo:
        title = getattr(self.app, "title", None)
        docs_url = getattr(self.app, "docs_url", None)
        return AppInfo(
            title if isinstance(title, str) else None,
            "FastAPI",
            _version("fastapi"),
            docs_url if isinstance(docs_url, str) else None,
        )

    def routes(self) -> list[RouteInfo]:
        # Read attributes only: no endpoint is called and no OpenAPI schema is built. Walked per call, so routes
        # added after install show up.
        routes: Any = getattr(self.app, "routes", [])
        return list(self._walk(routes, "", None, top=True))

    def _walk(
        self, routes: list[BaseRoute], prefix: str, host: str | None, *, top: bool = False
    ) -> Iterator[RouteInfo]:
        for route in list(routes):
            if callable(getattr(route, "effective_candidates", None)):
                # FastAPI's lazy include_router entry: expand it to its effective (prefixed) routes.
                expanded: list[Any] = [*route.effective_candidates(), *route.effective_low_priority_routes()]  # type: ignore[attr-defined]
                yield from self._walk([getattr(c, "starlette_route", None) or c for c in expanded], prefix, host)
                continue
            if isinstance(route, Mount) and top and route.path == self.exclude_mount:
                continue
            if isinstance(route, Mount | Host):
                children: Any = getattr(route, "routes", None)
                if children:
                    inner_host = route.host if isinstance(route, Host) else host
                    yield from self._walk(
                        children, prefix + (route.path if isinstance(route, Mount) else ""), inner_host
                    )
                else:
                    app: Any = route.app
                    base = prefix + (route.path if isinstance(route, Mount) else "")
                    yield RouteInfo(
                        (),
                        base + "/{path}",
                        _qualified(app),
                        route.host if isinstance(route, Host) else host,
                        None,
                        None,
                        route.name,
                    )
                continue
            yield self._leaf(route, prefix, host)

    @staticmethod
    def _leaf(route: BaseRoute, prefix: str, host: str | None) -> RouteInfo:
        path = getattr(route, "path", None)
        full = prefix + path if isinstance(path, str) else prefix or "(any)"  # unknown route types: best effort
        endpoint = getattr(route, "endpoint", None)
        handler = _qualified(endpoint if endpoint is not None else route)
        name = getattr(route, "name", None)
        if isinstance(route, WebSocketRoute):
            methods: tuple[str, ...] = ("WS",)
        else:
            raw: Any = getattr(route, "methods", None) or ()
            # Starlette adds HEAD next to GET implicitly; drop it so one GET handler is one row.
            methods = tuple(sorted(m for m in raw if m != "HEAD" or "GET" not in raw))
        return RouteInfo(
            methods, full, handler, host, _produces(route), _consumes(route), name if isinstance(name, str) else None
        )

    def providers(self) -> list[ProviderInfo]:
        raise NotImplementedError("providers() lands in Task 10")
