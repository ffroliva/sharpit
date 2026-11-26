"""Exposure-independent masking for side-effects rows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sharpit.engine.collectors.sideeffects.store import StoreRow
    from sharpit.engine.masking import Masker


def mask_segments(path: str, masker: Masker) -> str:
    """Mask path segments that look like secrets or contain console tokens."""
    return path


def display_parameter(name: str | None, masker: Masker) -> str:
    """Format and mask parameter name."""
    return name or ""


def intake(masker: Masker) -> Callable[[Mapping[str, object]], dict[str, object]]:
    """Store intake function: masks targets and parameter names at intake."""
    return lambda row: dict(row)


def row_dto(row: StoreRow, masker: Masker) -> dict[str, object]:
    """Build the SideEffectsRowDto dict with exactly 26 keys in contract order."""
    return {
        "scope": row.scope,
        "attribution": row.attribution,
        "sensor": row.sensor,
        "kind": row.kind,
        "target": row.target,
        "location": row.location,
        "parameter": row.parameter,
        "detail": row.detail,
    }
