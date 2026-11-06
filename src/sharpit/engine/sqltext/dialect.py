"""Which SQL dialect a database name means. A present but unknown name is ``UNSUPPORTED`` and ends the search."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Protocol, cast


class Dialect(Enum):
    POSTGRESQL = "postgresql"
    MYSQL_FAMILY = "mysql_family"
    SQLITE = "sqlite"
    UNSUPPORTED = "unsupported"


_NAMES = MappingProxyType(
    {
        "postgresql": Dialect.POSTGRESQL,
        "mysql": Dialect.MYSQL_FAMILY,
        "mariadb": Dialect.MYSQL_FAMILY,
        "sqlite": Dialect.SQLITE,
    }
)
_DRIVERS = {
    "psycopg": Dialect.POSTGRESQL,
    "psycopg2": Dialect.POSTGRESQL,
    "asyncpg": Dialect.POSTGRESQL,
    "pg8000": Dialect.POSTGRESQL,
    "sqlalchemy.dialects.postgresql.asyncpg": Dialect.POSTGRESQL,
    "pymysql": Dialect.MYSQL_FAMILY,
    "MySQLdb": Dialect.MYSQL_FAMILY,
    "mysql": Dialect.MYSQL_FAMILY,
    "mariadb": Dialect.MYSQL_FAMILY,
    "asyncmy": Dialect.MYSQL_FAMILY,
    "aiomysql": Dialect.MYSQL_FAMILY,
    "sqlite3": Dialect.SQLITE,
}
_DBAPI_NAMES = frozenset(
    {
        "Warning",
        "Error",
        "InterfaceError",
        "DatabaseError",
        "DataError",
        "OperationalError",
        "IntegrityError",
        "InternalError",
        "ProgrammingError",
        "NotSupportedError",
    }
)
_CHAIN_LIMIT = 32
_LEAF_LIMIT = 32
# BaseException's own descriptors: a subclass property of the same name never runs, so it cannot raise or hide a link
_CAUSE = BaseException.__dict__["__cause__"]
_CONTEXT = BaseException.__dict__["__context__"]
_SUPPRESS_CONTEXT = BaseException.__dict__["__suppress_context__"]
_INSTANCE_DICT = BaseException.__dict__["__dict__"]


def dialect_of_name(name: str | None) -> Dialect | None:
    """``None`` for no name at all; ``UNSUPPORTED`` for any other name the table does not know."""
    return None if name is None else _NAMES.get(name, Dialect.UNSUPPORTED)


class DialectSource(Protocol):
    def dialect_of(self, event: object, context: DialectContext) -> Dialect | None: ...


@dataclass(frozen=True)
class DialectContext:
    application: Callable[[], Dialect | None]


@dataclass(frozen=True)
class ChainReading:
    families: frozenset[Dialect]
    stopped: bool = False
    exhausted: bool = False
    visited: int = 0


def exception_leaves(exc: BaseException) -> list[BaseException]:
    """Bounded exception-group leaves, read without invoking subclass properties."""
    pending = [exc]
    leaves: list[BaseException] = []
    seen: set[int] = set()
    while pending:
        if len(seen) >= _LEAF_LIMIT:
            return []
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, BaseExceptionGroup):
            group = cast("BaseExceptionGroup[BaseException]", current)
            children = cast(
                "tuple[BaseException, ...]",
                BaseExceptionGroup.__dict__["exceptions"].__get__(group, type(group)),
            )
            pending.extend(reversed(children[: _LEAF_LIMIT - len(seen)]))
            if len(children) > _LEAF_LIMIT - len(seen):
                return []
        else:
            leaves.append(current)
    return leaves


def _class_value(cls: type, name: str) -> object:
    """``type``'s own descriptor, so no metaclass code runs. A missing value raises, and ``resolve`` hides on that."""
    return type.__dict__[name].__get__(cls)


