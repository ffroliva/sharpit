"""W5a P-connection: one ``connection`` journal event per logical connection the application releases.

BootUI ``SqlTraceRecorder.checkoutConnection`` / ``releaseConnection`` and ``ConnectionPayload`` on SQLAlchemy's pool
events: ``checkout`` starts following the connection, ``checkin`` (the application gave it back) offers the event.

Deviations from BootUI: ``waitNanos`` is always 0, which BootUI's readers take as "no wait" (``RouteTimeBreakdown``
and ``JournalAggregates`` add it up): the ``checkout`` event fires after the pool handed the connection over and no
event marks when the request for it began, so a wait is never invented. The event is offered with the correlation
current at checkout, on whichever thread releases it, as BootUI's ``ConnectionCheckout`` does.
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


class Checkout:
    """One connection from checkout to release; ``statements`` is bumped by the statement listener (see listeners)."""

    __slots__ = ("contexts", "epoch_ms", "obtained_ns", "pool", "request", "statements", "thread", "trace_id")

    def __init__(self, contexts: list[SharpitContext], pool: object, request: RequestInfo | None) -> None:
        self.contexts = [weakref.ref(c) for c in contexts]  # a leaked connection must not keep an install alive
        self.pool = pool
        self.request = request
        self.epoch_ms = time.time_ns() // 1_000_000
        self.thread = threading.current_thread().name
        self.trace_id = otel.current_trace_id()
        self.statements = 0
        self.obtained_ns = time.perf_counter_ns()  # last, so the clock starts after the bookkeeping above


def checkout(dbapi_connection: Any, record: Any, proxy: Any) -> None:
    """Start following the connection just obtained, when a journal that records the source will take it."""
    del dbapi_connection
    try:
        if INTERNAL.get():
            return
        pool = getattr(proxy, "_pool", None)
        targets = dispatch.connection_targets(pool)
        accepting = [c for c in targets if c.capture.journal is not None and c.capture.journal.accepts(SOURCE)]
        if accepting:  # a source the journal does not record follows nothing and counts nothing, as BootUI's
            record.info[CHECKOUT_KEY] = Checkout(accepting, pool, REQUEST.get())
    except Exception as exc:  # noqa: BLE001 - a listener never changes the host's checkout
        dispatch.routing_failed(exc)


def checkin(dbapi_connection: Any, record: Any) -> None:
    """The application released the connection: offer its event once (a second checkin finds no state)."""
    del dbapi_connection
    try:
        state: Checkout | None = record.info.pop(CHECKOUT_KEY, None)
        if state is None:
            return
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
        request = state.request
        journal.offer_flat(
            {
                "source": SOURCE,
                "epochMillis": state.epoch_ms,
                "durationNanos": held,
                "traceId": state.trace_id,
                "thread": state.thread,
                "requestId": None
                if request is None
                else request.id,  # checkout routed to its own request's context only
                "failedOrSlow": recorder.slow_held(held),
                "dataSource": registry.name_of_pool(state.pool) if registry is not None else None,
                "waitNanos": 0,
                "statements": state.statements,
                "checkoutNanos": state.obtained_ns,
            }
        )
    except Exception as exc:  # noqa: BLE001
        dispatch._context_failed(ctx, exc, "connection journal")
