from __future__ import annotations

from sharpit.engine.panels import PANELS

PANEL_IDS = {
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


def test_0_4_panels_are_registered_but_unimplemented() -> None:
    panels = {panel.id: panel for panel in PANELS if panel.id in PANEL_IDS}

    assert set(panels) == PANEL_IDS
    assert all(not panel.implemented for panel in panels.values())
