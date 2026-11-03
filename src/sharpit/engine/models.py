"""The mapper walk over ``install(models=...)`` and its configured-gate, shared by every ORM reader (0.5.0 spec §4.4).

Duck-typed over the objects the app passed in (a declarative base, a ``registry``, a mapped class); imports no
SQLAlchemy and never configures a mapper. ``mapper.relationships`` and ``mapper.attrs`` call ``configure_mappers()``
for the mapper's registry and the registries it depends on (user code, may raise), so a reader touches them only when
``mappers_configured`` says so: every mapper ``configured`` **and** the registry and each registry it depends on have a
clear ``_new_mappers`` flag (a mapper added to a registry flags its dependents, whose own mappers still say
``configured``). That flag is private: a real SQLAlchemy registry without it counts as not configured (fail closed).
"""

from __future__ import annotations

from inspect import getattr_static
from typing import Any

_MISSING = object()


def _has_mappers(candidate: object) -> bool:
    # getattr_static never runs a descriptor, so a hybrid property or a ``mappers`` column on a model is inert
    return not isinstance(candidate, type) and getattr_static(candidate, "mappers", _MISSING) is not _MISSING


def _registry_of(entry: object) -> object | None:
    candidate = getattr_static(entry, "registry", None) if isinstance(entry, type) else entry
    return candidate if _has_mappers(candidate) else None


def registries(models: tuple[object, ...]) -> tuple[list[object], list[str]]:
    """The distinct registries behind ``models`` (a base, a ``registry``, a mapped class); a warning per stranger."""
    found: list[object] = []
    warnings: list[str] = []
    for entry in models:
        try:
            registry = _registry_of(entry)
        except Exception:  # noqa: BLE001 - a hostile attribute must not fail the GET
            registry = None
        if registry is None:
            kind = type(entry).__name__
            warnings.append(f"Ignoring models entry of type {kind}: expected a declarative base or a registry")
        elif not any(registry is seen for seen in found):
            found.append(registry)
    return found, warnings


def _is_configured(mapper: Any) -> bool:
    try:
        return bool(mapper.configured)
    except Exception:  # noqa: BLE001
        return False


def _registry_is_clear(registry: Any) -> bool:
    """No registry this one depends on (itself included) has a mapper waiting to be configured."""
    if not any(c.__module__.startswith("sqlalchemy") for c in type(registry).__mro__):
        return True  # not SQLAlchemy's registry or a subclass: nothing private to read, the per-mapper flags decide
    try:
        pending = [registry]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            if getattr_static(current, "_new_mappers", True):  # absent or True: fail closed
                return False
            pending.extend(getattr_static(current, "_dependencies", ()))
    except Exception:  # noqa: BLE001
        return False
    return True


def mappers_configured(registry: Any, mappers: list[Any]) -> bool:
    """True when every mapper is configured and no registry ``registry`` depends on has one waiting."""
    return all(_is_configured(mapper) for mapper in mappers) and _registry_is_clear(registry)
