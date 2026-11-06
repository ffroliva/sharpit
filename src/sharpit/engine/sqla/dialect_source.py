"""Dialect evidence available on SQLAlchemy events and their exception chains."""

from __future__ import annotations

from collections.abc import Callable

from sharpit.engine.sqltext import Dialect, DialectContext, dialect_of_name, read_chain, resolve

_UNREADABLE = object()


def _attribute(value: object, name: str) -> object | None:
    """``None`` for an absent attribute; ``_UNREADABLE`` for one that raised, and for anything read from that."""
    if value is _UNREADABLE:
        return value
    try:
        return object.__getattribute__(value, name)
    except AttributeError:
        return None
    except BaseException:
        return _UNREADABLE


def _candidate(candidate: object | None) -> Dialect | None:
    """``None`` proves nothing. A dialect that is there and cannot be named hides."""
    if candidate is None or type(candidate) is Dialect:
        return candidate
    name = _attribute(candidate, "name")
    return dialect_of_name(name) if type(name) is str else Dialect.UNSUPPORTED


def engine_dialect(holder: object) -> Dialect | None:
    """``holder.dialect``, an engine's or a connection's, read at every call with no cache and no lock.

    It is a plain attribute there, and it can be replaced.
    """
    return _candidate(_attribute(holder, "dialect"))


class EngineDialectSource:
    def dialect_of(self, event: object, context: DialectContext) -> Dialect | None:
        del context
        candidates = [_candidate(_attribute(event, "dialect"))]
        execution = _attribute(event, "context")
        if execution is not None:
            candidates.append(_candidate(_attribute(execution, "dialect")))
        engine = _attribute(event, "engine")
        if engine is not None:
            candidates.append(engine_dialect(engine))
        proof: set[Dialect] = set()
        for candidate in candidates:
            if candidate is Dialect.UNSUPPORTED:
                return Dialect.UNSUPPORTED
            if candidate is not None:
                proof.add(candidate)
        if len(proof) > 1:
            return Dialect.UNSUPPORTED
        return next(iter(proof), None)


class ExceptionDialectSource:
    def dialect_of(self, event: object, context: DialectContext) -> Dialect | None:
        del context
        error = event if isinstance(event, BaseException) else _attribute(event, "error")
        if error is _UNREADABLE:
            return Dialect.UNSUPPORTED
        if not isinstance(error, BaseException):
            return None
        reading = read_chain(error)
        if reading.stopped or reading.exhausted or len(reading.families) > 1:
            return Dialect.UNSUPPORTED
        return next(iter(reading.families), None)


def exception_dialect(event: object, application: Callable[[], Dialect | None]) -> Dialect:
    return resolve(event, (ExceptionDialectSource(),), DialectContext(application))


_EVENT_SOURCES = (EngineDialectSource(),)
_ERROR_SOURCES = (*_EVENT_SOURCES, ExceptionDialectSource())


def event_dialect(event: object, application: Callable[[], Dialect | None]) -> Dialect:
    """Per statement. Agreement is decided in one place, ``EngineDialectSource``; with no error, no chain is walked."""
    sources = _EVENT_SOURCES if _attribute(event, "error") is None else _ERROR_SOURCES
    return resolve(event, sources, DialectContext(application))
