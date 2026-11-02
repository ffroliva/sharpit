"""``GET {api}/data/repositories[/{name}]``: one row per SQLAlchemy mapped class handed to ``install(models=...)``.

Port of BootUI ``DataController`` (contract Wave A §1), with the Spring Data repository replaced by the mapped class.
The collector is duck-typed over the objects the app passed in (a declarative base, a ``registry``) and never imports
SQLAlchemy. It reads ``registry.mappers`` and, per mapper, ``class_``, ``configured``, ``primary_key`` and
``local_table``: none of those configures anything. ``mapper.relationships`` and ``mapper.attrs`` call
``configure_mappers()`` for the mapper's registry (user code, may raise), so they are read only when **every** mapper
of that registry is already configured, which is what makes the registry's "new mapper" flag clear. A GET never
configures mappers, runs SQL or calls user code (spec §4).
"""

from __future__ import annotations

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


def _registry_of(entry: object) -> object | None:
    candidate = entry if hasattr(entry, "mappers") else getattr(entry, "registry", None)
    return candidate if hasattr(candidate, "mappers") else None


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


def _relationships(mapper: Any) -> list[dict[str, Any]]:
    rows = [
        {"name": str(rel.key), "target": _qualified(rel.mapper.class_), "lazy": str(rel.lazy)}
        for rel in mapper.relationships
    ]
    return sorted(rows, key=lambda row: row["name"])


def _row(mapper: Any, configured: bool) -> dict[str, Any]:
    cls = mapper.class_
    table = mapper.local_table
    name = _qualified(cls)
    return {
        "beanName": cls.__qualname__,
        "repositoryInterface": name,
        "domainType": name,
        "idType": ", ".join(type(column.type).__name__ for column in mapper.primary_key) or None,
        "storeModule": STORE_MODULE,
        "customImplementation": None,
        "queryMethodCount": None,
        "fragmentCount": None,
        "table": None if table is None else str(table.fullname),
        "relationships": _relationships(mapper) if configured else None,
    }


def _is_configured(mapper: Any) -> bool:
    try:
        return bool(mapper.configured)
    except Exception:  # noqa: BLE001
        return False


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
            warnings.append(f"Skipping a registry that could not be read ({type(error).__name__}: {error})")
            continue
        configured = all(_is_configured(mapper) for mapper in mappers)
        pending = pending or not configured
        for mapper in mappers:
            try:
                rows.append(_row(mapper, configured))
            except Exception as error:  # noqa: BLE001 - one bad mapper drops only its own row
                warnings.append(f"Skipping a mapper that could not be read ({type(error).__name__}: {error})")
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
