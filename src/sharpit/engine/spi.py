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
