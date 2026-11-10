import json
from pathlib import Path

import pytest
from tests.fastapi.test_cli_api import _client

from sharpit.engine.tools import TOOLS

ROOT = Path(__file__).parents[1]
BOOTUI = {
    tool["name"]: tool for tool in json.loads((ROOT / "fixtures/bootui/2.3.0/tools.json").read_text("utf-8"))["tools"]
}
SHARPIT = {tool.name: tool for tool in TOOLS}


def _schema_shape(schema: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    return ({name: value.get("type") for name, value in properties.items()}, schema.get("required", []))


MATCHED_TOOLS = (
    "get_architecture_report",
    "architecture_scan",
    "get_architecture_rule_violations",
    "mysql_read",
    "get_mysql_report",
    "get_database_connection_pools",
    "postgresql_read",
    "get_postgresql_report",
    "get_database_advisor_report",
    "database_advisor_scan",
    "get_database_advisor_rule_violations",
    "clear_exceptions",
    "get_exceptions",
    "get_exception_detail",
    "get_health",
    "get_http_routes",
    "get_loggers",
    "get_mappings",
    "get_overview",
    "get_request_profile",
    "get_rest_api_report",
    "rest_api_scan",
    "get_rest_api_rule_violations",
    "get_security_logs",
    "get_security_report",
    "security_scan",
    "get_security_rule_violations",
    "clear_sql_traces",
    "pause_sql_trace_recording",
    "resume_sql_trace_recording",
    "clear_traces",
    "get_traces",
    "clear_transactions",
    "get_transactions",
    "pause_transaction_recording",
    "resume_transaction_recording",
    "get_vulnerabilities_report",
    "vulnerabilities_scan",
)
MATCHED_CLI = (
    ("architecture/report", "get_architecture_report"),
    ("architecture/scan", "architecture_scan"),
    ("architecture/violations", "get_architecture_rule_violations"),
    ("beans", "get_beans"),
    ("config", "get_config"),
    ("db/mysql/read", "mysql_read"),
    ("db/mysql/report", "get_mysql_report"),
    ("db/pools", "get_database_connection_pools"),
    ("db/postgres/read", "postgresql_read"),
    ("db/postgres/report", "get_postgresql_report"),
    ("db/report", "get_database_advisor_report"),
    ("db/scan", "database_advisor_scan"),
    ("db/violations", "get_database_advisor_rule_violations"),
    ("exceptions/clear", "clear_exceptions"),
    ("exceptions/list", "get_exceptions"),
    ("exceptions/show", "get_exception_detail"),
    ("health", "get_health"),
    ("http/exchanges", "get_http_exchanges"),
    ("http/routes", "get_http_routes"),
    ("loggers", "get_loggers"),
    ("logs/tail", "get_log_tail"),
    ("mappings", "get_mappings"),
    ("overview", "get_overview"),
    ("rest-api/report", "get_rest_api_report"),
    ("rest-api/scan", "rest_api_scan"),
    ("rest-api/violations", "get_rest_api_rule_violations"),
    ("security/report", "get_security_report"),
    ("security/scan", "security_scan"),
    ("security/violations", "get_security_rule_violations"),
    ("sql/clear", "clear_sql_traces"),
    ("sql/pause", "pause_sql_trace_recording"),
    ("sql/resume", "resume_sql_trace_recording"),
    ("sql/traces", "get_sql_traces"),
    ("traces/clear", "clear_traces"),
    ("vulnerabilities/report", "get_vulnerabilities_report"),
    ("vulnerabilities/scan", "vulnerabilities_scan"),
)
_TOOL_CASES = [pytest.param(name, id=f"tool:{name}") for name in MATCHED_TOOLS]
_CLI_CASES = [pytest.param(path, name, id=f"cli:{path}") for path, name in MATCHED_CLI]


@pytest.mark.parametrize("name", _TOOL_CASES)
def test_tool_catalogue_matches_bootui_23(name: str) -> None:
    # matched: exact tool name, schema shape, default limit, and action flag from the pinned 2.3.0 fixture.
    local, oracle = SHARPIT[name], BOOTUI[name]
    assert local.name in SHARPIT
    assert local.name == oracle["name"]
    assert _schema_shape(local.input_schema) == _schema_shape(oracle["inputSchema"])
    if "defaultLimit" in oracle:
        assert local.default_limit == oracle["defaultLimit"]
    assert local.action is oracle["action"]


@pytest.mark.parametrize(("path", "name"), _CLI_CASES)
def test_cli_path_maps_to_bootui_tool(path: str, name: str) -> None:
    # matched: GET /cli exposes the same BootUI command path and tool name.
    tools = {tool["name"]: tool for tool in _client().get("/sharpit/api/cli").json()["tools"]}
    assert tools[name]["name"] == BOOTUI[name]["name"]
    assert tools[name]["command"].replace(" ", "/") == BOOTUI[name]["command"].replace(" ", "/")
    assert tools[name]["command"].replace(" ", "/") == path
