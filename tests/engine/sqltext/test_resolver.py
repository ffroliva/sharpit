"""# derived: BootUI has no dialect resolver; these rows pin the event proof rules."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import sharpit.engine.sqla.dialect_source as dialect_source
import sharpit.engine.sqltext.dialect as dialect_module
from sharpit.engine.sqla.dialect_source import ExceptionDialectSource
from sharpit.engine.sqltext.dialect import (
    Dialect,
    DialectContext,
    exception_leaves,
    read_chain,
    resolve,
)


@dataclass
class Source:
    result: Dialect | None

    def dialect_of(self, event: object, context: DialectContext) -> Dialect | None:
        return self.result


def context(family: Dialect | None = None, calls: list[str] | None = None) -> DialectContext:
    def application() -> Dialect | None:
        if calls is not None:
            calls.append("application")
        return family

    return DialectContext(application)


@pytest.mark.parametrize("family", [Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY, Dialect.SQLITE])
def test_one_source_family_resolves(family: Dialect) -> None:
    assert resolve(object(), [Source(family)], context()) is family


def test_an_unmapped_name_stops_later_sources() -> None:
    later = Source(Dialect.POSTGRESQL)
    assert resolve(object(), [Source(Dialect.UNSUPPORTED), later], context()) is Dialect.UNSUPPORTED


def test_two_source_families_conflict() -> None:
    assert resolve(object(), [Source(Dialect.POSTGRESQL), Source(Dialect.SQLITE)], context()) is Dialect.UNSUPPORTED


def test_event_proof_conflicts_with_application() -> None:
    calls: list[str] = []
    assert resolve(object(), [Source(Dialect.MYSQL_FAMILY)], context(Dialect.POSTGRESQL, calls)) is Dialect.UNSUPPORTED
    assert calls == ["application"]


def test_no_proof_uses_application_or_unsupported() -> None:
    assert resolve(object(), [Source(None)], context(Dialect.SQLITE)) is Dialect.SQLITE
    assert resolve(object(), [Source(None)], context()) is Dialect.UNSUPPORTED


def driver_error(module: str, name: str = "Error") -> BaseException:
    cls = type(name, (Exception,), {"__module__": module})
    return cls("failure")


def _assert_driver_table(module: str, expected: Dialect) -> None:
    reading = read_chain(driver_error(module))
    assert reading.families == frozenset({expected})
    assert not reading.stopped
    assert not reading.exhausted


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("psycopg", Dialect.POSTGRESQL),
        ("psycopg2.errors", Dialect.POSTGRESQL),
        ("asyncpg.exceptions", Dialect.POSTGRESQL),
        ("pg8000.exceptions", Dialect.POSTGRESQL),
        ("sqlalchemy.dialects.postgresql.asyncpg", Dialect.POSTGRESQL),
        ("pymysql.err", Dialect.MYSQL_FAMILY),
        ("MySQLdb", Dialect.MYSQL_FAMILY),
        ("mysql.connector.errors", Dialect.MYSQL_FAMILY),
        ("mariadb", Dialect.MYSQL_FAMILY),
        ("asyncmy", Dialect.MYSQL_FAMILY),
        ("aiomysql", Dialect.MYSQL_FAMILY),
        ("sqlite3", Dialect.SQLITE),
    ],
)
def test_driver_table_rows(module: str, expected: Dialect) -> None:
    _assert_driver_table(module, expected)


def test_one_family_two_drivers_is_no_conflict() -> None:
    outer = driver_error("psycopg")
    outer.__cause__ = driver_error("psycopg2.errors")
    assert read_chain(outer).families == frozenset({Dialect.POSTGRESQL})
    assert resolve(outer, [ExceptionDialectSource()], context()) is Dialect.POSTGRESQL


def test_the_walk_follows_orig() -> None:
    outer = Exception("wrapper")
    object.__setattr__(outer, "orig", driver_error("pg8000.exceptions"))
    assert read_chain(outer).families == frozenset({Dialect.POSTGRESQL})


def test_sqlalchemy_package_match_is_exact() -> None:
    outer = driver_error("sqlalchemy.exchange", "ProgrammingError")
    outer.__cause__ = driver_error("sqlite3")
    assert resolve(outer, [ExceptionDialectSource()], context()) is Dialect.UNSUPPORTED


def test_sqlalchemy_internal_driver_nodes_allow_the_chain_walk_to_continue() -> None:
    outer = driver_error("sqlalchemy.dialects.mysql.asyncmy", "ProgrammingError")
    outer.__cause__ = driver_error("psycopg.errors")
    assert resolve(outer, [ExceptionDialectSource()], context()) is Dialect.POSTGRESQL


def test_a_module_string_subclass_is_not_driver_proof() -> None:
    class ModuleName(str):
        pass

    error = type("ProgrammingError", (Exception,), {"__module__": ModuleName("psycopg")})("failed")
    assert read_chain(error).families == frozenset()


def test_two_families_in_a_chain_conflict() -> None:
    outer = driver_error("psycopg")
    outer.__cause__ = driver_error("sqlite3")
    assert resolve(outer, [ExceptionDialectSource()], context(Dialect.POSTGRESQL)) is Dialect.UNSUPPORTED


def test_event_proof_against_chain_conflicts() -> None:
    error = driver_error("pymysql")
    assert resolve(error, [Source(Dialect.POSTGRESQL), ExceptionDialectSource()], context()) is Dialect.UNSUPPORTED


def test_an_unlisted_dbapi_driver_stops_before_application() -> None:
    error = driver_error("oracledb", "DatabaseError")
    assert resolve(error, [ExceptionDialectSource()], context(Dialect.SQLITE)) is Dialect.UNSUPPORTED


def test_a_context_class_outside_the_driver_table_is_not_a_family() -> None:
    assert read_chain(driver_error("company.wrapper")).families == frozenset()


def test_a_suppressed_context_is_not_walked() -> None:
    outer = Exception("outer")
    outer.__context__ = driver_error("psycopg")
    outer.__suppress_context__ = True
    assert read_chain(outer).families == frozenset()


def test_the_walk_reaches_group_leaves() -> None:
    group = ExceptionGroup("group", [driver_error("psycopg"), driver_error("sqlite3")])
    assert read_chain(group).families == frozenset({Dialect.POSTGRESQL, Dialect.SQLITE})


def test_the_walk_survives_a_cycle() -> None:
    outer = Exception("outer")
    inner = driver_error("psycopg")
    object.__setattr__(outer, "__cause__", inner)
    object.__setattr__(inner, "orig", outer)
    assert read_chain(outer).families == frozenset({Dialect.POSTGRESQL})


def test_the_walk_stops_at_its_bound() -> None:
    outer = Exception("outer")
    current = outer
    for _ in range(32):
        following = Exception("wrapper")
        current.__cause__ = following
        current = following
    current.__cause__ = driver_error("psycopg")
    assert read_chain(outer).exhausted
    assert resolve(outer, [ExceptionDialectSource()], context(Dialect.SQLITE)) is Dialect.UNSUPPORTED


def test_the_walk_stops_when_group_children_exceed_its_bound() -> None:
    group = ExceptionGroup("wide", [driver_error("psycopg") for _ in range(33)])
    reading = read_chain(group)
    assert reading.exhausted
    assert reading.visited == 1
    assert resolve(group, [ExceptionDialectSource()], context(Dialect.POSTGRESQL)) is Dialect.UNSUPPORTED


def test_the_walk_reads_no_property() -> None:
    calls: list[str] = []

    class Hostile(Exception):
        @property
        def orig(self) -> BaseException:
            calls.append("orig")
            raise RuntimeError("property read")

        @property
        def __cause__(self) -> BaseException | None:
            calls.append("cause")
            raise RuntimeError("cause property read")

        @property
        def __context__(self) -> BaseException | None:
            calls.append("context")
            raise RuntimeError("context property read")

        @property
        def __suppress_context__(self) -> bool:
            calls.append("suppress")
            raise RuntimeError("suppress property read")

    hostile = Hostile()
    BaseException.__dict__["__cause__"].__set__(hostile, driver_error("psycopg"))
    reading = read_chain(hostile)
    assert reading.families == frozenset({Dialect.POSTGRESQL})
    assert not reading.stopped
    assert calls == []


def test_a_quiet_cause_property_cannot_hide_the_real_driver() -> None:
    class Quiet(Exception):
        @property
        def __cause__(self) -> BaseException | None:
            return None

    quiet = Quiet()
    BaseException.__dict__["__cause__"].__set__(quiet, driver_error("psycopg"))
    assert read_chain(quiet).families == frozenset({Dialect.POSTGRESQL})
    assert resolve(quiet, [ExceptionDialectSource()], context(Dialect.MYSQL_FAMILY)) is Dialect.UNSUPPORTED


def test_a_quiet_suppress_property_cannot_reveal_a_suppressed_context() -> None:
    class Quiet(Exception):
        @property
        def __suppress_context__(self) -> bool:
            return False

    quiet = Quiet()
    BaseException.__dict__["__context__"].__set__(quiet, driver_error("psycopg"))
    BaseException.__dict__["__suppress_context__"].__set__(quiet, True)
    assert read_chain(quiet).families == frozenset()


def test_a_quiet_dict_property_cannot_hide_orig() -> None:
    class Quiet(Exception):
        @property
        def __dict__(self) -> dict[str, object]:  # pyright: ignore[reportIncompatibleVariableOverride]
            return {}

    quiet = Quiet()
    BaseException.__dict__["__dict__"].__get__(quiet)["orig"] = driver_error("psycopg")
    assert read_chain(quiet).families == frozenset({Dialect.POSTGRESQL})


def test_a_link_that_cannot_be_read_hides_the_application_family() -> None:
    class Unreadable:
        __class__ = ValueError  # passes isinstance, so the walk visits it; BaseException's own descriptors refuse it

    outer = Exception("wrapper")
    object.__setattr__(outer, "orig", Unreadable())
    reading = read_chain(outer)
    assert reading.stopped
    assert resolve(outer, [ExceptionDialectSource()], context(Dialect.POSTGRESQL)) is Dialect.UNSUPPORTED


def _moduleless_error() -> type[Exception]:
    """A class whose dictionary has no ``__module__``: ``type`` raises when asked for it."""
    namespace: dict[str, object] = {}
    exec("E = type('Error', (Exception,), {})", namespace)  # noqa: S102 - globals without __name__
    return namespace["E"]  # pyright: ignore[reportReturnType]


# derived: Task 27 Opus review r2 #1: a class with no __module__ cannot make the walk raise; it stops it
def test_a_class_with_no_module_stops_the_walk() -> None:
    try:
        stopped = read_chain(_moduleless_error()("failed")).stopped
    except Exception:  # noqa: BLE001 - the defect; pytest cannot render a traceback holding this class
        stopped = None
    assert stopped is True


# derived: Task 27 Opus review r2 #2: an ``orig`` that is not an exception stops the walk, however it disguises itself
def test_a_link_whose_getattribute_claims_a_class_stops_the_walk() -> None:
    class Disguised:
        def __getattribute__(self, name: str) -> object:
            return ValueError if name == "__class__" else object.__getattribute__(self, name)

    outer = Exception("wrapper")
    object.__setattr__(outer, "orig", Disguised())
    assert read_chain(outer).stopped


# derived: Task 27 Opus review r2 #6: ``orig`` is read from the instance dictionary without running a subclass's get
def test_an_instance_dict_subclass_get_never_runs() -> None:
    ran: list[str] = []

    class SpyDict(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:  # pyright: ignore[reportIncompatibleMethodOverride]
            ran.append(key)
            return super().get(key, default)

    outer = Exception("wrapper")
    outer.__dict__ = SpyDict(orig=driver_error("psycopg"))
    read_chain(outer)
    assert ran == []


def test_class_metadata_failure_cannot_escape_the_resolver() -> None:
    class HostFailure(BaseException):
        pass

    class Meta(type):
        def __getattribute__(cls, name: str) -> object:
            if name == "__module__":
                raise HostFailure
            return super().__getattribute__(name)

    class ProgrammingError(Exception, metaclass=Meta):
        pass

    error = ProgrammingError("failed")
    assert resolve(error, [ExceptionDialectSource()], context(Dialect.POSTGRESQL)) is Dialect.UNSUPPORTED


def test_a_metaclass_module_property_never_runs() -> None:
    calls: list[str] = []

    class HostFailure(BaseException):
        pass

    def read(_cls: type) -> str:
        calls.append("read")
        raise HostFailure

    meta = type("Meta", (type,), {"__module__": property(read)})
    error = meta("ProgrammingError", (Exception,), {"__module__": "psycopg"})("failed")
    reading = read_chain(error)
    assert reading.families == frozenset({Dialect.POSTGRESQL})
    assert not reading.stopped
    assert calls == []


@pytest.mark.parametrize("name", ["__mro__", "__name__"])
def test_a_metaclass_property_cannot_hide_an_unlisted_driver(name: str) -> None:
    def read(_cls: type) -> object:
        raise RuntimeError(name)

    meta = type("Meta", (type,), {name: property(read)})
    error = meta("ProgrammingError", (Exception,), {"__module__": "oracledb"})("failed")
    resolved = resolve(error, [ExceptionDialectSource()], context(Dialect.POSTGRESQL))  # pytest cannot repr ``error``
    assert resolved is Dialect.UNSUPPORTED


def test_a_class_with_no_module_hides_the_application_family() -> None:
    # a class built where globals have no ``__name__`` gets no ``__module__``; ``del`` refuses, this does not
    builtins = {"type": type, "Exception": Exception}
    no_module = eval('type("NoModule", (Exception,), {})', {"__builtins__": builtins})  # noqa: S307
    assert resolve(no_module("failed"), [ExceptionDialectSource()], context(Dialect.POSTGRESQL)) is Dialect.UNSUPPORTED


def test_a_falsy_application_family_is_still_the_family(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Dialect, "__bool__", lambda _self: False, raising=False)
    assert resolve(object(), [Source(None)], context(Dialect.SQLITE)) is Dialect.SQLITE


def test_internal_module_string_subclass_is_not_sqlalchemy_proof() -> None:
    class ModuleName(str):
        pass

    module = ModuleName("sqlalchemy.dialects.mysql.asyncmy")
    internal = type("ProgrammingError", (Exception,), {"__module__": module})()
    internal.__cause__ = driver_error("psycopg")
    assert resolve(internal, [ExceptionDialectSource()], context()) is Dialect.UNSUPPORTED


def test_wrapper_module_string_subclass_is_not_sqlalchemy_proof() -> None:
    class ModuleName(str):
        pass

    wrapper = type("ProgrammingError", (Exception,), {"__module__": ModuleName("sqlalchemy.exc")})()
    wrapper.__cause__ = driver_error("psycopg")
    assert resolve(wrapper, [ExceptionDialectSource()], context()) is Dialect.UNSUPPORTED


def test_chain_walk_uses_the_builtin_bounded_group_children() -> None:
    calls: list[str] = []

    class HostileGroup(ExceptionGroup):
        @property
        def exceptions(self) -> tuple[BaseException, ...]:
            calls.append("exceptions")
            raise RuntimeError("property read")

    group = HostileGroup("group", [driver_error("psycopg")])
    assert read_chain(group).families == frozenset({Dialect.POSTGRESQL})
    assert calls == []


def test_engine_event_candidates_conflict() -> None:
    event = SimpleNamespace(
        dialect=Dialect.MYSQL_FAMILY,
        engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        error=None,
    )
    assert dialect_source.EngineDialectSource().dialect_of(event, context()) is Dialect.UNSUPPORTED


def test_an_event_with_no_error_never_reaches_the_exception_source(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def walked(_self: object, _event: object, _context: DialectContext) -> None:
        calls.append("walked")

    monkeypatch.setattr(ExceptionDialectSource, "dialect_of", walked)
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    event = SimpleNamespace(dialect=Dialect.POSTGRESQL, engine=engine, error=None)
    assert dialect_source.event_dialect(event, lambda: None) is Dialect.POSTGRESQL
    assert calls == []


def test_a_statement_that_proves_its_family_never_reads_the_application() -> None:
    """The common path: the event's own connection answers, so no statement walks the engine registry."""
    reads: list[str] = []

    def application() -> Dialect:
        reads.append("read")
        return Dialect.POSTGRESQL

    event = SimpleNamespace(dialect=Dialect.POSTGRESQL, engine=FakeEngine("postgresql"), error=None)
    assert dialect_source.event_dialect(event, application) is Dialect.POSTGRESQL
    assert reads == []


