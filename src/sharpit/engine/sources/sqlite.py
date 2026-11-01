"""The raw ``sqlite3`` source (spec 0.3.0 §8.2-8.4): ``sqlite3.connect`` swapped for a tracing one while attached.

Only ``sqlite3.connect`` is patched, never ``sqlite3.dbapi2.connect``: SQLAlchemy opens SQLite through the latter, so it
stays on its own source and is never counted twice. The tracing runs in the caller's thread and adds a
``perf_counter_ns`` pair and one ``SqlEvent`` to each statement; ``set_trace_callback`` is never used (it expands the
bound values, which the masker cannot see).
"""

from __future__ import annotations

import contextlib
import gc
import logging
import sqlite3
import sqlite3.dbapi2 as dbapi2
import sys
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, cast

from sharpit.engine.sources import dispatch
from sharpit.engine.sources.dispatch import SqlEvent

logger = logging.getLogger("sharpit")

UNTRACED_CALLERS = ("coverage", "_pytest", "aiosqlite")
EARLY_CONNECTIONS = "connections opened before capture started are not traced"
COUNT_FAILED = "connections opened before capture started could not be counted"
FACTORY_PASSED_THROUGH = (
    "a connection factory or cursor class that does not subclass sqlite3.Connection / sqlite3.Cursor is not traced"
)
_OWNERS_NOT_EARLY = (*UNTRACED_CALLERS, "sqlalchemy")  # their connections are untraced by design or traced elsewhere
_SKIPPED_MODULES = ("sqlite3", "sqlite3.dbapi2", "_sqlite3")

_lock = threading.Lock()
_holders: set[str] = set()
_real: Callable[..., sqlite3.Connection] | None = None  # the stdlib function while attached
_patched: Callable[..., sqlite3.Connection] | None = None
_preexisting = 0
_count_failed = False
_passed_through = False
# shortcut: one derived class per caller factory class, unbounded; factories are few per process
_derived: dict[tuple[type, type], type] = {}


def _connection_id(connection: sqlite3.Connection) -> str:
    """``hex(id(connection))``, built once per traced connection and kept on it."""
    try:
        return connection.__dict__["_sharpit_id"]
    except (KeyError, AttributeError):
        pass
    cid = hex(id(connection))
    with contextlib.suppress(AttributeError):  # a caller's factory with __slots__: computed per statement
        connection.__dict__["_sharpit_id"] = cid
    return cid


def _event(
    cursor: sqlite3.Cursor,
    sql: str,
    parameters: object,
    many: bool,
    batch: int | None,
    started: int,
    rowcount: int,
    error: BaseException | None,
) -> None:
    dispatch.emit(
        SqlEvent(
            "sqlite3",
            sql,
            parameters,
            many,
            batch,
            started,
            time.perf_counter_ns() - started,
            rowcount,
            error,
            _connection_id(cursor.connection),
            None,
        )  # fmt: skip
    )


class _TracedCursorMixin:
    """The three statement methods of a cursor; ``super()`` is the stdlib (or the caller's) cursor class."""

    def execute(self, sql: str, parameters: Any = (), /) -> Any:
        started = time.perf_counter_ns()
        try:
            result = cast("sqlite3.Cursor", super()).execute(sql, parameters)
        except BaseException as exc:
            _event(cast("sqlite3.Cursor", self), sql, parameters, False, None, started, -1, exc)
            raise
        _event(cast("sqlite3.Cursor", self), sql, parameters, False, None, started, result.rowcount, None)
        return result

    def executemany(self, sql: str, parameters: Any, /) -> Any:
        # a one-shot generator is consumed by the query: no size, and nothing worth passing to the masker
        sized = cast("Sequence[object] | None", parameters if isinstance(parameters, Sequence) else None)
        batch = len(sized) if sized is not None else None
        shown: object = sized
        started = time.perf_counter_ns()
        try:
            result = cast("sqlite3.Cursor", super()).executemany(sql, cast("Any", parameters))
        except BaseException as exc:
            _event(cast("sqlite3.Cursor", self), sql, shown, True, batch, started, -1, exc)
            raise
        _event(cast("sqlite3.Cursor", self), sql, shown, True, batch, started, result.rowcount, None)
        return result

    def executescript(self, sql_script: str, /) -> Any:
        started = time.perf_counter_ns()
        try:
            result = cast("sqlite3.Cursor", super()).executescript(sql_script)
        except BaseException as exc:
            _event(cast("sqlite3.Cursor", self), sql_script, None, False, None, started, -1, exc)
            raise
        _event(cast("sqlite3.Cursor", self), sql_script, None, False, None, started, result.rowcount, None)
        return result


class TracedCursor(_TracedCursorMixin, sqlite3.Cursor):
    pass


def _traced(base: type, mixin: type) -> type:
    """``base`` with ``mixin`` in front, one class per ``base`` (a caller's own subclass keeps its behaviour)."""
    key = (base, mixin)
    found = _derived.get(key)
    if found is None:
        found = _derived[key] = type("Traced" + base.__name__, (mixin, base), {})
    return found


