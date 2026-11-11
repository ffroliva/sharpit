import ast
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.tools import COMMANDS, TOOLS

ROOT = Path(__file__).parents[1]
BOOTUI_TOOLS = json.loads((ROOT / "fixtures/bootui/2.3.0/tools.json").read_text("utf-8"))["tools"]
BOOTUI = {tool["name"]: tool for tool in BOOTUI_TOOLS}
SHARPIT = {tool.name: tool for tool in TOOLS}


def _normalise_schema(schema: dict[str, Any]) -> dict[str, Any]:
    def normalise(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {name: normalise(child, name) for name, child in value.items()}
        if isinstance(value, list):
            return [normalise(child) for child in value]
        if key == "description" and isinstance(value, str):
            return value.replace("bootui.mcp.max-results", "SHARPIT_MCP_MAX_RESULTS")
        return value

    return normalise(schema)


def _client() -> TestClient:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), follow_redirects=False)


MATCHED_TOOLS = (
    "get_architecture_report",
    "architecture_scan",
    "mysql_read",
    "get_mysql_report",
    "get_database_connection_pools",
    "postgresql_read",
    "get_postgresql_report",
    "get_database_advisor_report",
    "database_advisor_scan",
    "clear_exceptions",
    "get_exceptions",
    "get_exception_detail",
    "get_health",
    "get_metrics",
    "get_overview",
    "get_request_profile",
    "get_rest_api_report",
    "rest_api_scan",
    "get_security_report",
    "security_scan",
    "clear_sql_traces",
    "pause_sql_trace_recording",
    "resume_sql_trace_recording",
    "clear_traces",
    "clear_transactions",
    "get_transactions",
    "pause_transaction_recording",
    "resume_transaction_recording",
    "vulnerabilities_scan",
    "get_startup_timeline",
)
PARTIAL_TOOLS = (
    "get_live_activity",
    "get_architecture_rule_violations",
    "get_beans",
    "get_config",
    "get_database_advisor_rule_violations",
    "get_http_exchanges",
    "get_http_routes",
    "get_loggers",
    "get_log_tail",
    "get_mappings",
    "get_rest_api_rule_violations",
    "get_security_logs",
    "get_security_rule_violations",
    "get_sql_traces",
    "get_threads",
    "get_traces",
    "get_vulnerabilities_report",
)
MISSING_TOOLS = (
    "disable_agent_sensor",
    "enable_agent_sensor",
    "get_agent_status",
    "get_ai_overview",
    "get_cache_stats",
    "get_code_inventory",
    "get_code_paths",
    "get_conditions",
    "get_crac_report",
    "crac_scan",
    "get_flyway_migrations",
    "get_liquibase_changesets",
    "get_dev_services",
    "trigger_devtools_livereload",
    "get_devtools_status",
    "get_fault_tolerance",
    "get_github_dashboard",
    "get_graalvm_report",
    "graalvm_scan",
    "get_hibernate_report",
    "hibernate_scan",
    "get_hibernate_statistics",
    "get_hibernate_rule_violations",
    "get_http_sessions",
    "get_runtime_run_comparison",
    "get_runtime_impact",
    "get_runtime_insights",
    "get_runtime_insight",
    "get_jms_activity",
    "get_jvm_tuning",
    "get_kafka_activity",
    "disable_low_footprint",
    "enable_low_footprint",
    "get_low_footprint",
    "get_emails",
    "analyze_heap_dump",
    "get_heap_dump_report",
    "get_live_memory",
    "get_memory_report",
    "memory_scan",
    "get_memory_rule_violations",
    "get_pentest_report",
    "pentest_scan",
    "get_method_probe",
    "start_method_probe",
    "get_profile_diff",
    "get_rabbitmq_activity",
    "get_spring_data_repositories",
    "clear_rest_client_traces",
    "pause_rest_client_recording",
    "resume_rest_client_recording",
    "get_rest_client_traces",
    "get_scheduled_tasks",
    "get_spring_security",
    "get_claude_code_sessions",
    "get_copilot_sessions",
    "get_side_effects",
    "get_spring_report",
    "spring_scan",
    "get_spring_rule_violations",
    "cancel_thread_observation",
    "capture_thread_snapshot",
    "clear_thread_snapshots",
    "get_thread_snapshots",
    "get_thread_observation",
    "start_thread_observation",
    "get_thread_analysis",
    "get_thread_detail",
    "get_websockets",
)
SHARPIT_ONLY = (
    "fastapi_scan",
    "get_data_repositories",
    "get_sqlalchemy_statistics",
    "enable_sqlalchemy_statistics",
    "get_alembic_migrations",
    "get_sql_trace_insights",
    "get_fastapi_rule_violations",
    "get_fastapi_report",
    "get_fastapi_security",
)
CLI_COMMAND_DIFFERENCES = (
    "get_request_profile",
    "clear_transactions",
    "get_transactions",
    "pause_transaction_recording",
    "resume_transaction_recording",
)
MATCHED_CLI = tuple((BOOTUI[name]["command"], name) for name in MATCHED_TOOLS if name not in CLI_COMMAND_DIFFERENCES)