def test_a_statement_that_proves_nothing_takes_the_application() -> None:
    event = SimpleNamespace(dialect=None, engine=None, error=None)
    assert dialect_source.event_dialect(event, lambda: Dialect.SQLITE) is Dialect.SQLITE


def test_a_statement_that_proves_nothing_in_an_unknown_application_hides() -> None:
    event = SimpleNamespace(dialect=None, engine=None, error=None)
    assert dialect_source.event_dialect(event, lambda: None) is Dialect.UNSUPPORTED


def test_a_failed_statement_still_meets_the_application() -> None:
    """A failure is rare, so it pays for the whole check: its own proof against step 2 hides."""
    event = SimpleNamespace(dialect=Dialect.MYSQL_FAMILY, engine=FakeEngine("mysql"), error=driver_error("pymysql"))
    assert dialect_source.event_dialect(event, lambda: Dialect.POSTGRESQL) is Dialect.UNSUPPORTED


def test_a_disagreeing_engine_hides_an_event_with_no_error() -> None:
    event = SimpleNamespace(dialect=Dialect.POSTGRESQL, engine=FakeEngine("mysql"), error=None)
    assert dialect_source.event_dialect(event, lambda: None) is Dialect.UNSUPPORTED


def test_an_error_of_another_family_hides_an_agreeing_event() -> None:
    event = SimpleNamespace(dialect=Dialect.POSTGRESQL, engine=FakeEngine("postgresql"), error=driver_error("sqlite3"))
    assert dialect_source.event_dialect(event, lambda: None) is Dialect.UNSUPPORTED


