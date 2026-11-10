"""Validation tests for captured BootUI 2.3.0 tracker fixtures.

Verifies provenance, pinned commit, scoped build command, JDK record,
and completeness against BootUI v2.3.0 source contracts.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "bootui" / "2.3.0"
PINNED_COMMIT = "7c89042c6a0a47e1cb22d2df7412d2177d7416d1"
PINNED_TAG = "v2.3.0"

REQUIRED_FIXTURES = (
    "meta.json",
    "panels.json",
    "routes.json",
    "tools.json",
    "rule-ids.json",
    "rule-ids-diff.json",
    "properties.json",
    "bootui-tests.json",
)


def _load_json(filename: str) -> dict | list:
    path = FIXTURES_ROOT / filename
    assert path.is_file(), f"Missing required fixture file: {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_bootui_23_fixtures_record_pin_command_and_catalog_completeness() -> None:
    """S1: Prove BootUI 2.3.0 fixtures record full commit, exact commands, JDK and complete catalog."""
    # 1. Metadata provenance
    meta_path = FIXTURES_ROOT / "meta.json"
    assert meta_path.is_file(), f"Missing fixture metadata at {meta_path}"

    meta = _load_json("meta.json")
    assert isinstance(meta, dict), "meta.json must be a JSON object"
    assert meta.get("commit") == PINNED_COMMIT, f"Expected commit {PINNED_COMMIT}, got {meta.get('commit')}"
    assert meta.get("tag") == PINNED_TAG, f"Expected tag {PINNED_TAG}, got {meta.get('tag')}"
    assert meta.get("bootuiVersion") == "2.3.0", f"Expected bootuiVersion 2.3.0, got {meta.get('bootuiVersion')}"
    assert "command" in meta, "meta.json must record the exact capture command"
    assert "mavenCommand" in meta, "meta.json must record the scoped Maven build command"
    assert "mvn -pl bootui-spring-boot-starter -am -DskipTests" in str(meta.get("mavenCommand")), (
        "meta.json mavenCommand must cite scoped build"
    )
    assert "jdk" in meta, "meta.json must record the JDK used"

    # 2. All 8 required fixtures exist
    for filename in REQUIRED_FIXTURES:
        assert (FIXTURES_ROOT / filename).is_file(), f"Missing fixture file: {filename}"

    # 3. Panels catalog completeness
    panels_data = _load_json("panels.json")
    assert isinstance(panels_data, dict), "panels.json must be a JSON object"
    panels = panels_data.get("panels", [])
    assert len(panels) >= 50, f"Expected >= 50 panels, got {len(panels)}"
    panel_ids = {p["id"] for p in panels}
    assert "overview" in panel_ids
    assert "health" in panel_ids
    assert "threads" in panel_ids
    assert "vulnerabilities" in panel_ids
    for p in panels:
        assert "id" in p
        assert "title" in p
        assert "actionCapable" in p
        assert "apiPrefixes" in p

    # 4. Routes catalog and cross-check completeness
    routes_data = _load_json("routes.json")
    assert isinstance(routes_data, dict), "routes.json must be a JSON object"
    reads = routes_data.get("reads", [])
    actions = routes_data.get("actions", [])
    cross_check = routes_data.get("crossCheck", {})
    assert len(reads) >= 40, f"Expected >= 40 read routes, got {len(reads)}"
    assert len(actions) >= 30, f"Expected >= 30 action routes, got {len(actions)}"
    assert "starterMappings" in cross_check, "routes.json must include starter @*Mapping cross-check"
    assert "unpanelledRoutes" in cross_check, "routes.json cross-check must record unpanelled routes (e.g. /otlp)"
    assert "gaps" in cross_check, "routes.json cross-check must record gaps"

    # 5. Tools catalog completeness
    tools_data = _load_json("tools.json")
    assert isinstance(tools_data, dict), "tools.json must be a JSON object"
    tools = tools_data.get("tools", [])
    assert len(tools) >= 50, f"Expected >= 50 tools, got {len(tools)}"
    for t in tools:
        assert "name" in t
        assert "panel" in t
        assert "action" in t
        assert "annotations" in t, f"Tool {t['name']} missing MCP annotations"
        annotations = t["annotations"]
        for key in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
            assert key in annotations, f"Tool {t['name']} annotations missing {key}"
            assert isinstance(annotations[key], bool), f"Tool {t['name']} annotation {key} must be bool"
        assert "inputSchema" in t, f"Tool {t['name']} missing inputSchema"
        assert t["inputSchema"].get("type") == "object", f"Tool {t['name']} inputSchema must be object"
        if not t["action"]:
            assert annotations["readOnlyHint"] is True, f"Read tool {t['name']} must have readOnlyHint=True"
            assert annotations["destructiveHint"] is False, f"Read tool {t['name']} must have destructiveHint=False"
            assert annotations["idempotentHint"] is True, f"Read tool {t['name']} must have idempotentHint=True"

    # 6. Rule IDs and diff completeness
    rule_ids_data = _load_json("rule-ids.json")
    assert isinstance(rule_ids_data, dict), "rule-ids.json must be a JSON object"
    rules = rule_ids_data.get("rules", [])
    assert len(rules) >= 50, f"Expected >= 50 rules, got {len(rules)}"
    diff_data = _load_json("rule-ids-diff.json")
    assert isinstance(diff_data, dict), "rule-ids-diff.json must be a JSON object"
    assert "explanations" in diff_data, "rule-ids-diff.json must explain diffs"

    # 7. Properties completeness
    props_data = _load_json("properties.json")
    assert isinstance(props_data, dict), "properties.json must be a JSON object"
    properties = props_data.get("properties", [])
    assert len(properties) >= 80, f"Expected >= 80 properties, got {len(properties)}"
    prop_names = {p["name"] for p in properties}
    assert "bootui.read-only" in prop_names or "bootui.mcp.enabled" in prop_names
    for p in properties:
        assert "name" in p
        assert "type" in p

    # 8. BootUI tests completeness
    tests_data = _load_json("bootui-tests.json")
    assert isinstance(tests_data, dict), "bootui-tests.json must be a JSON object"
    test_classes = tests_data.get("testClasses", {})
    assert len(test_classes) >= 100, f"Expected >= 100 test classes, got {len(test_classes)}"


def test_bootui_23_panels_catalog_exactness() -> None:
    """Verifies panels catalog contains all 65 panels matching BootUiPanels.java."""
    panels_data = _load_json("panels.json")
    assert isinstance(panels_data, dict)
    panels = panels_data["panels"]
    assert len(panels) == 65
    panel_map = {p["id"]: p for p in panels}

    # Verify specific key panels and their actionCapable flags
    assert panel_map["overview"]["title"] == "Scorecard"
    assert panel_map["overview"]["actionCapable"] is False
    assert panel_map["overview"]["apiPrefixes"] == []

    assert panel_map["health"]["title"] == "Health"
    assert panel_map["health"]["actionCapable"] is False
    assert panel_map["health"]["apiPrefixes"] == ["/health"]

    assert panel_map["http-sessions"]["title"] == "HTTP Sessions"
    assert panel_map["http-sessions"]["actionCapable"] is True
    assert panel_map["http-sessions"]["apiPrefixes"] == ["/http-sessions"]

    assert panel_map["vulnerabilities"]["title"] == "Vulnerabilities"
    assert panel_map["vulnerabilities"]["actionCapable"] is True
    assert panel_map["vulnerabilities"]["apiPrefixes"] == ["/vulnerabilities"]

    assert panel_map["cli"]["title"] == "Command Line"
    assert panel_map["cli"]["actionCapable"] is False
    assert panel_map["cli"]["apiPrefixes"] == []


def test_bootui_23_tools_mcp_annotations_and_schemas() -> None:
    """Verifies all 116 tools have complete MCP annotations and expanded input schemas."""
    tools_data = _load_json("tools.json")
    assert isinstance(tools_data, dict)
    tools = tools_data["tools"]
    assert len(tools) == 116

    tool_map = {t["name"]: t for t in tools}

    # Verify read tool annotations
    overview_tool = tool_map["get_overview"]
    assert overview_tool["action"] is False
    assert overview_tool["annotations"]["readOnlyHint"] is True
    assert overview_tool["annotations"]["destructiveHint"] is False
    assert overview_tool["annotations"]["idempotentHint"] is True
    assert overview_tool["annotations"]["openWorldHint"] is False

    # Verify action tool annotations
    scan_tool = tool_map["vulnerabilities_scan"]
    assert scan_tool["action"] is True
    assert scan_tool["annotations"]["readOnlyHint"] is False
    assert scan_tool["annotations"]["openWorldHint"] is True  # OSV.dev network call

    # Verify destructive action tool
    clear_tool = tool_map["clear_sql_traces"]
    assert clear_tool["action"] is True
    assert clear_tool["annotations"]["destructiveHint"] is True

    # Verify compact answer default limit
    vuln_report_tool = tool_map["get_vulnerabilities_report"]
    assert vuln_report_tool.get("defaultLimit") == 10

    thread_snap_tool = tool_map["get_thread_snapshots"]
    assert thread_snap_tool.get("defaultLimit") == 6


def test_bootui_23_properties_hand_filled_citations() -> None:
    """Verifies hand-filled properties cite BootUiProperties.java line numbers."""
    props_data = _load_json("properties.json")
    assert isinstance(props_data, dict)
    properties = props_data["properties"]
    prop_map = {p["name"]: p for p in properties}

    # Verify hand-filled properties cite BootUiProperties.java lines
    assert "bootui.enabled-profiles" in prop_map
    enabled_prof = prop_map["bootui.enabled-profiles"]
    assert enabled_prof["defaultValue"] == ["dev", "local"]
    assert "BootUiProperties.java" in enabled_prof["defaultValueSource"]

    assert "bootui.disabled-profiles" in prop_map
    disabled_prof = prop_map["bootui.disabled-profiles"]
    assert disabled_prof["defaultValue"] == ["prod", "production"]
    assert "BootUiProperties.java" in disabled_prof["defaultValueSource"]

    assert "bootui.api-path" in prop_map
    api_path_prop = prop_map["bootui.api-path"]
    assert api_path_prop["defaultValue"] == "/bootui/api"
    assert "BootUiProperties.java" in api_path_prop["defaultValueSource"]

    assert "bootui.cli.execution-timeout" in prop_map
    cli_timeout = prop_map["bootui.cli.execution-timeout"]
    assert cli_timeout["defaultValue"] == "30s"
    assert "BootUiProperties.java" in cli_timeout["defaultValueSource"]


def test_bootui_23_tests_catalog_resolves_ported_citations() -> None:
    """Verifies test catalog resolves ported BootUI test citations."""
    tests_data = _load_json("bootui-tests.json")
    assert isinstance(tests_data, dict)
    test_classes = tests_data["testClasses"]

    assert "BootUiActivationConditionTests" in test_classes
    methods = test_classes["BootUiActivationConditionTests"]
    assert "autoEnablesOnEnabledProfile" in methods
    assert "autoDisablesWithoutEnabledProfileAndWithoutDevtools" in methods
    assert "disabledProfileForcesOffByDefault" in methods
    assert "enabledOnOverridesDisabledProfileButRecordsWarning" in methods
    assert "enabledOffForcesDisabled" in methods


def test_bootui_23_rule_ids_diff_has_all_explanations() -> None:
    """Verifies rule-ids-diff.json has an explanation for every single diff entry."""
    diff_data = _load_json("rule-ids-diff.json")
    assert isinstance(diff_data, dict)
    in_doc_only = diff_data["inDocOnly"]
    in_java_only = diff_data["inJavaOnly"]
    explanations = diff_data["explanations"]

    for rid in in_doc_only:
        assert rid in explanations, f"Missing explanation for doc-only rule {rid}"
        assert len(explanations[rid]) > 0

    for rid in in_java_only:
        assert rid in explanations, f"Missing explanation for java-only rule {rid}"
        assert len(explanations[rid]) > 0


def test_bootui_23_fixtures_reject_incomplete_catalogs_and_machine_paths() -> None:
    meta = _load_json("meta.json")
    assert "javaVersionOutput" in meta, "metadata must record actual java -version output"
    assert "mavenVersionOutput" in meta, "metadata must record actual mvn -v output"
    assert "settingsOverride" in meta, "metadata must record the Maven settings override"
    assert meta["counts"] == {
        "panels": 65,
        "reads": 64,
        "actions": 18,
        "tools": 116,
        "rules": 0,
        "properties": 0,
        "defaultedProperties": 44,
        "testClasses": 0,
        "testMethods": 0,
    }
    routes = _load_json("routes.json")
    assert len(routes["reads"]) == 64
    assert len(routes["actions"]) == 18
    assert all(route["path"] != "/missing" for route in routes["reads"])
    assert all("classification" in route for route in routes["crossCheck"]["starterMappings"])
    tools = _load_json("tools.json")["tools"]
    assert {tool["name"]: tool["defaultLimit"] for tool in tools if "defaultLimit" in tool}["get_metrics"] == 25
    assert {tool["name"]: tool["defaultLimit"] for tool in tools if "defaultLimit" in tool}["get_log_tail"] == 50
    props = {prop["name"] for prop in _load_json("properties.json")["properties"]}
    assert "bootui.cli.max-payload-bytes" not in props
    assert "bootui.cli.max-response-bytes" not in props
    catalog = _load_json("bootui-tests.json")
    assert all("." in name for name in catalog["testClasses"])
    assert all(
        "C:/development" not in rule["javaSource"]
        for rule in _load_json("rule-ids.json")["rules"]
        if rule.get("javaSource")
    )
