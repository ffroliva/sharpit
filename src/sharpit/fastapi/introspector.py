"""FastAPI ``AppIntrospector``: routes for the mappings panel, dependency providers for the beans panel."""

from __future__ import annotations

import functools
import inspect
import re
import sys
import sysconfig
import types
import typing
from collections.abc import Iterator
from dataclasses import replace
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast

from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import Response
from starlette.routing import BaseRoute, Host, Mount, Route, WebSocketRoute, compile_path

from sharpit.engine.spi import (
    ApiModel,
    ApiRouteInfo,
    AppInfo,
    MiddlewareFacts,
    ProviderInfo,
    RouteInfo,
    SecuredRoute,
    SecurityChain,
    SecurityFacts,
    SecurityModel,
    SecurityScheme,
)
from sharpit.fastapi.capture import WrappingHandlers
from sharpit.fastapi.introspection_common import (
    MAX_DEPTH,
)
from sharpit.fastapi.introspection_common import (
    OWN_MODULE_PREFIX as _OWN_MODULE_PREFIX,
)
from sharpit.fastapi.introspection_common import (
    as_objects as _as_objects,
)
from sharpit.fastapi.introspection_common import (
    attrs as _attrs,
)
from sharpit.fastapi.introspection_common import (
    dotted as _dotted,
)
from sharpit.fastapi.introspection_errors import error_handler_infos, handler_name
from sharpit.fastapi.introspection_security import (
    FLAG_READERS as _FLAG_READERS,
)
from sharpit.fastapi.introspection_security import (
    middleware_facts as _middleware_facts,
)
from sharpit.fastapi.introspection_security import (
    scheme_objects as _scheme_objects,
)
from sharpit.fastapi.introspection_security import (
    scheme_urls as _scheme_urls,
)


class _FastAPIClasses(NamedTuple):
    apps: tuple[type, ...]
    routes: tuple[type, ...]
    websocket_routes: tuple[type, ...]


@functools.cache  # on first use: importing FastAPI here would load it in every pytest process (the plugin imports us)
def _fastapi_classes() -> _FastAPIClasses:
    """FastAPI's app, route and websocket route classes; the extra is optional, and an empty tuple matches no class."""
    try:
        from fastapi.applications import FastAPI  # noqa: PLC0415
        from fastapi.routing import APIRoute, APIWebSocketRoute  # noqa: PLC0415
    except ImportError:
        return _FastAPIClasses((), (), ())
    return _FastAPIClasses((FastAPI,), (APIRoute,), (APIWebSocketRoute,))


def _version(dist: str) -> str | None:
    try:
        return version(dist)
    except PackageNotFoundError:
        return None


_MOUNT_SUFFIX = "/{path}"
_UNEXPANDED_ROUTER = "<unexpanded include_router>"
_ANY_PATH = "(any)"


@functools.cache
def _known_routes() -> tuple[type, ...]:
    """The route classes the mappings classify, and subclasses: a route_class stays classified."""
    fastapi = _fastapi_classes()
    return (*fastapi.routes, *fastapi.websocket_routes, WebSocketRoute, Route)


def _qualified(obj: object) -> str:
    """``module:qualname`` of a callable (a class for instances); never ``repr``, which can carry closure values."""
    while isinstance(obj, functools.partial):
        obj = obj.func  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if inspect.getattr_static(obj, "__qualname__", None) is None:  # static: an instance's ``__getattr__`` never runs
        obj = type(obj)
    return f"{getattr(obj, '__module__', None) or '?'}:{getattr(obj, '__qualname__', '?')}"


def _exception_handler_name(handler: object) -> str:
    try:
        return handler_name(handler)[0]  # sharpit's capture wrapper is unwrapped to the host's own handler
    except ValueError:  # a ``__wrapped__`` loop
        return "UNRESOLVED"


def _source_target(obj: object) -> object:
    while isinstance(obj, functools.partial):
        obj = obj.func  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not (inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isclass(obj)):
        obj = type(obj)  # a callable instance is defined by its class
    return inspect.unwrap(obj) if callable(obj) else obj