def test_a_disagreeing_context_hides_an_agreeing_event() -> None:
    execution = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    event = SimpleNamespace(dialect=Dialect.MYSQL_FAMILY, engine=FakeEngine("mysql"), error=None, context=execution)
    assert dialect_source.event_dialect(event, lambda: None) is Dialect.UNSUPPORTED


def test_the_engine_source_counts_the_context() -> None:
    execution = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    event = SimpleNamespace(dialect=Dialect.MYSQL_FAMILY, context=execution)
    assert dialect_source.EngineDialectSource().dialect_of(event, context()) is Dialect.UNSUPPORTED


def test_an_agreeing_context_keeps_the_event() -> None:
    execution = SimpleNamespace(dialect=SimpleNamespace(name="mysql"))
    event = SimpleNamespace(dialect=Dialect.MYSQL_FAMILY, engine=FakeEngine("mysql"), error=None, context=execution)
    assert dialect_source.event_dialect(event, lambda: None) is Dialect.MYSQL_FAMILY


@pytest.mark.parametrize("name", ["dialect", "engine", "error", "context"])
def test_an_event_field_that_cannot_be_read_hides(name: str) -> None:
    class Event:
        dialect = Dialect.POSTGRESQL
        engine = FakeEngine("postgresql")
        error = None
        context = None

    def unreadable(_self: object) -> object:
        raise KeyboardInterrupt

    setattr(Event, name, property(unreadable))
    assert dialect_source.event_dialect(Event(), lambda: Dialect.POSTGRESQL) is Dialect.UNSUPPORTED


