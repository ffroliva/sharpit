from conftest import SideEffectGuard
from sharpit.engine.panels import PANELS, panel_for_api_path, panels_report

RO = "sharpit is read-only via SHARPIT_READ_ONLY=true"


def test_registry_rows_0_2_0():
    # spec §13.1: MVP rows first, then the 0.2.0 rows; health is action-capable, threads and activity are not
    assert [(p.id, p.title, p.action_capable, p.api_prefix) for p in PANELS[:19]] == [
        ("overview", "Scorecard", None, None),
        ("config", "Configuration", True, "/config"),  # W8 A0: BootUiPanels.java:105
        ("mappings", "Mappings", False, "/mappings"),
        ("loggers", "Loggers", True, "/loggers"),
        ("beans", "Beans", False, "/beans"),
        ("vulnerabilities", "Vulnerabilities", True, "/vulnerabilities"),
        ("mcp-server", "MCP Server", True, "/mcp-server"),
        ("cli", "CLI", None, None),
        ("activity", "Live Activity", False, "/activity"),
        ("http-exchanges", "HTTP Exchanges", False, "/http-exchanges"),
        ("exceptions", "Exceptions", True, "/exceptions"),
        ("sql-trace", "SQL Trace", True, "/sql-trace"),
        ("log-tail", "Log Tail", False, "/log-tail"),
        ("alembic", "Alembic", True, "/alembic"),
        ("database-connection-pools", "Database Connection Pools", False, "/database-connection-pools"),
        ("health", "Health", True, "/health"),
        ("threads", "Threads", False, "/threads"),
        ("rest-api", "REST API", True, "/rest-api"),
        ("http-probe", "HTTP Probe", True, "/http-probe"),
    ]


def _by_id(report):
    return {p["id"]: p for p in report["panels"]}


def test_read_only_only_for_action_capable():
    report = panels_report(True, {}, {})
    assert report["platform"] == "fastapi"
    panels = _by_id(report)
    assert panels["overview"]["readOnly"] is False
    assert panels["mappings"]["readOnly"] is False
    assert panels["mappings"]["readOnlyReason"] is None
    assert panels["loggers"] == {
        "id": "loggers",
        "title": "Loggers",
        "available": True,
        "unavailableReason": None,
        "enabled": True,
        "readOnly": True,
        "readOnlyReason": RO,
    }


def test_panel_flags_and_reasons():
    report = panels_report(
        False,
        {"mcp-server": (True, True), "beans": (False, False)},
        {"beans": "no beans here"},
    )
    panels = _by_id(report)
    assert panels["mcp-server"]["readOnlyReason"] == "Panel is read-only via SHARPIT_PANELS_MCP_SERVER_READ_ONLY=true"
    assert panels["beans"]["enabled"] is False
    assert panels["beans"]["available"] is False
    assert panels["beans"]["unavailableReason"] == "no beans here"
    assert panels["loggers"]["readOnly"] is False


def test_panel_disabled_reason_string():
    from sharpit.engine.panels import disabled_reason

    assert disabled_reason("mcp-server") == "Panel is disabled via SHARPIT_PANELS_MCP_SERVER_ENABLED=false"


def test_mcp_not_under_mcp_server_prefix():
    assert panel_for_api_path("/mcp") is None
    assert panel_for_api_path("/mcp-server") is not None
    assert panel_for_api_path("/mcp-server/x").id == "mcp-server"  # type: ignore[union-attr]
    assert panel_for_api_path("/loggersX") is None
    assert panel_for_api_path("/overview") is None


def test_dismissed_rules_prefix_unchanged():
    # /dismissed-rules stays a global write subject, owned by no panel prefix (spec §8 changes that in Task 9)
    assert panel_for_api_path("/dismissed-rules") is None
    assert panel_for_api_path("/dismissed-rules/V-1") is None


# BootUI 2.2.0 BootUiPanels: the overview panel is titled "Scorecard" (drift contract §1.2)
def test_overview_panel_title_is_scorecard():
    titles = {panel["id"]: panel["title"] for panel in panels_report(True, {}, {})["panels"]}
    assert titles["overview"] == "Scorecard"


