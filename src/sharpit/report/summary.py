"""Render a ``sharpit-report/1`` mapping as escaped Markdown (pure: no environment, no network)."""

from __future__ import annotations

from collections.abc import Mapping


def render_summary(report: Mapping[str, object]) -> str:
    return ""
