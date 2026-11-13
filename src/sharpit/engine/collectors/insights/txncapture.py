"""Whether this application's transactions are recorded at all (sharpit's own rule, owner ruling 2026-11-12).

BootUI 2.3.0 has no transaction capture state: with ``bootui.transactions.enabled=false`` its insights analyse an empty
transaction set silently. sharpit is stricter and mirrors ``SqlCapture`` (``RuntimeInsightsService.java:975-1008``): a
check that needs transactions is UNAVAILABLE, and an optional read carries a caveat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

DISABLED = "Transaction capture is disabled (SHARPIT_TRANSACTIONS_ENABLED=false), so no transaction is recorded."
NOT_RECORDED_SUFFIX = " Its transaction evidence is not counted."  # SqlCapture's suffix, for transactions
SOURCE = "transaction"


def reason_for(ctx: SharpitContext) -> str | None:
    """Why transactions are not recorded, ``None`` when they are: the flag ``install`` gates the recorder on
    (``fastapi/install.py``, with the panel). A disabled panel is not this question: the snapshot already names it
    (missing source first), so only the flag is reported here."""
    return None  # stub
