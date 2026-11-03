"""The ``mysql`` panel's report service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext


def mysql_report(_ctx: SharpitContext) -> dict[str, Any]:
    """The last read or the initial ``NOT_READ`` report."""
    return {}
