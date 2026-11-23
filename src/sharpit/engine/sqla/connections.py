"""W5a P-connection: one ``connection`` journal event per logical connection the application releases.

BootUI ``SqlTraceRecorder.checkoutConnection`` / ``releaseConnection`` and ``ConnectionPayload`` on SQLAlchemy's pool
events: ``checkout`` starts following the connection, ``checkin`` (the application gave it back) offers the event.

Deviations from BootUI: ``waitNanos`` is always 0, which BootUI's readers take as "no wait" (``RouteTimeBreakdown``
and ``JournalAggregates`` add it up): the ``checkout`` event fires after the pool handed the connection over and no
event marks when the request for it began, so a wait is never invented. The event is offered with the correlation
current at checkout, on whichever thread releases it, as BootUI's ``ConnectionCheckout`` does.

shortcut: the state sits in one slot of the pool record's ``info``. A pool that hands one record to several concurrent
checkouts (StaticPool, SingletonThreadPool: sqlite in memory) therefore journals one event for the overlapping
checkouts, the last one's; upgrade to a state keyed per fairy if such a pool needs one event per checkout.
Deviation: BootUI's ``ConnectionCheckout.statementExecuted`` counts ``statements`` per execute; counting per statement
here would cost the SQL listener a fairy ``__dict__`` read and write (+1.5 us paired), so the count is derived at
checkin instead, exact or -1 (unknown; BootUI defines -1 as unknown only for ``checkoutNanos``). It comes from the SQL
Trace rows recorded since the checkout, which carry the connection, while the ring still holds them all; else from the
journal's ``sql`` events since the checkout, which carry no connection, so only when every one is this checkout's
request and thread, no other followed checkout on that request and thread overlapped it, and no raw sqlite3 statement
reaches the install. A count is -1 when the panel was paused and the journal records no ``sql``, when the rows or
events left their ring, or when the journal cannot tell this connection's statements from another's.
shortcut: with no ``sql`` journal source the SQL Trace count is not cross-checked, so a panel paused for part of
a checkout undercounts it; upgrade with a pause generation on the recorder if that case needs to be exact.
shortcut: a connection that is invalidated before its release (``checkin`` then gets no DBAPI connection) offers no
event, since a checkout that failed after our listener looks the same; upgrade with a per-checkout flag.
shortcut: a connection detached from the pool (``Connection.detach()``) never fires ``checkin``, so it offers no
event; a state left by a listener gap is popped only at the next checkout made while the listener is on. Upgrade if a
re-armed listener (``suspend_hook`` then resume) must not misattribute a release.
"""

# pyright: reportPrivateUsage=false
# the pool's fairy keeps its pool in ``_pool``; the record's ``info`` dict is SQLAlchemy's per-connection scratch

from __future__ import annotations

import threading
import time
import weakref
from typing import TYPE_CHECKING, Any

from sharpit.engine import otel
from sharpit.engine.capture.correlation import INTERNAL, REQUEST, RequestInfo
from sharpit.engine.sources import dispatch  # the module, not its names: dispatch imports this package
from sharpit.engine.sqla import listeners as _listeners  # the module: listeners imports this one

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

CHECKOUT_KEY = "sharpit_connection"
SOURCE = "connection"
UNKNOWN_STATEMENTS = -1  # an unknown count; BootUI defines -1 only for ``checkoutNanos``: see the module note
RAW_SQLITE3 = "sqlite3"  # the raw sqlite3 SQL source, as ``dispatch`` names it: no pool checkout follows it
# per (request id, thread): [followed checkouts not yet released, checkouts started while one was]; how the journal
# count learns of a neighbour. shortcut: a detached connection (never checked in) keeps its key open, so that key's
# journal counts stay unknown; upgrade if a detaching application needs them
_open: dict[tuple[str | None, str], list[int]] = {}
_open_lock = threading.Lock()


class Checkout:
    """One connection from checkout to release."""

    __slots__ = (
        "contexts", "cursors", "epoch_ms", "followed", "obtained_ns", "pool", "request_id", "thread", "trace_id",
    )  # fmt: skip

    def __init__(self, contexts: list[SharpitContext], pool: object, request: RequestInfo | None) -> None:
        self.contexts = [weakref.ref(c) for c in contexts]  # a leaked connection must not keep an install alive
        self.cursors = _cursors(contexts)
        self.pool = pool
        self.request_id = None if request is None else request.id  # not the request: a record's info outlives it
        self.epoch_ms = time.time_ns() // 1_000_000
        self.thread = threading.current_thread().name
        self.trace_id = otel.current_trace_id()
        self.followed: tuple[int, int] = (0, 0)  # its key's open and started counts at this checkout, before it joined
        self.obtained_ns = time.perf_counter_ns()  # last, so the clock starts after the bookkeeping above


def _cursors(targets: list[SharpitContext]) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for ctx in targets:
        journal = ctx.capture.journal
        recorder = ctx.capture.sql_trace
        if journal is not None and recorder is not None and journal.accepts(SOURCE):
            out[ctx.context_id] = (recorder.checkout_cursor(), journal.sql_cursor())
    return out


