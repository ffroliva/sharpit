"""``GET {api}/data/repositories[/{name}]``: the SQLAlchemy mapped classes handed to ``install(models=...)``."""

from __future__ import annotations

from typing import Any

from sharpit.engine.context import SharpitContext

NO_MODELS = "pass models= to sharpit.install"
UNCONFIGURED = "Mappers are not configured yet: the app has not run a query"
NO_REGISTRY = "models= holds no declarative base or registry"


def registries(models: tuple[object, ...]) -> tuple[list[object], list[str]]:
    del models
    return [], []


def repositories_report(ctx: SharpitContext) -> dict[str, Any]:
    del ctx
    return {"springDataPresent": False, "total": 0, "repositories": [], "unavailableReason": None, "warnings": []}


def repository_detail(ctx: SharpitContext, name: str) -> dict[str, Any] | None:
    del ctx, name
    return None