pytestmark = [
    pytest.mark.bootui("cli:architecture report"),
    pytest.mark.bootui("cli:architecture scan"),
    pytest.mark.bootui("cli:db mysql read"),
    pytest.mark.bootui("cli:db mysql report"),
    pytest.mark.bootui("cli:db pools"),
    pytest.mark.bootui("cli:db postgres read"),
    pytest.mark.bootui("cli:db postgres report"),
    pytest.mark.bootui("cli:db report"),
    pytest.mark.bootui("cli:db scan"),
    pytest.mark.bootui("cli:exceptions clear"),
    pytest.mark.bootui("cli:exceptions list"),
    pytest.mark.bootui("cli:exceptions show"),
    pytest.mark.bootui("cli:metrics"),
    pytest.mark.bootui("cli:health"),
    pytest.mark.bootui("cli:overview"),
    pytest.mark.bootui("cli:rest-api report"),
    pytest.mark.bootui("cli:rest-api scan"),
    pytest.mark.bootui("cli:security report"),
    pytest.mark.bootui("cli:security scan"),
    pytest.mark.bootui("cli:sql clear"),
    pytest.mark.bootui("cli:startup"),
    pytest.mark.bootui("cli:sql pause"),
    pytest.mark.bootui("cli:sql resume"),
    pytest.mark.bootui("cli:traces clear"),
    pytest.mark.bootui("cli:vulnerabilities scan"),
    pytest.mark.bootui("tool:architecture_scan"),
    pytest.mark.bootui("tool:clear_exceptions"),
    pytest.mark.bootui("tool:clear_sql_traces"),
    pytest.mark.bootui("tool:clear_traces"),
    pytest.mark.bootui("tool:clear_transactions"),
    pytest.mark.bootui("tool:database_advisor_scan"),
    pytest.mark.bootui("tool:get_architecture_report"),
    pytest.mark.bootui("tool:get_database_advisor_report"),
    pytest.mark.bootui("tool:get_database_connection_pools"),
    pytest.mark.bootui("tool:get_exception_detail"),
    pytest.mark.bootui("tool:get_exceptions"),
    pytest.mark.bootui("tool:get_health"),
    pytest.mark.bootui("tool:get_metrics"),
    pytest.mark.bootui("tool:get_mysql_report"),
    pytest.mark.bootui("tool:get_overview"),
    pytest.mark.bootui("tool:get_postgresql_report"),
    pytest.mark.bootui("tool:get_request_profile"),
    pytest.mark.bootui("tool:get_rest_api_report"),
    pytest.mark.bootui("tool:get_security_report"),
    pytest.mark.bootui("tool:get_startup_timeline"),
    pytest.mark.bootui("tool:get_transactions"),
    pytest.mark.bootui("tool:mysql_read"),
    pytest.mark.bootui("tool:pause_sql_trace_recording"),
    pytest.mark.bootui("tool:pause_transaction_recording"),
    pytest.mark.bootui("tool:postgresql_read"),
    pytest.mark.bootui("tool:rest_api_scan"),
    pytest.mark.bootui("tool:resume_sql_trace_recording"),
    pytest.mark.bootui("tool:resume_transaction_recording"),
    pytest.mark.bootui("tool:security_scan"),
    pytest.mark.bootui("tool:vulnerabilities_scan"),
]


