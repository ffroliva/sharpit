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


def _agreed(proof: Dialect | None, other: Dialect | None) -> Dialect | None:
    if proof is None:
        return other
    return proof if other is None or other is proof else Dialect.UNSUPPORTED


def _event_proof(event: object) -> Dialect | None:
    """The connection, its execution context and its engine: three holders, each read once, that must agree."""
    proof = _candidate(_attribute(event, "dialect"))
    execution = _attribute(event, "context")
    if execution is not None:
        proof = _agreed(proof, _candidate(_attribute(execution, "dialect")))
    engine = _attribute(event, "engine")
    return proof if engine is None else _agreed(proof, engine_dialect(engine))


class EngineDialectSource:
    def dialect_of(self, event: object, context: DialectContext) -> Dialect | None:
        del context
        return _event_proof(event)


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


_ERROR_SOURCES = (EngineDialectSource(), ExceptionDialectSource())


def event_dialect(event: object, application: Callable[[], Dialect | None]) -> Dialect:
    """Per statement. With no error the event answers alone: no chain is walked and the application's engines are not
    read, unless the event proves nothing. A failure is rare, so it pays for the chain and for step 2."""
    if _attribute(event, "error") is not None:
        return resolve(event, _ERROR_SOURCES, DialectContext(application))
    proof = _event_proof(event)
    return proof if proof is not None else resolve(event, (), DialectContext(application))
