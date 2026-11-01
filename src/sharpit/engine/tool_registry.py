"""Shared tool catalogue access for MCP and CLI adapters."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sharpit.engine.tools import Tool


def catalogue() -> Sequence[Tool]:
    from sharpit.engine.tools import TOOLS

    return TOOLS
