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
Deviation: ``statements`` is always -1, BootUI's unknown (``ConnectionPayload.checkoutNanos`` uses it), where BootUI's
``ConnectionCheckout.statementExecuted`` counts per execute. Counting here cost every statement a fairy ``__dict__``
read and write (+1.5 us paired on the SQL listener, which has no room); the recorder keeps no per-connection count
(a bounded ring, pausable) to derive it from at checkin. Nothing in sharpit reads it: BootUI uses it only in
``RequestJournalProfiles`` display text. Upgrade if a profile view needs it: count at checkin, not per statement.
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

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

CHECKOUT_KEY = "sharpit_connection"
SOURCE = "connection"
UNKNOWN_STATEMENTS = -1  # BootUI's "unknown" for a ConnectionPayload number (``checkoutNanos``); see the module note


class Checkout:
    """One connection from checkout to release."""

    __slots__ = ("contexts", "epoch_ms", "obtained_ns", "pool", "request_id", "thread", "trace_id")

    def __init__(self, contexts: list[SharpitContext], pool: object, request: RequestInfo | None) -> None:
        self.contexts = [weakref.ref(c) for c in contexts]  # a leaked connection must not keep an install alive
        self.pool = pool
        self.request_id = None if request is None else request.id  # not the request: a record's info outlives it
        self.epoch_ms = time.time_ns() // 1_000_000
        self.thread = threading.current_thread().name
        self.trace_id = otel.current_trace_id()
        self.obtained_ns = time.perf_counter_ns()  # last, so the clock starts after the bookkeeping above


def checkout(dbapi_connection: Any, record: Any, proxy: Any) -> None:
    """Start following the connection just obtained, when a journal that records the source will take it."""
    del dbapi_connection
    try:
        record.info.pop(CHECKOUT_KEY, None)  # a state left by a checkout whose checkin listener was gone is not ours
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
        if state is None or dbapi_connection is None:
            return  # an invalidated record: includes a checkout that failed after our listener, never the app's
        held = max(0, time.perf_counter_ns() - state.obtained_ns)
        for ref in state.contexts:
            ctx = ref()
            if ctx is not None:
                _offer(ctx, state, held)
    except Exception as exc:  # noqa: BLE001 - a listener never changes the host's release
        dispatch.routing_failed(exc)


def _offer(ctx: SharpitContext, state: Checkout, held: int) -> None:
    journal = ctx.capture.journal
    recorder = ctx.capture.sql_trace
    if journal is None or recorder is None:
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
                "statements": UNKNOWN_STATEMENTS,
                "checkoutNanos": state.obtained_ns,
            },
            started=state.epoch_ms if state.request_id is not None or state.trace_id is not None else 0,
        )
    except Exception as exc:  # noqa: BLE001
        dispatch._context_failed(ctx, exc, "connection journal")
