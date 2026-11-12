"""Connection events (begin, commit, rollback, savepoints) other lanes listen to through one slot."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from sharpit.engine import sqla as _sqla
from sharpit.engine.sqla import _lock  # pyright: ignore[reportPrivateUsage] - one lock for the whole package

ConnectionEvent = Literal[
    "begin", "commit", "rollback", "savepoint", "rollback_savepoint", "release_savepoint", "handle_error",
    "before_cursor_execute",
]  # fmt: skip
CONNECTION_EVENTS: tuple[ConnectionEvent, ...] = (
    "begin",
    "commit",
    "rollback",
    "savepoint",
    "rollback_savepoint",
    "release_savepoint",
    "handle_error",
    "before_cursor_execute",  # the transactions panel's write counter
)  # add_connection_listener's events (O1)


def add_connection_listener(event: ConnectionEvent, fn: Callable[..., None]) -> Callable[[], None] | None:
    """Listen to the class-level ``Engine`` connection event ``event`` (O1 slot); returns an idempotent remover.

    Inert until a lane calls it (the transactions panel registers here).
    Returns ``None`` while SQLAlchemy is not imported: call it from a ``CaptureState.attachers`` entry, which the
    wiring retries at startup and on the first request, as ``add`` is retried.
    """
    if event not in CONNECTION_EVENTS:
        raise ValueError(f"unknown connection event {event!r}")
    sa = _sqla.sqlalchemy_module()
    if sa is None:
        return None
    with _lock:
        sa.event.listen(sa.engine.Engine, event, fn)

    def remove() -> None:
        with _lock:
            if sa.event.contains(sa.engine.Engine, event, fn):
                sa.event.remove(sa.engine.Engine, event, fn)

    return remove


def add_pool_listener(event: Literal["checkin"], fn: Callable[..., None]) -> Callable[[], None] | None:
    """Listen to the class-level ``Pool`` event ``event``; returns an idempotent remover, ``None`` without SQLAlchemy.

    ``checkin`` is the transactions panel's post-commit point: SQLAlchemy has no event after the DBAPI commit returns.
    """
    sa = _sqla.sqlalchemy_module()
    if sa is None:
        return None
    with _lock:
        if not sa.event.contains(sa.pool.Pool, event, fn):
            sa.event.listen(sa.pool.Pool, event, fn)

    def remove() -> None:
        with _lock:
            if sa.event.contains(sa.pool.Pool, event, fn):
                sa.event.remove(sa.pool.Pool, event, fn)

    return remove
