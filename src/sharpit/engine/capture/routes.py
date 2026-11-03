"""HTTP route summary (BootUI 2.2.0 ``HttpRouteSummaryService``): ``GET /http-exchanges/routes`` over the ring."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from sharpit.engine.capture.exchanges import HttpExchangeBuffer

DEFAULT_TOP_PER_CRITERION: Final[int] = 25
MAX_TOP_PER_CRITERION: Final[int] = 100


def summarize_http_routes(
    exchanges: HttpExchangeBuffer | None, *, limit: int | None = None, route: str | None = None
) -> dict[str, Any]:
    """``HttpRoutesReport``."""
    return {"routes": []}
