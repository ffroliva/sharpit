"""FastAPI ``AppIntrospector`` (only ``app_info`` so far; routes and providers land in Tasks 9 and 10)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo


def _version(dist: str) -> str | None:
    try:
        return version(dist)
    except PackageNotFoundError:
        return None


class FastApiIntrospector:
    def __init__(self, app: object) -> None:
        self.app = app

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
        raise NotImplementedError("routes() lands in Task 9")

    def providers(self) -> list[ProviderInfo]:
        raise NotImplementedError("providers() lands in Task 10")
