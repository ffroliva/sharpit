"""Ratchet: pinned counts a lane raises when it closes a row.

Lowering a pin needs its reason in the PR body (no direction check is possible without history).
"""

from __future__ import annotations

import json
from pathlib import Path

PARITY = Path(__file__).parent
ROUTES_MATCHED_PIN = 5  # routes still measure the BootUI 2.3.0 live goldens until the live capture lands
PROPERTIES_MATCHED_PIN = 103


def test_matched_routes_ratchet() -> None:
    """Pinned count a lane raises when it closes a row; lowering a pin needs its reason in the PR body."""
    counts = json.loads((PARITY / "routes_status.json").read_text("utf-8"))["counts"]
    assert counts["matched"] == ROUTES_MATCHED_PIN


def test_matched_properties_ratchet() -> None:
    """Pinned count a lane raises when it closes a row; lowering a pin needs its reason in the PR body."""
    rows = json.loads((PARITY / "properties_status.json").read_text("utf-8"))["properties"]
    assert sum(row["status"] == "matched" for row in rows) == PROPERTIES_MATCHED_PIN
