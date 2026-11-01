"""Session-level entry points for the pytest plugin."""

from __future__ import annotations

from typing import Any

from sharpit.pytest_plugin.options import PluginOptions, resolve


def resolve_options(config: Any) -> PluginOptions:
    return resolve(config)
