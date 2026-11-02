"""Database connection pool reads remain local and side-effect free (D3)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from conftest import SideEffectGuard
from sharpit import install
from sharpit.engine.collectors.pools import pools_report

PANEL = "database-connection-pools"
GET_ROWS = [
    "/sharpit/api/database-connection-pools/pools",
    "/sharpit/api/database-connection-pools/pools/{name:path}/snapshot",
]
WRITE_ROWS: list[tuple[str, str]] = []


def test_d3_legacy_panel_is_not_added_as_a_panels04_lane():
    from safety import load

    assert load().invalid == ()


def test_pools_report_read_has_no_side_effects(no_side_effects: SideEffectGuard):
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir), engines=[]
    )
    try:
        no_side_effects.rebaseline()
        report: dict[str, Any] = pools_report(handle.context)
        assert report["total"] == 0
        assert no_side_effects.violations == []
    finally:
        handle.uninstall_capture()
