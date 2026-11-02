from __future__ import annotations

import pytest

from sharpit.engine.panels import PANELS
from sharpit.engine.panels04 import IMPLEMENTED

ALL_PANEL_IDS = {
    "data",
    "transactions",
    "postgresql",
    "mysql",
    "traces",
    "security",
    "security-logs",
    "database-advisor",
    "architecture",
    "sqlalchemy-statistics",
    "fastapi-security",
    "fastapi",
}
PANEL_IDS = {panel_id for panel_id, implemented in IMPLEMENTED.items() if not implemented}


def test_0_4_panels_are_registered_but_unimplemented() -> None:
    panels = {panel.id: panel for panel in PANELS if panel.id in PANEL_IDS}

    assert set(panels) == PANEL_IDS
    assert all(not panel.implemented for panel in panels.values())


def test_all_0_4_panel_ids_remain_registered() -> None:
    assert set(IMPLEMENTED) == ALL_PANEL_IDS
    assert ALL_PANEL_IDS.issubset({panel.id for panel in PANELS})


@pytest.mark.parametrize("implemented", [False, True], ids=["flag-false", "flag-true"])
def test_every_0_4_panel_is_registered_behind_its_flag(monkeypatch: pytest.MonkeyPatch, implemented: bool) -> None:
    # replaces test_0_4_panels_are_registered_but_unimplemented (it read PANEL_IDS, later derived from today's flags)
    for panel_id in ALL_PANEL_IDS:
        monkeypatch.setitem(IMPLEMENTED, panel_id, implemented)
    panels = {panel.id: panel for panel in PANELS if panel.id in ALL_PANEL_IDS}

    assert set(panels) == ALL_PANEL_IDS
    assert {panel.implemented for panel in panels.values()} == {implemented}