def _first_line(target: object) -> int | None:
    """The definition's line from compiled metadata; the source file is never opened (spec §4.4)."""
    code = getattr(target, "__code__", None)  # a function, or a bound method's function
    if isinstance(code, types.CodeType):
        return code.co_firstlineno
    if not inspect.isclass(target):
        return None
    own = _attrs(target)
    line = own.get("__firstlineno__")  # Python 3.13+
    if isinstance(line, int):
        return line
    # 3.12: the class's first own function (its ``def`` line, not the ``class`` line)
    # type() checks only: isinstance() or getattr() would run a class-level proxy's own code
    funcs: list[object] = [
        cast(Any, v).__func__ if issubclass(type(v), staticmethod | classmethod) else v for v in own.values()
    ]
    lines = [f.__code__.co_firstlineno for f in funcs if type(f) is types.FunctionType]
    return min(lines, default=None)


def _resource(obj: object) -> str | None:
    """``file:line`` where the provider is defined (``file`` alone when no line is known), or ``None``."""
    try:
        target: Any = _source_target(obj)
        source = inspect.getsourcefile(target)  # maps the filename; stats it, never reads it
        if not source:
            return None
        line = _first_line(target)
        return f"{source}:{line}" if line is not None else source
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
    response_class: Any = _attrs(route).get("response_class")
    response_class = getattr(response_class, "value", response_class)  # FastAPI wraps defaults in DefaultPlaceholder
    media_type = getattr(response_class, "media_type", None)
    return media_type if isinstance(media_type, str) else None


def _consumes(route: object) -> str | None:
    media_type = getattr(getattr(_attrs(route).get("body_field"), "field_info", None), "media_type", None)
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
    values = _attrs(route)  # a user APIRoute subclass's properties are never run
    endpoint: Any = values.get("endpoint")
    annotation: object = _return_annotation(endpoint)
    dependant = values.get("dependant")
    returns_response = isinstance(annotation, type) and issubclass(annotation, Response)
    status_code = values.get("status_code")
    summary = values.get("summary")
    description = values.get("description")
    tags: Any = values.get("tags") or ()
    return ApiRouteInfo(
        methods=info.methods,
        path=info.path,
        handler=info.handler,
        status_code=status_code if isinstance(status_code, int) else None,
        response_model=values.get("response_model"),
        return_annotation=cast(object, annotation),
        dynamic_response=returns_response or bool(getattr(dependant, "response_param_name", None)),
        has_body=values.get("body_field") is not None,
        query_params=_query_params(dependant),
        summary=summary if isinstance(summary, str) else None,
        description=description if isinstance(description, str) else None,
        tags=tuple(str(t.value if isinstance(t, Enum) else t) for t in tags),
    )


def _framework(handler: str) -> bool:
    return handler.partition(":")[0].partition(".")[0] in ("fastapi", "starlette", "sharpit")


NOT_FASTAPI = "FastAPI security dependencies are not available: the app is not a FastAPI app"


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
        if cls is None or str(getattr(cls, "__module__", "")).startswith(_OWN_MODULE_PREFIX):  # sharpit's own: hidden
            continue
        names.append(_dotted(cls))
        if isinstance(cls, type) and issubclass(cls, AuthenticationMiddleware):
            backend = _backend(entry)
            if backend is not None:
                backends.append(_dotted(type(backend)))
    return tuple(names), tuple(backends)


def _wrapped_middleware(app: object) -> tuple[tuple[str, ...], object]:
    """(types in a mounted middleware wrapper chain, the innermost app); only instance dictionaries are read."""
    names: list[str] = []
    current = app
    seen: set[int] = set()
    while id(current) not in seen:
        seen.add(id(current))
        inner = _attrs(current).get("app")
        if inner is None:
            break
        names.append(_dotted(type(current)))
        current = inner
    return tuple(names), current


def _served_as_is(app: object) -> bool:
    """A framework app with no security of its own (``StaticFiles``); a wrapped or Starlette app is the user's."""
    inner = _wrapped_middleware(app)[1]
    return not issubclass(type(inner), Starlette) and _framework(_qualified(inner))


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
        unique = tuple(sorted(set(scopes)))  # FastAPI 0.115's security_scopes already hold the parents' scopes
        out.append(SecurityScheme(_dotted(type(call)), auto if isinstance(auto, bool) else True, unique))
        return True
    found = False
    if depth < MAX_DEPTH:
        for sub in getattr(node, "dependencies", None) or ():
            found = _schemes_in(sub, scopes, depth + 1, out, base) or found
    return found


