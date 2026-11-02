"""FastAPI ``AppIntrospector``: routes for the mappings panel, dependency providers for the beans panel."""

from __future__ import annotations

import functools
import inspect
import sys
import sysconfig
import typing
from collections.abc import Iterator
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal, cast

from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import Response
from starlette.routing import BaseRoute, Host, Mount, WebSocketRoute, compile_path

from sharpit.engine.spi import (
    ApiModel,
    ApiRouteInfo,
    AppInfo,
    ProviderInfo,
    RouteInfo,
    SecuredRoute,
    SecurityChain,
    SecurityModel,
    SecurityScheme,
)


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


def _return_annotation(endpoint: object) -> object | None:
    """The resolved return annotation: None when there is none, ``type(None)`` for ``-> None``."""
    try:
        return typing.get_type_hints(endpoint, include_extras=True).get("return")
    except Exception:  # noqa: BLE001 - an unresolvable forward reference: fall back to the raw annotation
        try:
            raw = inspect.signature(endpoint).return_annotation  # pyright: ignore[reportArgumentType]
        except (TypeError, ValueError):
            return None
        return None if raw is inspect.Signature.empty else type(None) if raw is None else raw


def _query_params(dependant: object, depth: int = 0) -> tuple[str, ...]:
    """Query parameter names of the route and its sub-dependencies (signature metadata only; nothing is called)."""
    params: Any = getattr(dependant, "query_params", None) or ()
    names = [str(getattr(p, "alias", None) or getattr(p, "name", "")) for p in params]
    if depth < MAX_DEPTH:
        for sub in getattr(dependant, "dependencies", None) or ():
            names.extend(_query_params(sub, depth + 1))
    return tuple(names)


def _api_route(info: RouteInfo, route: object) -> ApiRouteInfo:
    endpoint: Any = getattr(route, "endpoint", None)
    annotation: object = _return_annotation(endpoint)
    dependant = getattr(route, "dependant", None)
    returns_response = isinstance(annotation, type) and issubclass(annotation, Response)
    status_code = getattr(route, "status_code", None)
    summary = getattr(route, "summary", None)
    description = getattr(route, "description", None)
    tags: Any = getattr(route, "tags", None) or ()
    return ApiRouteInfo(
        methods=info.methods,
        path=info.path,
        handler=info.handler,
        status_code=status_code if isinstance(status_code, int) else None,
        response_model=getattr(route, "response_model", None),
        return_annotation=cast(object, annotation),
        dynamic_response=returns_response or bool(getattr(dependant, "response_param_name", None)),
        has_body=getattr(route, "body_field", None) is not None,
        query_params=_query_params(dependant),
        summary=summary if isinstance(summary, str) else None,
        description=description if isinstance(description, str) else None,
        tags=tuple(str(t.value if isinstance(t, Enum) else t) for t in tags),
    )


def _framework(handler: str) -> bool:
    return handler.partition(":")[0].partition(".")[0] in ("fastapi", "starlette", "sharpit")


NOT_FASTAPI = "FastAPI security dependencies are not available: the app is not a FastAPI app"


def _dotted(cls: object) -> str:
    return f"{getattr(cls, '__module__', None) or '?'}.{getattr(cls, '__qualname__', '?')}"


def _backend(entry: object) -> object | None:
    """``AuthenticationMiddleware``'s backend: the only option read, and only its type leaves."""
    kwargs: Any = getattr(entry, "kwargs", None)
    if isinstance(kwargs, dict) and "backend" in kwargs:
        return cast(object, kwargs["backend"])
    args: Any = getattr(entry, "args", None)
    return cast(object, args[0]) if isinstance(args, tuple | list) and args else None