class FakeEngine:
    """Hashable and weakly referenced, as a real engine is."""

    def __init__(self, name: str) -> None:
        self.dialect = SimpleNamespace(name=name)


def test_engine_dialect_follows_a_changed_name() -> None:
    engine = FakeEngine("postgresql")
    assert dialect_source.engine_dialect(engine) is Dialect.POSTGRESQL
    engine.dialect.name = "mysql"
    assert dialect_source.engine_dialect(engine) is Dialect.MYSQL_FAMILY


def test_engine_dialect_follows_a_replaced_dialect() -> None:
    engine = FakeEngine("postgresql")
    assert dialect_source.engine_dialect(engine) is Dialect.POSTGRESQL
    engine.dialect = SimpleNamespace(name="sqlite")
    assert dialect_source.engine_dialect(engine) is Dialect.SQLITE


def test_engine_dialect_can_be_reentered_from_inside_its_own_read() -> None:
    """The shape of a collection that runs a statement's finalizer inside a read: a lock here deadlocks one thread."""
    inner = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    seen: list[Dialect | None] = []

    class Engine:
        dialect = SimpleNamespace(name="postgresql")

        def __hash__(self) -> int:
            seen.append(dialect_source.engine_dialect(inner))
            return 1

    finished = threading.Event()

    def read() -> None:
        dialect_source.engine_dialect(Engine())
        finished.set()

    threading.Thread(target=read, daemon=True).start()
    assert finished.wait(5)


