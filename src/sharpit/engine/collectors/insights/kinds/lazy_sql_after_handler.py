"""``lazy-sql-after-handler``: BootUI ``E/insights/LazySqlAfterHandler.java:45-72``. Statements run after the handler
returned, while the response was written, outside every transaction.

Deviation (proposed): BootUI places a statement by the ``phase`` its filter stamps on the sql event
(``RequestPhase.RESPONSE``). sharpit's sql event carries ``phase: None`` and the http event carries no handler-end
time (``startNanos`` and ``durationNanos`` only), so a statement cannot be told from the handler's own. The kind answers
not applicable with a fixed reason, whatever was recorded, and evaluates nothing: BootUI's own reasons
(WebFlux, Quarkus) do not describe sharpit. A handler-end mark would come from the FastAPI adapter; this lane
adds none.
"""

from sharpit.engine.collectors.insights.snapshot import Snapshot

KIND = "lazy-sql-after-handler"
TITLE = "SQL after the handler returned"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = True

NOT_APPLICABLE = (
    "sharpit marks no end of the handler on a request, so a statement that ran while the response was written cannot "
    "be told from the handler's own."
)


def not_applicable(snapshot: Snapshot) -> str:
    """Always: the data this kind needs, a handler end, is not produced."""
    del snapshot  # the reason does not depend on what was recorded
    return NOT_APPLICABLE
