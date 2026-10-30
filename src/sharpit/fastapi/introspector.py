"""FastAPI ``AppIntrospector``: routes for the mappings panel, dependency providers for the beans panel."""

from __future__ import annotations

import functools
import inspect
import sys
import sysconfig
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from starlette.routing import BaseRoute, Host, Mount, WebSocketRoute

from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo


def _version(dist: str) -> str | None:
    try:
        return version(dist)
    except PackageNotFoundError:
        return None


MAX_DEPTH = 32


def _qualified(obj: object) -> str:
    """``module:qualname`` of a callable (a class for instances); never ``repr``, which can carry closure values."""
    while isinstance(obj, functools.partial):
        obj = obj.func  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not hasattr(obj, "__qualname__"):
        obj = type(obj)
    return f"{getattr(obj, '__module__', None) or '?'}:{getattr(obj, '__qualname__', '?')}"


def _source_target(obj: object) -> object:
    while isinstance(obj, functools.partial):
        obj = obj.func  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not (inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isclass(obj)):
        obj = type(obj)  # a callable instance is defined by its class
    return inspect.unwrap(obj) if callable(obj) else obj


def _resource(obj: object) -> str | None:
    """``file:line`` where the provider is defined, or ``None`` (built-ins, ``exec``'d code)."""
    try:
        target: Any = _source_target(obj)
        source = inspect.getsourcefile(target)
        return f"{source}:{inspect.getsourcelines(target)[1]}" if source else None
    except Exception:  # noqa: BLE001 - no source (built-in, C extension, exec'd): the bean stays, without a resource
        return None


def _classify(name: str) -> Literal["APPLICATION", "FRAMEWORK", "PLATFORM", "BOOTUI", "OTHER"]:
    module = name.partition(":")[0]
    top = module.partition(".")[0]
    if not module or module == "?":
        return "OTHER"
    if top == "sharpit":
        return "BOOTUI"
    file = getattr(sys.modules.get(module), "__file__", None)
    if isinstance(file, str):
        path = Path(file)
        if {"site-packages", "dist-packages"} & set(path.parts):  # first: site-packages can sit inside the stdlib dir
            return "FRAMEWORK"
        # By location, not name: an app package called ``email`` outside the stdlib directory is the app's.
        return "PLATFORM" if path.is_relative_to(_STDLIB) else "APPLICATION"
    return "PLATFORM" if top in sys.stdlib_module_names or top == "builtins" else "APPLICATION"  # no file: built-ins


_STDLIB = Path(sysconfig.get_paths()["stdlib"])
_MERGED_LIFESPAN = "_merge_lifespan_context.<locals>.merged_lifespan"


def _host_lifespan(lifespan: object) -> object:
    """Unwrap FastAPI's per-``include_router`` merged lifespan back to the host's own (closure read, never called).

    shortcut: relies on FastAPI-private ``merged_lifespan``/``original_context``; any drift returns the input unchanged.
    """
    try:
        current = lifespan
        for _ in range(MAX_DEPTH):
            inner: Any = getattr(current, "__wrapped__", None)
            if inner is None or not str(getattr(current, "__qualname__", "")).endswith(_MERGED_LIFESPAN):
                return current
            cells = dict(zip(inner.__code__.co_freevars, inner.__closure__ or (), strict=False))
            if "original_context" not in cells:
                return current
            current = cells["original_context"].cell_contents
        return current
    except Exception:  # noqa: BLE001 - private layout drifted: show what the router holds
        return lifespan


def _dependant_of(call: object) -> object | None:
    """The sub-dependency tree FastAPI would build for an override (signature only; nothing is called)."""
    from fastapi.dependencies.utils import get_dependant  # noqa: PLC0415 - FastAPI is optional for sharpit

    return get_dependant(path="", call=call)  # pyright: ignore[reportArgumentType]


def _produces(route: object) -> str | None:
    response_class: Any = getattr(route, "response_class", None)
    response_class = getattr(response_class, "value", response_class)  # FastAPI wraps defaults in DefaultPlaceholder
    media_type = getattr(response_class, "media_type", None)
    return media_type if isinstance(media_type, str) else None


def _consumes(route: object) -> str | None:
    media_type = getattr(getattr(getattr(route, "body_field", None), "field_info", None), "media_type", None)
    return media_type if isinstance(media_type, str) else None