def test_engine_dialect_is_none_without_a_dialect() -> None:
    assert dialect_source.engine_dialect(SimpleNamespace()) is None


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_a_dialect_that_cannot_be_read_hides(failure: type[BaseException]) -> None:
    class Engine:
        @property
        def dialect(self) -> object:
            raise failure

    assert dialect_source.engine_dialect(Engine()) is Dialect.UNSUPPORTED


@pytest.mark.parametrize("dialect", [SimpleNamespace(), SimpleNamespace(name=None), SimpleNamespace(name=1)])
def test_a_dialect_with_no_usable_name_hides(dialect: object) -> None:
    assert dialect_source.engine_dialect(SimpleNamespace(dialect=dialect)) is Dialect.UNSUPPORTED


def test_a_name_string_subclass_runs_no_code_and_hides() -> None:
    calls: list[str] = []

    class Name(str):
        def __hash__(self) -> int:
            calls.append("hash")
            return super().__hash__()

    engine = SimpleNamespace(dialect=SimpleNamespace(name=Name("postgresql")))
    assert dialect_source.engine_dialect(engine) is Dialect.UNSUPPORTED
    assert calls == []


def test_the_name_table_cannot_be_changed() -> None:
    with pytest.raises(TypeError):
        dialect_module._NAMES["oracle"] = Dialect.POSTGRESQL  # noqa: SLF001  # pyright: ignore[reportIndexIssue]


