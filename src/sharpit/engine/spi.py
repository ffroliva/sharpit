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
