"""``GET {api}/data/repositories[/{name}]``: one row per SQLAlchemy mapped class handed to ``install(models=...)``.

Port of BootUI ``DataController`` (contract Wave A §1), with the Spring Data repository replaced by the mapped class.
The collector is duck-typed over the objects the app passed in (a declarative base, a ``registry``) and never imports
SQLAlchemy. The registries and the configured-gate come from ``engine/models.py``; per mapper it reads ``class_``,
``primary_key`` and ``local_table`` (none configures anything) and ``relationships`` only behind the gate. A GET never
configures mappers, runs SQL or calls user code (spec §4).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any, NamedTuple, cast

from sharpit.engine import sqla
from sharpit.engine.context import SharpitContext, application_family
from sharpit.engine.models import mappers_configured, registries
from sharpit.engine.sqla.dialect_source import exception_dialect
from sharpit.engine.sqltext import Dialect, error_text

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


def _qualified(cls: Any) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _lazy(value: object) -> str:
    # relationship(lazy=...) still accepts None, True and False; report the strategy they stand for
    return (
        {None: "noload", True: "select", False: "joined"}[value]
        if value is None or isinstance(value, bool)
        else str(value)
    )


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
        warnings.append(_warning(ctx, f"Could not read {label}", error))
        return None


def _masked(ctx: SharpitContext, text: str, error: BaseException | None = None) -> str:
    application = partial(application_family, ctx)
    family = exception_dialect(error, application) if error is not None else application()
    dialect = Dialect.UNSUPPORTED if family is None else family
    if error is not None:
        return error_text(ctx.masker, error, dialect) or type(error).__name__
    return error_text(ctx.masker, text, dialect) or text.split(" (", 1)[0]


def _warning(ctx: SharpitContext, label: str, error: BaseException) -> str:
    """``label (Name: message)``. The message is read from the object, never by ``str()``, which is application code
    and can raise; the label is sharpit's own text and stays outside what is masked."""
    name = type(error).__name__
    message = _masked(ctx, name, error)
    return f"{label} ({name})" if message == name else f"{label} ({name}: {message})"


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
            warnings.append(_warning(ctx, "Skipping a registry that could not be read", error))
            continue
        configured = mappers_configured(registry, mappers)
        pending = pending or not configured
        for mapper in mappers:
            try:
                rows.append(_row(ctx, warnings, mapper, configured))
            except Exception as error:  # noqa: BLE001 - one bad mapper drops only its own row
                warnings.append(_warning(ctx, "Skipping a mapper that could not be read", error))
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