def test_exception_leaves_are_bounded() -> None:
    group = ExceptionGroup("many", [Exception("leaf") for _ in range(2_000)])
    assert len(exception_leaves(group)) <= 32


def test_exception_leaves_do_not_follow_a_recursive_group_property() -> None:
    calls: list[str] = []

    class RecursiveGroup(ExceptionGroup):
        @property
        def exceptions(self) -> tuple[BaseException, ...]:
            calls.append("exceptions")
            return (self,) if len(calls) == 1 else ()

    leaf = Exception("leaf")
    group = RecursiveGroup("group", [leaf])
    assert exception_leaves(group) == [leaf]
    assert calls == []


def test_resolve_hides_when_a_source_raises_baseexception() -> None:
    class HostFailure(BaseException):
        pass

    class BrokenSource:
        def dialect_of(self, event: object, context: DialectContext) -> Dialect | None:
            raise HostFailure

    try:
        actual = resolve(object(), [BrokenSource()], context(Dialect.POSTGRESQL))
    except HostFailure:
        actual = None
    assert actual is Dialect.UNSUPPORTED


def test_exception_source_ignores_text_that_looks_like_a_driver() -> None:
    event = type("Event", (), {"error": "psycopg.errors.ProgrammingError: failed"})()
    assert ExceptionDialectSource().dialect_of(event, context()) is None


def test_the_walk_stays_linear() -> None:
    outer = Exception("outer")
    current = outer
    for _ in range(24):
        following = Exception("wrapper")
        current.__cause__ = following
        current = following
    current.__cause__ = driver_error("psycopg")
    reading = read_chain(outer)
    assert reading.families == frozenset({Dialect.POSTGRESQL})
    assert reading.visited <= 32