def test_bootui_marks_equal_the_matched_rows() -> None:
    source = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    assignment = next(
        (
            node
            for node in source.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets)
        ),
        None,
    )
    marked = {
        call.args[0].value
        for call in ast.walk(assignment.value if assignment is not None else ast.List(elts=[], ctx=ast.Load()))
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "bootui"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    }
    assert marked == {"tool:" + name for name in MATCHED_TOOLS} | {"cli:" + command for command, _ in MATCHED_CLI}


@pytest.mark.parametrize("name", MATCHED_TOOLS, ids=lambda name: f"tool:{name}")
def test_tool_catalogue_matches_bootui_23(name: str) -> None:
    local, oracle = SHARPIT[name], BOOTUI[name]
    assert local.name == oracle["name"]
    assert _normalise_schema(local.input_schema) == _normalise_schema(oracle["inputSchema"])
    assert local.default_limit == oracle.get("defaultLimit")
    assert local.action is oracle["action"]
    assert local.panel == oracle["panel"]


@pytest.mark.parametrize("name", PARTIAL_TOOLS, ids=lambda name: f"tool:{name}")
def test_partial_tool_catalogue_difference_is_known(name: str) -> None:
    local, oracle = SHARPIT[name], BOOTUI[name]
    assert local.name == oracle["name"]
    assert _normalise_schema(local.input_schema) != _normalise_schema(oracle["inputSchema"])
    assert (local.default_limit == oracle.get("defaultLimit")) is (
        name
        not in {"get_live_activity", "get_beans", "get_config", "get_http_exchanges", "get_log_tail", "get_sql_traces"}
    )
    assert local.action is oracle["action"]
    assert local.panel == oracle["panel"]


def test_tool_coverage_matches_fixture() -> None:
    classified = set(MATCHED_TOOLS) | set(PARTIAL_TOOLS) | set(MISSING_TOOLS)
    assert classified == set(BOOTUI)
    assert len(BOOTUI_TOOLS) == 116
    assert set(SHARPIT) - set(BOOTUI) == set(SHARPIT_ONLY)
    assert set(COMMANDS) - set(BOOTUI) == set(SHARPIT_ONLY)
    cli_paths = {(BOOTUI[name]["command"], name) for name in (*MATCHED_TOOLS, *PARTIAL_TOOLS, *MISSING_TOOLS)}
    assert cli_paths == {(tool["command"], tool["name"]) for tool in BOOTUI_TOOLS}
    assert len(cli_paths) == 116
    assert {(COMMANDS[name], name) for name in SHARPIT_ONLY} == {
        (command, name) for name, command in COMMANDS.items() if name not in BOOTUI
    }


@pytest.mark.parametrize(("command", "name"), MATCHED_CLI, ids=lambda value: str(value))
def test_cli_path_maps_to_bootui_tool(command: str, name: str) -> None:
    response = _client().get("/sharpit/api/cli").json()
    tools = {tool["name"]: tool for tool in response["tools"]}
    local = tools[name]
    oracle = BOOTUI[name]
    assert local["name"] == oracle["name"]
    assert oracle["command"] == command
    assert local["command"] == command
    assert local["action"] is oracle["action"]
    assert local["panel"] == oracle["panel"]


def test_cli_default_limit_matches_bootui_23() -> None:
    # CliServerStatus exposes the effective CLI result limit, not each tool's input defaultLimit.
    assert _client().get("/sharpit/api/cli").json()["maxResults"] == 200