def _middleware(app: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(middleware, auth backends) as dotted class names, outermost first; option values are never read."""
    entries: Any = inspect.getattr_static(app, "user_middleware", None)
    names: list[str] = []
    backends: list[str] = []
    listed: list[object] = list(cast(list[object], entries)) if isinstance(entries, list | tuple) else []
    for entry in listed:
        cls: Any = getattr(entry, "cls", None)
        if cls is None or str(getattr(cls, "__module__", "")).startswith("sharpit."):  # sharpit's own: hidden
            continue
        names.append(_dotted(cls))
        if isinstance(cls, type) and issubclass(cls, AuthenticationMiddleware):
            backend = _backend(entry)
            if backend is not None:
                backends.append(_dotted(type(backend)))
    return tuple(names), tuple(backends)


def _scopes(node: object) -> tuple[str, ...]:
    # FastAPI >= 0.120 keeps a node's own scopes in ``own_oauth_scopes``; 0.115 in ``security_scopes``.
    raw: Any = getattr(node, "own_oauth_scopes", None) or getattr(node, "security_scopes", None) or ()
    return tuple(str(s) for s in raw)


def _schemes_in(node: object, scopes: tuple[str, ...], depth: int, out: list[SecurityScheme], base: type) -> bool:
    """Append every scheme in ``node``'s tree to ``out``; True when one was found. Nothing is called."""
    scopes = (*scopes, *_scopes(node))
    call: object = getattr(node, "call", None)
    if issubclass(type(call), base):  # type(), not isinstance(): a user ``__class__`` property is never run
        auto: object = inspect.getattr_static(call, "auto_error", True)  # a user property is not run either
        out.append(SecurityScheme(_dotted(type(call)), auto if isinstance(auto, bool) else True, tuple(sorted(scopes))))
        return True
    found = False
    if depth < MAX_DEPTH:
        for sub in list(getattr(node, "dependencies", None) or ()):
            found = _schemes_in(sub, scopes, depth + 1, out, base) or found
    return found


def _path_regex(path: str, prefix_only: bool) -> str | None:
    """Starlette's compiled pattern for ``path`` (framework convertor regexes; no route or convertor is called)."""
    try:
        if not prefix_only:
            return compile_path(path)[0].pattern
        pattern = compile_path(path.removesuffix("/{path}") or "/")[0].pattern
        return pattern.removesuffix("$").removesuffix("/") + "(?:/.*)?$"
    except Exception:  # noqa: BLE001 - an unknown convertor: the route cannot be matched statically
        return None


def _secured_route(info: RouteInfo, route: object, chain: int, base: type, limitations: list[str]) -> SecuredRoute:
    regex = _path_regex(info.path, False)
    try:
        schemes: list[SecurityScheme] = []
        unknown = False
        for sub in list(getattr(getattr(route, "dependant", None), "dependencies", None) or ()):
            # route/router/app ``dependencies=[...]`` have no parameter name: a guard whose meaning is unknown
            if not _schemes_in(sub, (), 0, schemes, base) and getattr(sub, "name", "") is None:
                unknown = True
    except Exception as exc:  # noqa: BLE001 - FastAPI internals drifted: list the route as unknown, never crash
        limitations.append(f"Route {info.path} could not be inspected ({type(exc).__name__}).")
        return SecuredRoute(info.methods, info.path, info.handler, opaque=True, path_regex=regex, chain=chain)
    return SecuredRoute(
        info.methods, info.path, info.handler, tuple(dict.fromkeys(schemes)), unknown, False, regex, chain
    )


def _chain_of(path: str, chains: list[SecurityChain]) -> int:
    best, length = 0, -1
    for index, chain in enumerate(chains):
        prefix = chain.prefix
        if prefix is not None and len(prefix) > length and (path == prefix or path.startswith(prefix + "/")):
            best, length = index, len(prefix)
    return best


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

    def api_model(self) -> ApiModel:
        """Route metadata for the REST API advisor: ``APIRoute`` attributes only, never ``app.openapi()``."""
        routes: list[ApiRouteInfo] = []
        limitations: list[str] = []
        for info, route in self._entries():
            if route is None:
                if info.handler == "<unexpanded include_router>":
                    limitations.append(f"Included router at {info.path} could not be expanded.")
                elif not _framework(info.handler):  # StaticFiles and other framework apps serve no API
                    base = info.path.removesuffix("/{path}") or "/"
                    limitations.append(f"Mounted application at {base} has no inspectable routes.")
            elif not isinstance(route, WebSocketRoute) and getattr(route, "endpoint", None) is not None:
                routes.append(_api_route(info, route))
        handlers: Any = getattr(self.app, "exception_handlers", None) or {}
        # sharpit's exception capture wraps each handler: report the host's own function
        names = tuple(_qualified(getattr(h, "__sharpit_original__", h)) for h in list(handlers.values()))
        return ApiModel(tuple(routes), names, tuple(limitations))

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

    def security_model(self) -> SecurityModel:
        """Middleware stacks and each route's security schemes, read from objects FastAPI built; nothing is called."""
        try:
            from fastapi.security.base import SecurityBase  # noqa: PLC0415

            from fastapi import FastAPI  # noqa: PLC0415 - FastAPI is optional for sharpit
        except ImportError:
            return SecurityModel(False, (), (), (), (NOT_FASTAPI,))
        if not isinstance(self.app, FastAPI):
            return SecurityModel(False, (), (), (), (NOT_FASTAPI,))
        chains: list[SecurityChain] = []
        backends: list[str] = []
        self._chains(self.app, None, chains, backends, frozenset(), 0)
        routes: list[SecuredRoute] = []
        limitations: list[str] = []
        for info, route in self._entries():
            chain = _chain_of(info.path, chains)
            if route is None:
                routes.append(self._opaque_route(info, chain, limitations))
            elif not _framework(info.handler):  # FastAPI's docs routes are not the app's endpoints
                routes.append(_secured_route(info, route, chain, SecurityBase, limitations))
        return SecurityModel(True, tuple(chains), tuple(backends), tuple(routes), tuple(limitations))

    def _chains(
        self,
        app: object,
        prefix: str | None,
        chains: list[SecurityChain],
        backends: list[str],
        seen: frozenset[int],
        depth: int,
    ) -> None:
        middleware, found = _middleware(app)
        if prefix is None or middleware:  # the app's own stack always; a mount only when it adds middleware
            chains.append(SecurityChain(prefix, middleware))
            backends.extend(found)
        routes: list[object] = list(app.routes) if isinstance(app, Starlette) else []  # user ASGI apps: opaque
        for route in routes:
            if not isinstance(route, Mount) or (prefix is None and route.path == self.exclude_mount):
                continue
            if id(route.app) not in seen and depth < MAX_DEPTH:
                self._chains(
                    route.app, (prefix or "") + route.path, chains, backends, seen | {id(route.app)}, depth + 1
                )

    @staticmethod
    def _opaque_route(info: RouteInfo, chain: int, limitations: list[str]) -> SecuredRoute:
        if _framework(info.handler):  # StaticFiles and other framework apps: served as is, no security of their own
            return SecuredRoute((), info.path, info.handler, path_regex=_path_regex(info.path, True), chain=chain)
        base = info.path.removesuffix("/{path}") or "/"
        limitations.append(f"Mounted application at {base} has no inspectable routes.")
        return SecuredRoute(
            (), info.path, info.handler, opaque=True, path_regex=_path_regex(info.path, True), chain=chain
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
            if cls is not None and not getattr(cls, "__module__", "").startswith("sharpit."):  # not sharpit's own
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