def _optional_nested(node: object, depth: int, base: type) -> bool:
    call = getattr(node, "call", None)
    if issubclass(type(call), base) and inspect.getattr_static(call, "auto_error", True) is False:
        return True
    return depth < MAX_DEPTH and any(
        _optional_nested(sub, depth + 1, base) for sub in getattr(node, "dependencies", None) or ()
    )


def _mount_path(values: dict[str, Any], is_mount: bool) -> str:
    path = values.get("path", "") if is_mount else ""
    return path if isinstance(path, str) else ""


def _path_regex(path: str, prefix_only: bool) -> str | None:
    """Starlette's compiled pattern for ``path`` (framework convertor regexes; no route or convertor is called)."""
    try:
        if not prefix_only:
            return compile_path(path)[0].pattern
        pattern = compile_path(path.removesuffix(_MOUNT_SUFFIX) or "/")[0].pattern
        return pattern.removesuffix("$").removesuffix("/") + "(?:/.*)?$"
    except Exception:  # noqa: BLE001 - an unknown convertor: the route cannot be matched statically
        return None


def _route_list(app: object) -> list[BaseRoute]:
    """Routes from Starlette's stored objects, avoiding Mount.routes descriptor access."""
    values = _attrs(app)
    if issubclass(type(app), Starlette):
        router = values.get("router")
        if router is not None:
            values = _attrs(router)
    routes = values.get("routes")
    return cast(list[BaseRoute], routes) if isinstance(routes, list) else []


def _secured_route(
    info: RouteInfo,
    route: object,
    chain: int,
    base: type,
    limitations: list[str],
    inherited_dependencies: tuple[object, ...] = (),
) -> SecuredRoute:
    regex = _path_regex(info.path, False)
    try:
        schemes: list[SecurityScheme] = []
        unknown = False
        unchecked = False
        dependencies: list[object] = list(getattr(_attrs(route).get("dependant"), "dependencies", None) or ())
        for dependency in inherited_dependencies:
            call = getattr(dependency, "dependency", None)
            if call is not None:
                dependencies.append(_dependant_of(call))
        for sub in dependencies:
            # route/router/app ``dependencies=[...]`` have no parameter name: a guard whose meaning is unknown
            found = _schemes_in(sub, (), 0, schemes, base)
            if not found:
                if getattr(sub, "name", "") is None:
                    unknown = True
                else:
                    unchecked = True
            elif _optional_nested(sub, 0, base):
                unchecked = True
    except Exception as exc:  # noqa: BLE001 - FastAPI internals drifted: list the route as unknown; never crash
        limitations.append(f"Route {info.path} could not be inspected ({type(exc).__name__}).")
        return SecuredRoute(info.methods, info.path, info.handler, opaque=True, path_regex=regex, chain=chain)
    return SecuredRoute(
        info.methods, info.path, info.handler, tuple(dict.fromkeys(schemes)), unknown, False, regex, chain, unchecked
    )


