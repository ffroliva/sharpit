"""BootUI 2.2.0 golden loader (stub: wrong value, pinned by tests/test_golden.py)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent / "fixtures" / "bootui" / "2.2.0"


class UnverifiedParityWarning(UserWarning):
    """A payload was checked against a provisional fixture: it merges, but counts as unverified, not parity."""


def bootui_ids() -> dict[str, str]:
    return json.loads((ROOT / "ids.json").read_text(encoding="utf-8"))


def assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None:
    return None
