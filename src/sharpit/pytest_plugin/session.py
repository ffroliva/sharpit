"""Session-level entry points for the pytest plugin."""

from __future__ import annotations

from typing import Any

from sharpit.pytest_plugin.options import PluginOptions


def resolve_options(config: Any) -> PluginOptions:
    return PluginOptions(False, None, None, 0, "MEDIUM", False, None, False, 0)
