"""``GET {api}/data/repositories[/{name}]``: one row per SQLAlchemy mapped class handed to ``install(models=...)``.

Port of BootUI ``DataController`` (contract Wave A §1), with the Spring Data repository replaced by the mapped class.
The collector is duck-typed over the objects the app passed in (a declarative base, a ``registry``) and never imports
SQLAlchemy. It reads ``registry.mappers`` and, per mapper, ``class_``, ``configured``, ``primary_key`` and
``local_table``: none of those configures anything. ``mapper.relationships`` and ``mapper.attrs`` call
``configure_mappers()`` for the mapper's registry and the registries it depends on (user code, may raise), so they are
read only when every mapper is ``configured`` **and** the registry and each registry it depends on have a clear
``_new_mappers`` flag (a mapper added to a registry flags its dependents, whose own mappers still say ``configured``).
That flag is private: a real SQLAlchemy registry without it counts as not configured (fail closed). A GET never
configures mappers, runs SQL or calls user code (spec §4).
"""

from __future__ import annotations

from collections.abc import Callable
from inspect import getattr_static
from typing import Any, NamedTuple, cast

from sharpit.engine import sqla
from sharpit.engine.context import SharpitContext

NO_MODELS = "pass models= to sharpit.install"
UNCONFIGURED = "Mappers are not configured yet: the app has not run a query"
NO_REGISTRY = "models= holds no declarative base or registry"
STORE_MODULE = "SQLAlchemy"
_SUMMARY_KEYS = ("beanName", "repositoryInterface", "domainType", "idType", "storeModule", "customImplementation")


class _Scan(NamedTuple):
    rows: list[dict[str, Any]]
    warnings: list[str]
    reason: str | None
    present: bool


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


def _qualified(cls: Any) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


_LEGACY_LAZY = {None: "noload", True: "select", False: "joined"}


def _lazy(value: object) -> str:
    # relationship(lazy=...) still accepts None, True and False; report the strategy they stand for
    return _LAZY_NAME.get(value, str(value)) if isinstance(value, bool) or value is None else str(value)


_LAZY_NAME = _LEGACY_LAZY


def _relationships(mapper: Any) -> list[dict[str, Any]]:
    rows = [
        {"name": str(rel.key), "target": _qualified(rel.mapper.class_), "lazy": _lazy(rel.lazy)}
        for rel in mapper.relationships
    ]
    return sorted(rows, key=lambda row: row["name"])


def _field(ctx: SharpitContext, warnings: list[str], label: str, read: Callable[[], Any]) -> Any:
    """One field of a row; a failure nulls that field with a masked warning and keeps the row."""
    try:
        return read()
    except Exception as error:  # noqa: BLE001 - user mapping code must not fail the GET
        warnings.append(_masked(ctx, f"Could not read {label} ({type(error).__name__}: {error})"))
        return None


def _masked(ctx: SharpitContext, text: str) -> str:
    return ctx.masker.mask_text(text) or text.split(" (", 1)[0]


def _table(mapper: Any) -> str | None:
    table = mapper.local_table  # a Join or Subquery has no ``fullname``: no table name, not an error
    name = getattr(table, "fullname", None)
    return None if name is None else str(name)


def _row(ctx: SharpitContext, warnings: list[str], mapper: Any, configured: bool) -> dict[str, Any]:
    cls = mapper.class_  # without the class there is no row to name: the caller drops it
    name = _qualified(cls)
    return {
        "beanName": cls.__qualname__,
        "repositoryInterface": name,
        "domainType": name,
        "idType": _field(
            ctx,
            warnings,
            f"the id type of {name}",
            lambda: ", ".join(type(c.type).__name__ for c in mapper.primary_key) or None,
        ),
        "storeModule": STORE_MODULE,
        "customImplementation": None,
        "queryMethodCount": None,
        "fragmentCount": None,
        "table": _field(ctx, warnings, f"the table of {name}", lambda: _table(mapper)),
        "relationships": _field(ctx, warnings, f"the relationships of {name}", lambda: _relationships(mapper))
        if configured
        else None,
    }


