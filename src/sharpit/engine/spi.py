"""Service-provider interface between the engine and a framework adapter (no framework imports here)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class AppInfo:
    title: str | None
    framework: str
    framework_version: str | None
    docs_url: str | None


@dataclass(frozen=True)
class RouteInfo:
    methods: tuple[str, ...]
    path: str
    handler: str
    host: str | None
    produces: str | None
    consumes: str | None
    name: str | None


@dataclass(frozen=True)
class ApiRouteInfo:
    """One route handler as the REST API advisor reads it (declared metadata only; nothing is called)."""

    methods: tuple[str, ...]
    path: str
    handler: str  # ``module:qualname`` of the endpoint
    status_code: int | None = None  # the declared success status; None is the framework default (200)
    response_model: object | None = None  # the type the framework serialises through, None when there is none
    return_annotation: object | None = None  # None: no annotation; ``type(None)``: ``-> None``
    dynamic_response: bool = False  # returns a Response or takes one as a parameter: status/body set at runtime
    has_body: bool = False
    query_params: tuple[str, ...] = ()
    summary: str | None = None
    description: str | None = None  # an explicit description or the endpoint's docstring
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApiModel:
    routes: tuple[ApiRouteInfo, ...]
    exception_handlers: tuple[str, ...]  # ``module:qualname`` of each registered exception handler
    limitations: tuple[str, ...]  # what could not be inspected (an opaque mounted app)


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    type_name: str
    scope: Literal["request", "singleton"]
    resource: str | None
    dependencies: tuple[str, ...]
    classification: Literal["APPLICATION", "FRAMEWORK", "PLATFORM", "BOOTUI", "OTHER"]
    overridden_by: str | None


class AppIntrospector(Protocol):
    def app_info(self) -> AppInfo: ...

    def routes(self) -> list[RouteInfo]: ...

    def providers(self) -> list[ProviderInfo]: ...


@dataclass(frozen=True)
class SecurityScheme:
    """A ``fastapi.security`` scheme found in a route's dependency tree (read, never called)."""

    type_name: str  # ``module.qualname`` of the scheme class
    auto_error: bool  # False: the scheme lets anonymous requests through (optional auth)
    scopes: tuple[str, ...]  # scopes from ``Security(..., scopes=[...])`` on the path to the scheme, sorted


@dataclass(frozen=True)
class SecurityChain:
    """One ASGI middleware stack: the app's own (``prefix`` None) or a mounted sub-app's."""

    prefix: str | None
    middleware: tuple[str, ...]  # ``module.qualname`` of each middleware, outermost first


@dataclass(frozen=True)
class SecuredRoute:
    methods: tuple[str, ...]  # () = any method (an opaque mount)
    path: str
    handler: str
    schemes: tuple[SecurityScheme, ...] = ()
    unknown_dependency: bool = False  # a route-level dependency with no scheme in its tree (a custom guard)
    opaque: bool = False  # the route's security could not be read
    path_regex: str | None = None  # the adapter's compiled path pattern; None: cannot be matched statically
    chain: int = 0  # index into ``SecurityModel.chains``
    # a parameter dependency without a scheme, or an optional scheme inside a user dependency: its effect is unknown
    unchecked_dependency: bool = False
    # every enclosing mount, outermost first, as (identity, prefix pattern); pattern None: matched by host, unknown
    mounts: tuple[tuple[int, str | None], ...] = ()


@dataclass(frozen=True)
class SecurityModel:
    present: bool  # the app has FastAPI dependency trees to read
    chains: tuple[SecurityChain, ...]
    auth_backends: tuple[str, ...]  # ``module.qualname`` of each ``AuthenticationMiddleware`` backend
    routes: tuple[SecuredRoute, ...]  # route-table order (the order Starlette matches in)
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class MiddlewareFacts:
    """One middleware on the app's own stack: its security-relevant options as fact names, never their values."""

    name: str  # ``module.qualname`` of the middleware class
    flags: tuple[str, ...]  # sorted, e.g. ``any_origin``, ``credentials``, ``https_only``, ``short_secret``
    mount: str | None = None  # the mount path of the sub-app whose own stack holds it; None: the root app


@dataclass(frozen=True)
class SchemeUrl:
    """A URL a security scheme declares (OpenID Connect discovery, OAuth2 flow endpoints), as a fact only."""

    scheme: str  # ``module.qualname`` of the scheme class
    field: str  # ``openIdConnectUrl``, ``authorizationUrl``, ``tokenUrl`` or ``refreshUrl``
    insecure: bool  # ``http://`` to a host that is not loopback


@dataclass(frozen=True)
class SecurityFacts:
    """The security advisor's reads beyond ``SecurityModel`` (read statically on a scan; nothing is called)."""

    debug: bool  # ``FastAPI(debug=True)``: tracebacks reach the client
    openapi_url: str | None
    middleware: tuple[MiddlewareFacts, ...]  # the app's own ``user_middleware``, outermost first, then mounted apps'
    scheme_urls: tuple[SchemeUrl, ...]
    limitations: tuple[str, ...] = ()