class _TracedConnectionMixin:
    """Connection-level statements run through ``self.cursor()``: the stdlib ones do not call a Python override."""

    def cursor(self, factory: Any = None) -> Any:
        global _passed_through  # noqa: PLW0603 - a limitation flag, set once
        if factory is None or factory is sqlite3.Cursor:
            cls: Any = TracedCursor
        elif isinstance(factory, type) and issubclass(factory, sqlite3.Cursor):
            cls = factory if issubclass(factory, _TracedCursorMixin) else _traced(factory, _TracedCursorMixin)
        else:
            _passed_through = True
            return cast("sqlite3.Connection", super()).cursor(cast("Any", factory))
        return cast("sqlite3.Connection", super()).cursor(cls)

    def execute(self, sql: str, parameters: Any = (), /) -> Any:
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql: str, parameters: Any, /) -> Any:
        return self.cursor().executemany(sql, parameters)

    def executescript(self, sql_script: str, /) -> Any:
        return self.cursor().executescript(sql_script)


class TracedConnection(_TracedConnectionMixin, sqlite3.Connection):
    pass


def _caller_untraced(depth: int) -> bool:
    """Whether the code that called ``sqlite3.connect`` is one of ``UNTRACED_CALLERS`` (decided once per connection)."""
    name = sys._getframe(depth).f_globals.get("__name__", "")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    return isinstance(name, str) and name.partition(".")[0] in UNTRACED_CALLERS


def _make_connect(real: Callable[..., sqlite3.Connection]) -> Callable[..., sqlite3.Connection]:
    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        global _passed_through  # noqa: PLW0603
        if not _holders or _caller_untraced(2):
            return real(*args, **kwargs)
        positional = (
            len(args) > 5
        )  # connect(database, timeout, detect_types, isolation_level, check_same_thread, factory)
        factory = args[5] if positional else kwargs.get("factory")
        if factory is None or factory is sqlite3.Connection:
            chosen: type = TracedConnection
        elif isinstance(factory, type) and issubclass(factory, sqlite3.Connection):
            chosen = (
                factory if issubclass(factory, _TracedConnectionMixin) else _traced(factory, _TracedConnectionMixin)
            )
        else:
            _passed_through = True
            return real(*args, **kwargs)
        if positional:
            args = (*args[:5], chosen, *args[6:])
        else:
            kwargs["factory"] = chosen
        return real(*args, **kwargs)

    return connect


def _count_preexisting() -> int:
    """Connections that already exist, minus those owned by coverage, pytest, aiosqlite or SQLAlchemy."""
    count = 0
    for obj in gc.get_objects():
        kind = cast("type[object]", type(obj))  # never isinstance: a proxy's __class__ would run its own code
        if issubclass(kind, sqlite3.Connection) and not issubclass(kind, _TracedConnectionMixin):
            count += not _owned_elsewhere(obj)
    return count


def _owned_elsewhere(conn: object) -> bool:
    try:
        for holder in gc.get_referrers(conn):
            candidates = gc.get_referrers(holder) if isinstance(holder, dict) else [holder]  # an instance's __dict__
            for owner in candidates:
                module = getattr(type(cast("object", owner)), "__module__", "") or ""
                if module.partition(".")[0] in _OWNERS_NOT_EARLY:
                    return True
    except Exception:  # noqa: BLE001 - counting is best effort
        return False
    return False


def attach(holder: str = "api") -> bool:
    """Patch ``sqlite3.connect`` for ``holder``; True when this call did the patching (a second holder shares it)."""
    global _real, _patched, _preexisting, _count_failed
    with _lock:
        _holders.add(holder)
        if _real is not None:
            return False
        try:
            count, _count_failed = _count_preexisting(), False
        except Exception:  # noqa: BLE001 - counting is best effort; attach never raises into the host
            count, _count_failed = 0, True
        real = sqlite3.connect
        patched = _make_connect(real)
        sqlite3.connect = patched  # type: ignore[assignment]
        _real, _patched, _preexisting = real, patched, count  # state only once the patch is in
        return True


def detach(holder: str = "api") -> bool:
    """Drop ``holder``; restore the stdlib function when the last holder leaves and nobody else re-patched it."""
    global _real, _patched, _passed_through, _count_failed
    with _lock:
        _holders.discard(holder)
        if _holders or _real is None:
            return False
        restored = sqlite3.connect is _patched
        if restored:
            sqlite3.connect = _real  # type: ignore[assignment]
        else:
            logger.warning("sharpit left sqlite3.connect alone: another library replaced it after sharpit's patch")
        _real = _patched = None
        _passed_through = _count_failed = False
        return restored


def detach_all() -> None:
    """Forget every holder and restore ``sqlite3.connect`` (tests start from a clean slate with it)."""
    with _lock:
        _holders.clear()
    detach("")


def is_attached() -> bool:
    return _real is not None


def preexisting_connections() -> int:
    return _preexisting


def early_aliases() -> list[str]:
    """``"<module>.<name>"`` for module globals bound to the original ``sqlite3.connect`` or ``dbapi2.connect``."""
    originals: list[object] = [f for f in (_real, dbapi2.connect) if f is not None]
    found: list[str] = []
    for name, module in list(sys.modules.items()):
        if name in _SKIPPED_MODULES or name == __name__ or name.startswith("sqlalchemy.") or name == "sqlalchemy":
            continue
        try:
            namespace = vars(module)
            found += [f"{name}.{attr}" for attr, value in list(namespace.items()) if any(value is o for o in originals)]
        except TypeError:  # an entry without a __dict__
            continue
    return found


def limitations() -> list[str]:
    lines: list[str] = []
    if _real is not None and (_preexisting > 0 or early_aliases()):
        lines.append(EARLY_CONNECTIONS)
    if _real is not None and _count_failed:
        lines.append(COUNT_FAILED)
    if _passed_through:
        lines.append(FACTORY_PASSED_THROUGH)
    return lines
