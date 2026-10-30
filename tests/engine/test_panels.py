from sharpit.engine.panels import PANELS, panel_for_api_path, panels_report

RO = "sharpit is read-only via SHARPIT_READ_ONLY=true"


def test_registry_order_titles_and_action_capability():
    assert [(p.id, p.title, p.action_capable, p.api_prefix) for p in PANELS] == [
        ("overview", "Overview", None, None),
        ("config", "Configuration", False, "/config"),
        ("mappings", "Mappings", False, "/mappings"),
        ("loggers", "Loggers", True, "/loggers"),
        ("beans", "Beans", False, "/beans"),
        ("vulnerabilities", "Vulnerabilities", True, "/vulnerabilities"),
        ("mcp-server", "MCP Server", True, "/mcp-server"),
        ("cli", "CLI", None, None),
    ]


def _by_id(report):
    return {p["id"]: p for p in report["panels"]}


def test_read_only_only_for_action_capable():
    report = panels_report(True, {}, {})
    assert report["platform"] == "fastapi"
    panels = _by_id(report)
    assert panels["overview"]["readOnly"] is False
    assert panels["config"]["readOnly"] is False
    assert panels["config"]["readOnlyReason"] is None
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