class FastApiIntrospector:
    def __init__(self, app: object, exclude_mount: str | None = None, lifespan: object | None = None) -> None:
        self.app = app
        # The host's own lifespan: install() passes it before wrapping ``router.lifespan_context``.
        raw = lifespan if lifespan is not None else getattr(getattr(app, "router", None), "lifespan_context", None)
        self.lifespan = _host_lifespan(raw) if raw is not None else None
        self.exclude_mount = (exclude_mount or "").rstrip(
            "/"
        ) or None  # sharpit's own mount path: its rows are not the host's

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
        return [info for info, _ in self._entries()]

    def _entries(self) -> Iterator[tuple[RouteInfo, object | None]]:
        routes: Any = getattr(self.app, "routes", [])
        return self._walk(routes, "", None, frozenset(), 0, top=True)

    def _walk(
        self,
        routes: list[BaseRoute],
        prefix: str,
        host: str | None,
        path_apps: frozenset[int],
        depth: int,
        *,
        top: bool = False,
    ) -> Iterator[tuple[RouteInfo, object | None]]:
        """Each listed row with its leaf route object (``None`` for opaque mount / unexpanded rows)."""
        for route in list(routes):
            if callable(getattr(route, "effective_candidates", None)):
                # FastAPI's lazy include_router entry (private API): expand it to its effective (prefixed) routes.
                try:
                    expanded: list[Any] = [*route.effective_candidates(), *route.effective_low_priority_routes()]  # type: ignore[attr-defined]
                    flat = [getattr(c, "starlette_route", None) or c for c in expanded]
                except Exception:  # noqa: BLE001 - FastAPI internals drifted: keep the listing, show a visible row
                    include_prefix = getattr(getattr(route, "include_context", None), "prefix", None)
                    base = prefix + include_prefix if isinstance(include_prefix, str) and include_prefix else None
                    path = base + "/{path}" if base else "(include_router)"
                    yield RouteInfo((), path, "<unexpanded include_router>", host, None, None, None), None
                    continue
                yield from self._walk(flat, prefix, host, path_apps, depth)
                continue
            # Only a top-level mount can be sharpit's own; a host's nested mount at the same path is its own.
            if isinstance(route, Mount) and top and route.path == self.exclude_mount:
                continue
            if isinstance(route, Mount | Host):
                children: Any = getattr(route, "routes", None)
                inner_host = route.host if isinstance(route, Host) else host
                base = prefix + (route.path if isinstance(route, Mount) else "")
                app_id = id(route.app)
                if children and app_id not in path_apps and depth < MAX_DEPTH:
                    yield from self._walk(children, base, inner_host, path_apps | {app_id}, depth + 1)
                else:  # no routes to list, a cycle, or past the depth cap: one opaque row, stop descending
                    yield (
                        RouteInfo((), base + "/{path}", _qualified(route.app), inner_host, None, None, route.name),
                        None,
                    )
                continue
            yield self._leaf(route, prefix, host), route

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
        # Read attributes only: no dependency is called, the middleware stack is never built, no OpenAPI schema.
        # Beans are dependency providers; route endpoints are mappings, not beans.
        found: dict[int, tuple[object, Literal["request", "singleton"]]] = {}  # identity -> object, discovery order
        edges: dict[int, dict[int, None]] = {}  # identity -> ordered direct sub-provider identities

        def add(obj: object, scope: Literal["request", "singleton"]) -> tuple[int, bool]:
            key = id(obj)
            new = key not in found
            if new:
                found[key] = (obj, scope)
                edges[key] = {}
            return key, new

        def visit(dependant: object, owner: int | None, depth: int) -> None:
            subs: Any = getattr(dependant, "dependencies", None) or ()
            for sub in list(subs):
                call = getattr(sub, "call", None)
                if call is None:
                    continue
                key, new = add(call, "request")  # registered before the edge, so an edge never dangles
                if owner is not None:
                    edges[owner][key] = None
                if new and depth < MAX_DEPTH:
                    visit(sub, key, depth + 1)

        for _, route in self._entries():
            try:
                visit(getattr(route, "dependant", None), None, 0)
            except Exception:  # noqa: BLE001,S112 - one odd route must not empty the panel
                continue

        overridden_by: dict[int, int] = {}
        overrides: Any = getattr(self.app, "dependency_overrides", None) or {}
        for original, override in list(overrides.items()):
            try:
                add(original, "request")
                key, new = add(override, "request")
                overridden_by[id(original)] = key
                if new:
                    visit(_dependant_of(override), key, 1)
            except Exception:  # noqa: BLE001,S112
                continue

        middleware: Any = getattr(self.app, "user_middleware", None) or ()
        for entry in list(middleware):
            cls = getattr(entry, "cls", None)  # only the class: args/kwargs (secret keys) are never read
            if cls is not None:
                add(cls, "singleton")
        if self.lifespan is not None:
            add(self.lifespan, "singleton")

        names: dict[int, str] = {}
        seen: dict[str, int] = {}
        for key, (obj, _) in found.items():
            base = _qualified(obj)
            seen[base] = seen.get(base, 0) + 1
            names[key] = base if seen[base] == 1 else f"{base}#{seen[base]}"
        return [
            ProviderInfo(
                names[key],
                _qualified(obj),
                scope,
                _resource(obj),
                tuple(names[d] for d in edges[key]),
                _classify(names[key]),
                names[overridden_by[key]] if key in overridden_by else None,
            )
            for key, (obj, scope) in found.items()
        ]
