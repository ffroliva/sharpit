"""Shared tool catalogue access for MCP and CLI adapters."""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.tools import Tool


def catalogue() -> Sequence[Tool]:
    return ()