def _is_configured(mapper: Any) -> bool:
    try:
        return bool(mapper.configured)
    except Exception:  # noqa: BLE001
        return False


def _registry_is_clear(registry: Any) -> bool:
    """No registry this one depends on (itself included) has a mapper waiting to be configured."""
    if not type(registry).__module__.startswith("sqlalchemy"):
        return True  # not SQLAlchemy's registry: nothing private to read, the per-mapper flags decide
    try:
        pending = [registry]
        seen: list[Any] = []
        while pending:
            current = pending.pop()
            if any(current is other for other in seen):
                continue
            seen.append(current)
            if getattr(current, "_new_mappers", True):  # absent or True: fail closed
                return False
            pending.extend(getattr(current, "_dependencies", ()))
    except Exception:  # noqa: BLE001
        return False
    return True


def _scan(ctx: SharpitContext) -> _Scan:
    if not ctx.models:
        return _Scan([], [], NO_MODELS, False)
    unavailable = sqla.unavailable_reason()
    if unavailable is not None:
        return _Scan([], [], unavailable, False)
    found, warnings = registries(ctx.models)
    if not found:
        return _Scan([], warnings, NO_REGISTRY, False)
    rows: list[dict[str, Any]] = []
    pending = False
    for registry in found:
        try:
            mappers = list(cast(Any, registry).mappers)
        except Exception as error:  # noqa: BLE001
            warnings.append(
                _masked(ctx, f"Skipping a registry that could not be read ({type(error).__name__}: {error})")
            )
            continue
        configured = all(_is_configured(mapper) for mapper in mappers) and _registry_is_clear(registry)
        pending = pending or not configured
        for mapper in mappers:
            try:
                rows.append(_row(ctx, warnings, mapper, configured))
            except Exception as error:  # noqa: BLE001 - one bad mapper drops only its own row
                warnings.append(
                    _masked(ctx, f"Skipping a mapper that could not be read ({type(error).__name__}: {error})")
                )
    rows.sort(key=lambda row: row["repositoryInterface"])
    if pending:
        warnings.append(UNCONFIGURED)
    return _Scan(rows, warnings, UNCONFIGURED if pending else None, True)


def repositories_report(ctx: SharpitContext) -> dict[str, Any]:
    """``RepositoriesReport`` plus the extra keys ``unavailableReason`` and ``warnings``."""
    scan = _scan(ctx)
    return {
        "springDataPresent": scan.present,
        "total": len(scan.rows),
        "repositories": scan.rows,
        "unavailableReason": scan.reason,
        "warnings": scan.warnings,
    }


def _simple_name(row: dict[str, Any]) -> str:
    return str(row["repositoryInterface"]).rsplit(".", 1)[-1]


def repository_detail(ctx: SharpitContext, name: str) -> dict[str, Any] | None:
    """``RepositoryDetailDto`` for the class whose bean name, qualified name or simple name is ``name``; else ``None``.

    Rows are sorted by qualified name, so a simple name shared by two modules answers the first, as BootUI does.
    """
    row = next(
        (r for r in _scan(ctx).rows if name in (r["beanName"], r["repositoryInterface"], _simple_name(r))),
        None,
    )
    if row is None:
        return None
    relationships = row["relationships"]
    methods = [
        {
            "name": rel["name"],
            "signature": f"{rel['name']} -> {str(rel['target']).rsplit('.', 1)[-1]}",
            "origin": "APPLICATION",
            "query": None,
            "nativeQuery": False,
            "namedQuery": None,
        }
        for rel in relationships or ()
    ]
    return {
        **{key: row[key] for key in _SUMMARY_KEYS},
        "methods": methods,
        "fragments": [],
        "table": row["table"],
        "unavailableReason": UNCONFIGURED if relationships is None else None,
    }
