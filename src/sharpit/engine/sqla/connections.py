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
checkin instead, exact or -1 (unknown; BootUI defines -1 as unknown only for ``checkoutNanos``). It comes only from the
SQL Trace rows recorded since the checkout, which carry the connection, while the ring still holds them all. A count is
-1 when there is no SQL Trace recorder, when the rows left the ring, or when the panel was paused (BootUI keeps
counting then): the journal's ``sql`` events carry no connection, so they never stand in for the rows.
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


class Checkout:
    """One connection from checkout to release."""

    __slots__ = ("contexts", "cursors", "epoch_ms", "obtained_ns", "pool", "request_id", "thread", "trace_id")

    def __init__(self, contexts: list[SharpitContext], pool: object, request: RequestInfo | None) -> None:
        self.contexts = [weakref.ref(c) for c in contexts]  # a leaked connection must not keep an install alive
        self.cursors = _cursors(contexts)
        self.pool = pool
        self.request_id = None if request is None else request.id  # not the request: a record's info outlives it
        self.epoch_ms = time.time_ns() // 1_000_000
        self.thread = threading.current_thread().name
        self.trace_id = otel.current_trace_id()
        self.obtained_ns = time.perf_counter_ns()  # last, so the clock starts after the bookkeeping above


def _cursors(targets: list[SharpitContext]) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for ctx in targets:
        journal = ctx.capture.journal
        recorder = ctx.capture.sql_trace
        if journal is not None and recorder is not None and journal.accepts(SOURCE):
            out[ctx.context_id] = (recorder.checkout_cursor(), journal.sql_cursor())
    return out


def _count_statements(ctx: SharpitContext, state: Checkout, connection_id: str | None) -> int:
    cursor = state.cursors.get(ctx.context_id)
    recorder = ctx.capture.sql_trace
    journal = ctx.capture.journal
    if cursor is None or recorder is None or journal is None:
        return UNKNOWN_STATEMENTS
    start_total, start_sql_accepted = cursor
    # fewer rows than journal ``sql`` events since the checkout: the panel was paused, so the rows would undercount
    if journal.accepts("sql") and journal.sql_cursor() - start_sql_accepted != recorder.checkout_cursor() - start_total:
        return UNKNOWN_STATEMENTS
    count = recorder.count_for_connection(connection_id, start_total)
    return UNKNOWN_STATEMENTS if count is None else count


def checkout(dbapi_connection: Any, record: Any, proxy: Any) -> None:
    """Start following the connection just obtained, when a journal that records the source will take it."""
    del dbapi_connection
    try:
        record.info.pop(CHECKOUT_KEY, None)  # left by a checkout whose checkin listener was gone: not ours
        if INTERNAL.get():
            return
        pool = getattr(proxy, "_pool", None)
        targets = dispatch.connection_targets(pool, SOURCE)
        if targets:  # a source the journal does not record follows nothing and counts nothing, as BootUI's
            record.info[CHECKOUT_KEY] = Checkout(targets, pool, REQUEST.get())
    except Exception as exc:  # noqa: BLE001 - a listener never changes the host's checkout
        dispatch.routing_failed(exc)


def checkin(dbapi_connection: Any, record: Any) -> None:
    """The application released the connection: offer its event once (a second checkin finds no state)."""
    try:
        state: Checkout | None = record.info.pop(CHECKOUT_KEY, None)
        if state is None:
            return
        if dbapi_connection is None:
            return  # an invalidated record: includes a checkout that failed after our listener, never the app's
        held = max(0, time.perf_counter_ns() - state.obtained_ns)
        connection_id = hex(id(dbapi_connection))
        for ref in state.contexts:
            ctx = ref()
            if ctx is not None:
                _offer(ctx, state, held, connection_id)
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