class FastApiIntrospector:
    def __init__(self, app: object, exclude_mount: str | None = None, lifespan: object | None = None) -> None:
        self.app = app
        # The host's own lifespan: install() passes it before wrapping ``router.lifespan_context``.
        raw = lifespan if lifespan is not None else _attrs(_attrs(app).get("router")).get("lifespan_context")
        self.lifespan = _host_lifespan(raw) if raw is not None else None
        self.exclude_mount = (exclude_mount or "").rstrip(
            "/"
        ) or None  # sharpit's own mount path: its rows are not the host's

    def app_info(self) -> AppInfo:
        values = _attrs(self.app)  # a FastAPI subclass's properties are never run
        title = values.get("title")
        docs_url = values.get("docs_url")
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
                if info.handler == _UNEXPANDED_ROUTER:
                    limitations.append(f"Included router at {info.path} could not be expanded.")
                elif not self._opaque_rows.get(id(info), ((), None, False))[2]:  # StaticFiles serves no API
                    base = info.path.removesuffix(_MOUNT_SUFFIX) or "/"
                    limitations.append(f"Mounted application at {base} has no inspectable routes.")
            elif not issubclass(type(route), WebSocketRoute) and _attrs(route).get("endpoint") is not None:
                routes.append(_api_route(info, route))
        handlers: Any = _attrs(self.app).get("exception_handlers")
        handler_map = cast(dict[object, object], handlers)
        names = (
            tuple(_exception_handler_name(h) for h in handler_map.values())
            if type(handlers) is dict or type(handlers) is WrappingHandlers
            else ()
        )
        error_handlers, error_limitations = error_handler_infos(self.app, self.exclude_mount)
        return ApiModel(tuple(routes), names, (*limitations, *error_limitations), error_handlers)

    def _entries(self) -> Iterator[tuple[RouteInfo, object | None]]:
        routes = _route_list(self.app)
        self._mounts_by_route: dict[int, tuple[tuple[int, str | None], ...]] = {}
        self._included_dependencies_by_route: dict[int, tuple[object, ...]] = {}
        self._fastapi_routes: set[int] = set()  # routes whose enclosing app is FastAPI: dependencies classify
        # opaque mount rows by id(RouteInfo), as each row is made: (enclosing mounts, own mount, served as is)
        self._opaque_rows: dict[int, tuple[tuple[tuple[int, str | None], ...], int | None, bool]] = {}
        router: object | None = _attrs(self.app).get("router")
        app_dependencies = _as_objects(_attrs(router).get("dependencies", ())) if router is not None else ()
        return self._walk(
            routes,
            "",
            None,
            frozenset(),
            0,
            top=True,
            included_dependencies=app_dependencies,
            in_fastapi=issubclass(type(self.app), _fastapi_classes().apps),
        )

    def _walk(
        self,
        routes: list[BaseRoute],
        prefix: str,
        host: str | None,
        path_apps: frozenset[int],
        depth: int,
        *,
        top: bool = False,
        mounts: tuple[tuple[int, str | None], ...] = (),
        included_dependencies: tuple[object, ...] = (),
        in_fastapi: bool = False,
    ) -> Iterator[tuple[RouteInfo, object | None]]:
        """Each listed row with its leaf route object (``None`` for opaque mount / unexpanded rows)."""
        for route in cast(list[object], list(routes)):
            # Read the router's plain route list; never call effective-candidate methods.
            route_type: type[object] = type(route)
            if route_type.__module__ == "fastapi.routing" and route_type.__name__ == "_IncludedRouter":
                yield from self._walk_included(
                    route, prefix, host, path_apps, depth, mounts, (included_dependencies, in_fastapi)
                )
                continue
            # Only a top-level mount can be sharpit's own; a host's nested mount at the same path is its own.
            route_mro = type(route).__mro__
            is_mount = Mount in route_mro
            is_host = Host in route_mro
            if is_mount and top and _attrs(route).get("path") == self.exclude_mount:
                continue
            if is_mount or is_host:
                yield from self._walk_mounted(route, prefix, host, path_apps, depth, mounts, (is_mount, in_fastapi))
                continue
            if not issubclass(route_type, _known_routes()):  # issubclass(type()): a user ``__class__`` is never run
                # Unknown BaseRoute implementations are opaque; do not inspect even their descriptors.
                yield RouteInfo((), prefix or _ANY_PATH, "custom route", host, None, None, None), None
                continue
            self._mounts_by_route[id(route)] = mounts
            self._included_dependencies_by_route[id(route)] = included_dependencies
            if in_fastapi:
                self._fastapi_routes.add(id(route))
            yield self._leaf(cast(BaseRoute, route), prefix, host), route

    def _walk_included(
        self,
        route: object,
        prefix: str,
        host: str | None,
        path_apps: frozenset[int],
        depth: int,
        mounts: tuple[tuple[int, str | None], ...],
        inherited: tuple[tuple[object, ...], bool],
    ) -> Iterator[tuple[RouteInfo, object | None]]:
        included_dependencies, in_fastapi = inherited
        route_values = _attrs(route)
        context: object | None = route_values.get("include_context")
        context_values = _attrs(context) if context is not None else {}
        include_prefix = context_values.get("prefix")
        base = prefix + include_prefix if isinstance(include_prefix, str) and include_prefix else prefix
        original: object | None = route_values.get("original_router")
        router_values = _attrs(original) if original is not None else {}
        included_routes = router_values.get("routes")
        router_dependencies = router_values.get("dependencies", ())
        inherited_dependencies = (
            *included_dependencies,
            *_as_objects(router_dependencies),
            *_as_objects(context_values.get("dependencies", ())),
        )
        if isinstance(included_routes, list):
            yield from self._walk(
                cast(list[BaseRoute], included_routes),
                base,
                host,
                path_apps,
                depth + 1,
                mounts=mounts,
                included_dependencies=inherited_dependencies,
                in_fastapi=in_fastapi,
            )
        else:
            yield RouteInfo((), base or "/", _UNEXPANDED_ROUTER, host, None, None, None), None

    def _walk_mounted(
        self,
        route: object,
        prefix: str,
        host: str | None,
        path_apps: frozenset[int],
        depth: int,
        mounts: tuple[tuple[int, str | None], ...],
        kind: tuple[bool, bool],
    ) -> Iterator[tuple[RouteInfo, object | None]]:
        is_mount, in_fastapi = kind
        values = _attrs(route)
        base_app = values.get("_base_app") if is_mount else values.get("app")
        children = _route_list(base_app) if base_app is not None else []
        host_value = values.get("host", host) if not is_mount else host
        inner_host = host_value if isinstance(host_value, str) or host_value is None else host
        base = prefix + _mount_path(values, is_mount)
        child_app = values.get("app")
        if child_app is None:
            return
        app_id = id(child_app)
        pattern = values.get("path_regex")
        regex = cast(re.Pattern[str], pattern).pattern if is_mount and isinstance(pattern, re.Pattern) else None
        nested_mounts = (*mounts, (id(route), regex))
        # A plain Starlette sub-app is not FastAPI: its routes' dependencies say nothing about its security.
        app_type = type(base_app)
        child_fastapi = in_fastapi and (
            issubclass(app_type, _fastapi_classes().apps) or not issubclass(app_type, Starlette)
        )
        if children and app_id not in path_apps and depth < MAX_DEPTH:
            yield from self._walk(
                children,
                base,
                inner_host,
                path_apps | {app_id},
                depth + 1,
                mounts=nested_mounts,
                in_fastapi=child_fastapi,
            )
        else:
            route_name = values.get("name")
            info = RouteInfo(
                (),
                base + _MOUNT_SUFFIX,
                _qualified(child_app),
                inner_host,
                None,
                None,
                route_name if isinstance(route_name, str) else None,
            )
            self._opaque_rows[id(info)] = (mounts, id(route), _served_as_is(child_app))
            yield info, None

    @staticmethod
    def _leaf(route: BaseRoute, prefix: str, host: str | None) -> RouteInfo:
        values = _attrs(route)
        path = values.get("path")
        full = prefix + path if isinstance(path, str) else prefix or _ANY_PATH  # unknown route types: best effort
        endpoint = values.get("endpoint")
        handler = _qualified(endpoint if endpoint is not None else route)
        name = values.get("name")
        if issubclass(type(route), WebSocketRoute):
            methods: tuple[str, ...] = ("WS",)
        else:
            raw: Any = values.get("methods") or ()
            # Starlette adds HEAD next to GET implicitly; drop it so one GET handler is one row.
            methods = tuple(sorted(m for m in raw if m != "HEAD" or "GET" not in raw))
        return RouteInfo(
            methods, full, handler, host, _produces(route), _consumes(route), name if isinstance(name, str) else None
        )

    def security_model(self) -> SecurityModel:
        """Middleware stacks and each route's security schemes, read from objects FastAPI built; nothing is called."""
        try:
            from fastapi.security.base import SecurityBase  # noqa: PLC0415
        except ImportError:
            return SecurityModel(False, (), (), (), (NOT_FASTAPI,))
        if not issubclass(type(self.app), _fastapi_classes().apps):  # type(): a user ``__class__`` is never run
            return SecurityModel(False, (), (), (), (NOT_FASTAPI,))
        chains: list[SecurityChain] = []
        backends: list[str] = []
        self._chain_by_mount: dict[int, int] = {}
        self._chains(self.app, None, chains, backends, frozenset(), 0)
        routes: list[SecuredRoute] = []
        limitations: list[str] = []
        for info, route in self._entries():
            if route is None:  # an opaque mount row: its own mount picks the chain, its path_regex matches it
                mounts, own, served = self._opaque_rows.get(id(info), ((), None, False))
            else:
                mounts, served = self._mounts_by_route.get(id(route), ()), False
                own = mounts[-1][0] if mounts else None
            chain = self._chain_by_mount.get(own, 0) if own is not None else 0
            row = self._security_row(info, route, chain, SecurityBase, limitations, served)
            if row is not None:
                routes.append(replace(row, mounts=mounts))
        return SecurityModel(True, tuple(chains), tuple(backends), tuple(routes), tuple(limitations))

    def _security_row(
        self,
        info: RouteInfo,
        route: object | None,
        chain: int,
        security_base: type,
        limitations: list[str],
        served: bool,
    ) -> SecuredRoute | None:
        if route is None:
            if info.handler == _UNEXPANDED_ROUTER:
                limitations.append(f"Included router at {info.path} could not be expanded.")
                return None
            return self._opaque_route(info, chain, limitations, served)
        if _framework(info.handler):
            return None
        if issubclass(type(route), _fastapi_classes().routes) and id(route) in self._fastapi_routes:
            return _secured_route(
                info,
                route,
                chain,
                security_base,
                limitations,
                self._included_dependencies_by_route.get(id(route), ()),
            )
        if issubclass(type(route), Route):  # a Starlette route, or an APIRoute outside FastAPI: unknown
            return SecuredRoute(
                (), info.path, info.handler, opaque=True, path_regex=_path_regex(info.path, False), chain=chain
            )
        return SecuredRoute((), info.path, info.handler, opaque=True, path_regex=None, chain=chain)

    def _chains(
        self,
        app: object,
        prefix: str | None,
        chains: list[SecurityChain],
        backends: list[str],
        seen: frozenset[int],
        depth: int,
        inherited: tuple[str, ...] = (),
        mount_id: int | None = None,
        parent_chain: int = 0,
    ) -> None:
        middleware, found = _middleware(app)
        stack = (*inherited, *middleware)
        own_chain = parent_chain  # a mount that adds no middleware stays on its parent's chain, never a sibling's
        if prefix is None or stack:
            chains.append(SecurityChain(prefix, stack))
            backends.extend(found)
            own_chain = len(chains) - 1
        if mount_id is not None:
            self._chain_by_mount[mount_id] = own_chain
        for route, is_mount, child, child_path in self._children(app, prefix is None):
            if id(child) not in seen and depth < MAX_DEPTH:
                # the wrapper's types join the stack; the walk goes on in the sub-app it wraps (nested mounts)
                wrappers, inner = _wrapped_middleware(child)
                mount_names = wrappers if is_mount else ()
                self._chains(
                    inner,
                    (prefix or "") + child_path,
                    chains,
                    backends,
                    seen | {id(child)},
                    depth + 1,
                    (*stack, *mount_names),
                    id(route),
                    own_chain,
                )

    def _children(self, app: object, top: bool) -> Iterator[tuple[object, bool, object, str]]:
        """(route, is_mount, child app, mount path) of each mount and host of ``app``, sharpit's own left out."""
        routes: list[object] = list(_route_list(app)) if issubclass(type(app), Starlette) else []
        for route in routes:
            route_mro = type(route).__mro__
            is_mount = Mount in route_mro
            is_host = Host in route_mro
            if not (is_mount or is_host):
                continue
            values = _attrs(route)
            if top and is_mount and values.get("path") == self.exclude_mount:
                continue
            child = values.get("app")
            if child is not None:
                yield route, is_mount, child, _mount_path(values, is_mount)

    @staticmethod
    def _opaque_route(info: RouteInfo, chain: int, limitations: list[str], served: bool) -> SecuredRoute:
        if info.path == _ANY_PATH:
            return SecuredRoute((), info.path, info.handler, opaque=True, chain=chain)
        if served:  # StaticFiles and other framework apps: served as is, no security of their own
            return SecuredRoute((), info.path, info.handler, path_regex=_path_regex(info.path, True), chain=chain)
        base = info.path.removesuffix(_MOUNT_SUFFIX) or "/"
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
                visit(_attrs(route).get("dependant") if route is not None else None, None, 0)
                for dependency in self._included_dependencies_by_route.get(id(route), ()):
                    call = getattr(dependency, "dependency", None)
                    if call is not None:
                        key, new = add(call, "request")
                        if new:
                            visit(_dependant_of(call), key, 1)
            except Exception:  # noqa: BLE001,S112 - one odd route must not empty the panel
                continue

        overridden_by: dict[int, int] = {}
        overrides: Any = _attrs(self.app).get("dependency_overrides") or {}
        for original, override in list(overrides.items()):
            try:
                add(original, "request")
                key, new = add(override, "request")
                overridden_by[id(original)] = key
                if new:
                    visit(_dependant_of(override), key, 1)
            except Exception:  # noqa: BLE001,S112
                continue

        middleware: Any = _attrs(self.app).get("user_middleware") or ()
        for entry in list(middleware):
            cls = getattr(entry, "cls", None)  # only the class: args/kwargs (secret keys) are never read
            if cls is not None and not getattr(cls, "__module__", "").startswith(
                _OWN_MODULE_PREFIX
            ):  # not sharpit's own
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

    def security_facts(self) -> SecurityFacts:
        """The security advisor's option facts (``vars()``-style reads only; no option value leaves as a value)."""
        try:
            from fastapi.security.base import SecurityBase  # noqa: PLC0415
        except ImportError:
            return SecurityFacts(False, None, (), (), (NOT_FASTAPI,))
        if not issubclass(type(self.app), _fastapi_classes().apps):  # type(): a user ``__class__`` is never run
            return SecurityFacts(False, None, (), (), (NOT_FASTAPI,))
        values = _attrs(self.app)
        openapi_url = values.get("openapi_url")
        limitations: list[str] = []
        middleware = (*_middleware_facts(self.app, limitations), *self._mounted_middleware(limitations))
        schemes: dict[int, object] = {}
        for _info, route in self._entries():
            if route is not None and issubclass(type(route), _fastapi_classes().routes):
                _scheme_objects(_attrs(route).get("dependant"), 0, SecurityBase, schemes)
        urls = tuple(url for scheme in schemes.values() for url in _scheme_urls(scheme))
        debug = values.get("debug") is True
        return SecurityFacts(
            debug, openapi_url if isinstance(openapi_url, str) else None, middleware, urls, tuple(limitations)
        )

    def _mounted_middleware(self, limitations: list[str]) -> list[MiddlewareFacts]:
        """Each mounted Starlette app's own ``user_middleware`` facts, read like the root's; a middleware instance
        wrapping a mount keeps its options in derived attributes, so its options are a limitation, never a guess."""
        found: list[MiddlewareFacts] = []
        pending: list[tuple[object, str, int]] = [(self.app, "", 0)]
        seen: set[int] = {id(self.app)}
        while pending:
            app, prefix, depth = pending.pop(0)
            for _route, _is_mount, child, path in self._children(app, depth == 0):
                if id(child) in seen or depth >= MAX_DEPTH:
                    continue
                seen.add(id(child))
                here = prefix + path
                label = here or "/"
                wrappers, inner = _wrapped_middleware(child)
                limitations.extend(
                    f"{simple} options on the app mounted at {label} were not read."
                    for simple in (w.rpartition(".")[2] for w in wrappers)
                    if simple in _FLAG_READERS
                )
                if issubclass(type(inner), Starlette):
                    found.extend(_middleware_facts(inner, limitations, label))
                    pending.append((inner, here, depth + 1))
        return found