def _driver_family(exc: BaseException) -> Dialect | None:
    module = _class_value(type(exc), "__module__")
    if type(module) is not str:
        return None
    for package, family in _DRIVERS.items():
        if module == package or module.startswith(package + "."):
            return family
    return None


def _is_dbapi_error(exc: BaseException) -> bool:
    classes = cast("tuple[type, ...]", _class_value(type(exc), "__mro__"))
    return any(_class_value(cls, "__name__") in _DBAPI_NAMES for cls in classes)


def _is_sqlalchemy_wrapper(exc: BaseException) -> bool:
    module = _class_value(type(exc), "__module__")
    return type(module) is str and (module == "sqlalchemy.exc" or module.startswith("sqlalchemy.exc."))


def _is_sqlalchemy_internal(exc: BaseException) -> bool:
    module = _class_value(type(exc), "__module__")
    return type(module) is str and (
        module.startswith("sqlalchemy.dialects.") or module.startswith("sqlalchemy.connectors.")
    )


def _queue_group_children(current: BaseException, pending: list[BaseException], visited: int) -> ChainReading | None:
    if not isinstance(current, BaseExceptionGroup):
        return None
    group = cast("BaseExceptionGroup[BaseException]", current)
    try:
        children = cast(
            "tuple[BaseException, ...]",
            BaseExceptionGroup.__dict__["exceptions"].__get__(group, type(group)),
        )
    except BaseException:
        return ChainReading(frozenset(), stopped=True, visited=visited)
    available = _CHAIN_LIMIT - visited
    if len(children) > available:
        return ChainReading(frozenset(), exhausted=True, visited=visited)
    pending.extend(reversed(children))
    return None


def _queue_exception_links(current: BaseException, pending: list[BaseException]) -> bool:
    """``False`` when a link cannot be read. SQLAlchemy keeps ``orig`` in the instance dictionary."""
    try:
        cause = _CAUSE.__get__(current)
        context = _CONTEXT.__get__(current)
        suppressed = _SUPPRESS_CONTEXT.__get__(current)
        original = _INSTANCE_DICT.__get__(current).get("orig")
    except BaseException:
        return False
    if isinstance(cause, BaseException):
        pending.append(cause)
    elif not suppressed and isinstance(context, BaseException):
        pending.append(context)
    if isinstance(original, BaseException):
        pending.append(original)
    return True


def read_chain(exc: BaseException) -> ChainReading:
    pending = [exc]
    seen: set[int] = set()
    families: set[Dialect] = set()
    visited = 0
    while pending and visited < _CHAIN_LIMIT:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        visited += 1
        family = _driver_family(current)
        if family is not None:
            families.add(family)
            if len(families) > 1:
                return ChainReading(frozenset(families), visited=visited)
        elif _is_dbapi_error(current) and not _is_sqlalchemy_wrapper(current) and not _is_sqlalchemy_internal(current):
            return ChainReading(frozenset(families), stopped=True, visited=visited)
        group_result = _queue_group_children(current, pending, visited)
        if group_result is not None:
            return ChainReading(frozenset(families), group_result.stopped, group_result.exhausted, visited)
        if not _queue_exception_links(current, pending):
            return ChainReading(frozenset(families), stopped=True, visited=visited)
        pending = [item for item in pending if id(item) not in seen]
    return ChainReading(frozenset(families), exhausted=bool(pending), visited=visited)


def resolve(event: object, sources: Sequence[DialectSource], context: DialectContext) -> Dialect:
    try:
        proof: set[Dialect] = set()
        for source in sources:
            found = source.dialect_of(event, context)
            if found is Dialect.UNSUPPORTED:
                return Dialect.UNSUPPORTED
            if found is not None:
                proof.add(found)
        if len(proof) > 1:
            return Dialect.UNSUPPORTED
        application = context.application()
        if proof:
            family = next(iter(proof))
            return family if application in (None, family) else Dialect.UNSUPPORTED
        return application if application is not None else Dialect.UNSUPPORTED
    except BaseException:
        return Dialect.UNSUPPORTED
