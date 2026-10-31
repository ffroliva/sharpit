from sharpit.engine.panels import PANELS, panel_for_api_path, panels_report

RO = "sharpit is read-only via SHARPIT_READ_ONLY=true"


def test_registry_rows_0_2_0():
    # spec §13.1: MVP rows first, then the 0.2.0 rows; health is action-capable, threads and activity are not
    assert [(p.id, p.title, p.action_capable, p.api_prefix) for p in PANELS] == [
        ("overview", "Overview", None, None),
        ("config", "Configuration", False, "/config"),
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


def test_dismissed_rules_prefix_unchanged():
    # /dismissed-rules stays a global write subject, owned by no panel prefix (spec §8 changes that in Task 9)
    assert panel_for_api_path("/dismissed-rules") is None
    assert panel_for_api_path("/dismissed-rules/V-1") is None
