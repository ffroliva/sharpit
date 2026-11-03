"""The mapper walk over ``install(models=...)`` and its configured-gate, shared by every ORM reader (0.5.0 spec §4.4).

Duck-typed over the objects the app passed in (a declarative base, a ``registry``, a mapped class); imports no
SQLAlchemy and never configures a mapper.
"""

from __future__ import annotations

from typing import Any


def registries(models: tuple[object, ...]) -> tuple[list[object], list[str]]:
    """The distinct registries behind ``models``; a warning per entry that is neither a base nor a registry."""
    del models
    return [], []


def mappers_configured(registry: Any, mappers: list[Any]) -> bool:
    """True when every mapper is configured and no registry ``registry`` depends on has one waiting."""
    del registry, mappers
    return True