def test_w5b_wave1_panel_rows_match_bootui(no_side_effects: SideEffectGuard):
    from fastapi.testclient import TestClient

    from fastapi import FastAPI
    from sharpit import install

    expected = {
        "metrics": ("Metrics", False, "/metrics"),
        "startup": ("Startup Timeline", False, "/startup"),
        "profile-diff": ("Profile Diff", False, "/profile-diff"),
        "scheduled": ("Scheduled Tasks", False, "/scheduled"),
    }
    assert {
        panel.id: (panel.title, panel.action_capable, panel.api_prefix) for panel in PANELS if panel.id in expected
    } == expected

    app = FastAPI()
    install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        no_side_effects.block_network()
        listed = {panel["id"] for panel in client.get("/sharpit/api/panels").json()["panels"]}
    assert listed.isdisjoint(expected.keys() - {"startup", "profile-diff"})
    assert "startup" in listed
    assert "profile-diff" in listed
    assert no_side_effects.violations == []


def test_w7_wave1_panel_rows_match_bootui(no_side_effects: SideEffectGuard):
    from fastapi.testclient import TestClient

    from fastapi import FastAPI
    from sharpit import install

    expected = {
        "copilot": ("Copilot", False, "/copilot"),
        "claude-code": ("Claude Code", False, "/claude-code"),
        "github": ("GitHub", True, "/github"),
        "ai": ("AI Framework", False, "/ai"),
    }
    assert {
        panel.id: (panel.title, panel.action_capable, panel.api_prefix) for panel in PANELS if panel.id in expected
    } == expected

    app = FastAPI()
    install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        no_side_effects.block_network()
        listed = {panel["id"] for panel in client.get("/sharpit/api/panels").json()["panels"]}
    assert listed.isdisjoint(expected.keys() - {"copilot", "claude-code", "ai"})
    assert "copilot" in listed
    assert "claude-code" in listed
    assert "ai" in listed  # W7 A implements the AI Framework panel
    assert no_side_effects.violations == []


def test_w6_sensor_panel_rows_match_bootui(no_side_effects: SideEffectGuard):
    from fastapi.testclient import TestClient

    from fastapi import FastAPI
    from sharpit import install

    expected = {
        "java-agent": ("Java Agent", True, "/java-agent"),
        "code-inventory": ("Code Inventory", False, "/code-inventory"),
        "code-paths": ("Code Paths", True, "/code-paths"),
        "side-effects": ("Side Effects", False, "/side-effects"),
    }
    assert {
        panel.id: (panel.title, panel.action_capable, panel.api_prefix) for panel in PANELS if panel.id in expected
    } == expected

    app = FastAPI()
    install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        no_side_effects.block_network()
        listed = {panel["id"] for panel in client.get("/sharpit/api/panels").json()["panels"]}
    assert set(expected) <= listed
    assert no_side_effects.violations == []


def test_live_memory_panel_owns_low_footprint_controls():
    assert "live-memory" in {p.id for p in PANELS}
    panel = next(p for p in PANELS if p.id == "live-memory")
    assert panel.title == "Live Memory"
    assert panel.action_capable is True
    assert panel.api_prefix == "/live-memory"
    assert panel.implemented is True


# W8 A0: BootUiPanels.java:105,124,133,136 declares config, cache, dev-services and flyway action-capable; sharpit's
# alembic is BootUI's flyway (matrix :143). Without the flag the read-only gate never refuses their W8 actions.
W8_ACTION_PANELS = {"config": "config", "alembic": "flyway", "cache": "cache", "dev-services": "dev-services"}


def test_write_action_panels_are_action_capable():
    import json
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "bootui" / "2.3.0" / "panels.json"
    bootui = {p["id"]: p["actionCapable"] for p in json.loads(fixture.read_text(encoding="utf-8"))["panels"]}
    ours = {p.id: p.action_capable for p in PANELS}
    for sharpit_id, bootui_id in W8_ACTION_PANELS.items():
        assert bootui[bootui_id] is True, bootui_id
        assert ours.get(sharpit_id) is True, sharpit_id


def test_w8_slots_registered_unimplemented_with_bootui_rows():
    # cache (W5b K) and dev-services (W7 D) own the read side; A0 only reserves the slots behind their flags
    expected = {"cache": ("Cache", True, "/cache"), "dev-services": ("Dev Services", True, "/dev-services")}
    rows = {p.id: (p.title, p.action_capable, p.api_prefix) for p in PANELS if p.id in expected}
    assert rows == expected
    implemented = {p.id: p.implemented for p in PANELS if p.id in expected}
    assert implemented == {"cache": False, "dev-services": False}


def test_config_read_only_reported_under_global_read_only():
    config = _by_id(panels_report(True, {}, {}))["config"]
    assert config["readOnly"] is True
    assert config["readOnlyReason"] == RO