def _follow(state: Checkout) -> None:
    with _open_lock:
        counts = _open.setdefault((state.request_id, state.thread), [0, 0])
        state.followed = (counts[0], counts[1])
        counts[0] += 1
        counts[1] += 1


def _shared(state: Checkout) -> bool:
    """Whether another checkout on ``state``'s request and thread was open at its checkout or started since; read
    while ``state`` is still followed, so its key is present."""
    with _open_lock:
        counts = _open.get((state.request_id, state.thread))
        open_before, started_before = state.followed
        return counts is None or open_before > 0 or counts[1] != started_before + 1


def _unfollow(state: Checkout) -> None:
    key = (state.request_id, state.thread)
    with _open_lock:
        counts = _open.get(key)
        if counts is not None:
            counts[0] -= 1
            if counts[0] <= 0:  # nothing open on this key: the next checkout starts a new count
                del _open[key]


def _count_statements(ctx: SharpitContext, state: Checkout, connection_id: str | None) -> int:
    cursor = state.cursors.get(ctx.context_id)
    if cursor is None:
        return UNKNOWN_STATEMENTS
    start_total, start_sql_accepted = cursor
    recorder = ctx.capture.sql_trace
    journal = ctx.capture.journal
    if recorder is None or journal is None:
        return UNKNOWN_STATEMENTS
    sql_delta = journal.sql_cursor() - start_sql_accepted
    recorder_delta = recorder.checkout_cursor() - start_total
    if not journal.accepts("sql") or sql_delta == recorder_delta:
        count = recorder.count_for_connection(connection_id, start_total)
        if count is not None:
            return count
    count = journal.count_sql_since(state.obtained_ns, state.request_id, state.thread, start_sql_accepted)
    # journal events carry no connection, so another's statements look like ours; checked after the count, so a
    # neighbour that checked out before the walk is seen
    if count is None or (count > 0 and (_shared(state) or RAW_SQLITE3 in ctx.capture.sql_delivered)):
        return UNKNOWN_STATEMENTS
    return count


def checkout(dbapi_connection: Any, record: Any, proxy: Any) -> None:
    """Start following the connection just obtained, when a journal that records the source will take it."""
    del dbapi_connection
    try:
        stale = record.info.pop(CHECKOUT_KEY, None)  # left by a checkout whose checkin listener was gone: not ours
        if stale is not None:
            _unfollow(stale)
        if INTERNAL.get():
            return
        pool = getattr(proxy, "_pool", None)
        targets = dispatch.connection_targets(pool, SOURCE)
        if targets:  # a source the journal does not record follows nothing and counts nothing, as BootUI's
            state = Checkout(targets, pool, REQUEST.get())
            _follow(state)
            record.info[CHECKOUT_KEY] = state
    except Exception as exc:  # noqa: BLE001 - a listener never changes the host's checkout
        dispatch.routing_failed(exc)


def checkin(dbapi_connection: Any, record: Any) -> None:
    """The application released the connection: offer its event once (a second checkin finds no state)."""
    try:
        state: Checkout | None = record.info.pop(CHECKOUT_KEY, None)
        if state is None:
            return
        try:
            if dbapi_connection is None:
                return  # an invalidated record: includes a checkout that failed after our listener, never the app's
            held = max(0, time.perf_counter_ns() - state.obtained_ns)
            connection_id = hex(id(dbapi_connection))
            for ref in state.contexts:
                ctx = ref()
                if ctx is not None:
                    _offer(ctx, state, held, connection_id)
        finally:
            _unfollow(state)  # after the counts: a checkout made while they ran is a neighbour
    except Exception as exc:  # noqa: BLE001 - a listener never changes the host's release
        dispatch.routing_failed(exc)


def _offer(ctx: SharpitContext, state: Checkout, held: int, connection_id: str) -> None:
    journal = ctx.capture.journal
    recorder = ctx.capture.sql_trace
    # another install keeps the shared listeners attached: a suspended or uninstalled capture still takes nothing
    if journal is None or recorder is None or not _listeners.routes_statements(ctx):
        return
    try:  # the event is built inside the guard: a failure loses this event, never the host's release
        registry = ctx.capture.engine_registry
        journal.offer_flat(
            {
                "source": SOURCE,
                "epochMillis": state.epoch_ms,
                "durationNanos": held,
                "traceId": state.trace_id,
                "thread": state.thread,
                "requestId": state.request_id,  # checkout routed to its own request's context only
                "failedOrSlow": recorder.slow_held(held),
                "dataSource": registry.name_of_pool(state.pool) if registry is not None else None,
                "waitNanos": 0,
                "statements": _count_statements(ctx, state, connection_id),
                "checkoutNanos": state.obtained_ns,
            },
            started=state.epoch_ms if state.request_id is not None or state.trace_id is not None else 0,
        )
    except Exception as exc:  # noqa: BLE001
        dispatch._context_failed(ctx, exc, "connection journal")
