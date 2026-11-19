"""Validation tests for captured BootUI tracker fixtures (2.3.0 and 2.4.0).

Verifies provenance, pinned commit, scoped build command, JDK record,
and completeness against BootUI v2.3.0 and v2.4.0 source contracts.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

FIXTURES_BASE = Path(__file__).parent / "fixtures" / "bootui"
VERSIONS = ("2.3.0", "2.4.0")
PINNED_COMMITS = {
    "2.3.0": "7c89042c6a0a47e1cb22d2df7412d2177d7416d1",
    "2.4.0": "0df7ed764688d04f83c246c9965e90158c1db488",
}
PINNED_TAGS = {
    "2.3.0": "v2.3.0",
    "2.4.0": "v2.4.0",
}

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

EXPECTED_COUNTS = {
    "2.3.0": {
        "reads": 82,
        "actions": 78,
        "testClasses": 1109,
        "testMethods": 10646,
    },
    "2.4.0": {
        "reads": 82,
        "actions": 78,
        "testClasses": 1128,
        "testMethods": 10927,
    },
}

TOTAL_CLASSES = {"2.3.0": 1109, "2.4.0": 1128}
TOTAL_SIMPLE_NAMES = {"2.3.0": 1106, "2.4.0": 1125}

RECONCILIATION_COUNTS = {
    "2.3.0": {"union": 619, "rules": 603, "exclusions": 42, "additions": 26},
    "2.4.0": {"union": 621, "rules": 604, "exclusions": 43, "additions": 26},
}


def _load_json(filename: str, version: str = "2.3.0") -> dict | list:
    path = FIXTURES_BASE / version / filename
    assert path.is_file(), f"Missing required fixture file: {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _assert_route_completeness(routes: dict, expected_counts: dict) -> None:
    mappings = [
        *routes["crossCheck"]["starterMappings"],
        *routes["crossCheck"].get("inheritedMappings", []),
    ]
    catalog_routes = [*routes["reads"], *routes["actions"]]
    assert len(routes["reads"]) == expected_counts["reads"], "read route count changed"
    assert len(routes["actions"]) == expected_counts["actions"], "action route count changed"
    assert len(routes["crossCheck"]["starterMappings"]) == expected_counts["starterMappings"], (
        "starter mapping count changed"
    )
    assert len(routes["crossCheck"]["unpanelledRoutes"]) == expected_counts["unpanelledRoutes"], (
        "unpanelled GET route count changed"
    )

    def paths_match(left: str, right: str) -> bool:
        left_parts = left.split("?", 1)[0].strip("/").split("/")
        right_parts = right.split("?", 1)[0].strip("/").split("/")
        return len(left_parts) == len(right_parts) and all(
            a == b or "{" in a or "{" in b for a, b in zip(left_parts, right_parts, strict=True)
        )

    def is_catalog_mapping(mapping: dict) -> bool:
        return any(
            route["method"] == mapping["verb"] and paths_match(mapping["path"], route["path"])
            for route in catalog_routes
        )

    def route_has_mapping(route: dict) -> bool:
        return any(
            mapping["verb"] == route["method"] and paths_match(mapping["path"], route["path"]) for mapping in mappings
        )

    route_gaps = [gap for gap in routes["crossCheck"]["gaps"] if gap.get("category") == "catalog-without-mapping"]
    for route in catalog_routes:
        if not route_has_mapping(route):
            assert any(
                gap["method"] == route["method"]
                and gap["path"] == route["path"]
                and gap.get("catalogSource")
                and gap.get("starterSource")
                for gap in route_gaps
            ), f"catalog route has no starter mapping: {route['method']} {route['path']}"
    assert all(m.get("classification") for m in mappings if not is_catalog_mapping(m)), (
        "starter mapping missing from catalog must have a classification"
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_fixtures_record_pin_command_and_catalog_completeness(version: str) -> None:
    """Prove BootUI fixtures record full commit, exact commands, JDK and complete catalog."""
    # 1. Metadata provenance
    meta_path = FIXTURES_BASE / version / "meta.json"
    assert meta_path.is_file(), f"Missing fixture metadata at {meta_path}"

    meta = _load_json("meta.json", version)
    assert isinstance(meta, dict), "meta.json must be a JSON object"
    assert meta.get("commit") == PINNED_COMMITS[version], (
        f"Expected commit {PINNED_COMMITS[version]}, got {meta.get('commit')}"
    )
    assert meta.get("tag") == PINNED_TAGS[version], f"Expected tag {PINNED_TAGS[version]}, got {meta.get('tag')}"
    assert meta.get("bootuiVersion") == version, f"Expected bootuiVersion {version}, got {meta.get('bootuiVersion')}"
    assert "command" in meta, "meta.json must record the exact capture command"
    assert "mavenCommand" in meta, "meta.json must record the scoped Maven build command"
    assert "mvn -pl bootui-spring-boot-starter -am -DskipTests" in str(meta.get("mavenCommand")), (
        "meta.json mavenCommand must cite scoped build"
    )
    assert "jdk" in meta, "meta.json must record the JDK used"

    # 2. All 8 required fixtures exist
    for filename in REQUIRED_FIXTURES:
        assert (FIXTURES_BASE / version / filename).is_file(), f"Missing fixture file: {filename}"

    # 3. Panels catalog completeness
    panels_data = _load_json("panels.json", version)
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
    routes_data = _load_json("routes.json", version)
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
    tools_data = _load_json("tools.json", version)
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
    rule_ids_data = _load_json("rule-ids.json", version)
    assert isinstance(rule_ids_data, dict), "rule-ids.json must be a JSON object"
    rules = rule_ids_data.get("rules", [])
    assert len(rules) >= 50, f"Expected >= 50 rules, got {len(rules)}"
    diff_data = _load_json("rule-ids-diff.json", version)
    assert isinstance(diff_data, dict), "rule-ids-diff.json must be a JSON object"
    assert "explanations" in diff_data, "rule-ids-diff.json must explain diffs"

    # 7. Properties completeness
    props_data = _load_json("properties.json", version)
    assert isinstance(props_data, dict), "properties.json must be a JSON object"
    properties = props_data.get("properties", [])
    assert len(properties) == 209, f"Expected 209 properties, got {len(properties)}"
    prop_names = {p["name"] for p in properties}
    assert "bootui.read-only" in prop_names or "bootui.mcp.enabled" in prop_names
    for p in properties:
        assert "name" in p
        assert "type" in p

    # 8. BootUI tests completeness
    tests_data = _load_json("bootui-tests.json", version)
    assert isinstance(tests_data, dict), "bootui-tests.json must be a JSON object"
    test_classes = tests_data.get("testClasses", {})
    assert len(test_classes) >= 100, f"Expected >= 100 test classes, got {len(test_classes)}"


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_panels_catalog_exactness(version: str) -> None:
    """Verifies panels catalog contains all 65 panels matching BootUiPanels.java."""
    panels_data = _load_json("panels.json", version)
    assert isinstance(panels_data, dict)
    panels = panels_data["panels"]
    assert len(panels) == 65
    panel_map = {p["id"]: p for p in panels}

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


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_tools_mcp_annotations_and_schemas(version: str) -> None:
    """Verifies all 116 tools have complete MCP annotations and expanded input schemas."""
    tools_data = _load_json("tools.json", version)
    assert isinstance(tools_data, dict)
    tools = tools_data["tools"]
    assert len(tools) == 116

    tool_map = {t["name"]: t for t in tools}

    overview_tool = tool_map["get_overview"]
    assert overview_tool["action"] is False
    assert overview_tool["annotations"]["readOnlyHint"] is True
    assert overview_tool["annotations"]["destructiveHint"] is False
    assert overview_tool["annotations"]["idempotentHint"] is True
    assert overview_tool["annotations"]["openWorldHint"] is False

    scan_tool = tool_map["vulnerabilities_scan"]
    assert scan_tool["action"] is True
    assert scan_tool["annotations"]["readOnlyHint"] is False
    assert scan_tool["annotations"]["openWorldHint"] is True

    clear_tool = tool_map["clear_sql_traces"]
    assert clear_tool["action"] is True
    assert clear_tool["annotations"]["destructiveHint"] is True

    vuln_report_tool = tool_map["get_vulnerabilities_report"]
    assert vuln_report_tool.get("defaultLimit") == 10

    thread_snap_tool = tool_map["get_thread_snapshots"]
    assert thread_snap_tool.get("defaultLimit") == 6


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_tool_default_limits_match_tag_constants(version: str) -> None:
    tools = _load_json("tools.json", version)["tools"]
    limits = {tool["name"]: tool["defaultLimit"] for tool in tools if "defaultLimit" in tool}
    assert limits["get_metrics"] == 25
    assert limits["get_log_tail"] == 50
    assert limits["get_startup_timeline"] == 25


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_properties_hand_filled_citations(version: str) -> None:
    """Verifies hand-filled properties cite BootUiProperties.java line numbers."""
    props_data = _load_json("properties.json", version)
    assert isinstance(props_data, dict)
    properties = props_data["properties"]
    prop_map = {p["name"]: p for p in properties}

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


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_tests_catalog_resolves_ported_citations(version: str) -> None:
    """Verifies test catalog resolves ported BootUI test citations."""
    tests_data = _load_json("bootui-tests.json", version)
    assert isinstance(tests_data, dict)
    test_classes = tests_data["testClasses"]

    activation_class = tests_data["simpleNameIndex"]["BootUiActivationConditionTests"]["classes"][0]
    methods = test_classes[activation_class]
    assert "autoEnablesOnEnabledProfile" in methods
    assert "autoDisablesWithoutEnabledProfileAndWithoutDevtools" in methods
    assert "disabledProfileForcesOffByDefault" in methods
    assert "enabledOnOverridesDisabledProfileButRecordsWarning" in methods
    assert "enabledOffForcesDisabled" in methods


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_rule_ids_diff_has_all_explanations(version: str) -> None:
    """Verifies rule-ids-diff.json has an explanation for every single diff entry."""
    diff_data = _load_json("rule-ids-diff.json", version)
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


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_fixtures_reject_incomplete_catalogs_and_machine_paths(version: str) -> None:
    meta = _load_json("meta.json", version)
    assert "javaVersionOutput" in meta, "metadata must record actual java -version output"
    assert "mavenVersionOutput" in meta, "metadata must record actual mvn -v output"
    assert "settingsOverride" in meta, "metadata must record the Maven settings override"
    exp = EXPECTED_COUNTS[version]
    assert meta["counts"]["reads"] == exp["reads"]
    assert meta["counts"]["actions"] == exp["actions"]
    assert meta["counts"]["testClasses"] == exp["testClasses"]
    assert meta["counts"]["testMethods"] == exp["testMethods"]


@pytest.mark.parametrize("script_name", ["capture_bootui_23.py", "capture_bootui_24.py"])
def test_bootui_capture_pin_check_is_not_an_optimizable_assert(script_name: str) -> None:
    source = Path(__file__).parents[1] / "scripts" / script_name
    tree = ast.parse(source.read_text(encoding="utf-8"))
    guards = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "actual_commit != PINNED_COMMIT"
    ]
    assert len(guards) == 1, "capture must explicitly compare the resolved commit to the pinned commit"
    guard = guards[0]
    assert any(isinstance(node, ast.Raise) for node in guard.body)


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_routes_are_complete_and_classified(version: str) -> None:
    routes = _load_json("routes.json", version)
    reads = routes["reads"]
    actions = routes["actions"]
    cross_check = routes["crossCheck"]
    mappings = cross_check["starterMappings"]
    meta = _load_json("meta.json", version)
    assert len(reads) == meta["counts"]["reads"]
    assert len(actions) == meta["counts"]["actions"]
    assert len(mappings) == meta["counts"]["starterMappings"]
    assert len(cross_check["unpanelledRoutes"]) == meta["counts"]["unpanelledRoutes"]
    _assert_route_completeness(routes, meta["counts"])
    assert len(cross_check["gaps"]) == meta["counts"]["gaps"]
    assert [
        (gap["method"], gap["path"]) for gap in cross_check["gaps"] if gap.get("category") == "catalog-without-mapping"
    ] == [("POST", "/dev-services/services/conformance/restart")], (
        "only the documented dev-services route mismatch is allowed"
    )
    assert any(
        gap.get("category") == "catalog-without-mapping" and gap["path"] == "/dev-services/services/conformance/restart"
        for gap in cross_check["gaps"]
    ), "BootUI's dev-services restart inconsistency must be explicitly classified"


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_route_completeness_check_rejects_removed_route(version: str) -> None:
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / "routes.json"
        shutil.copy(FIXTURES_BASE / version / "routes.json", copy)
        routes = json.loads(copy.read_text(encoding="utf-8"))
        routes["reads"].pop()
        copy.write_text(json.dumps(routes), encoding="utf-8")
        mutated = json.loads(copy.read_text(encoding="utf-8"))
        counts = _load_json("meta.json", version)["counts"]
        with pytest.raises(AssertionError, match="read route count changed"):
            _assert_route_completeness(mutated, counts)


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_fixtures_contain_no_machine_paths(version: str) -> None:
    for path in (FIXTURES_BASE / version).glob("*.json"):
        contents = path.read_text(encoding="utf-8")
        assert not re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[/\\]", contents), f"Machine-specific path in {path.name}"
        assert "Files\\Amazon Corretto" not in contents, f"Machine-specific path in {path.name}"
    rules_data = _load_json("rule-ids.json", version)
    assert all("C:/development" not in rule["javaSource"] for rule in rules_data["rules"] if rule.get("javaSource"))


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_properties_exclude_nonexistent_cli_properties(version: str) -> None:
    names = {prop["name"] for prop in _load_json("properties.json", version)["properties"]}
    assert "bootui.cli.max-payload-bytes" not in names
    assert "bootui.cli.max-response-bytes" not in names


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_test_catalog_is_fully_qualified_and_unambiguous(version: str) -> None:
    catalog = _load_json("bootui-tests.json", version)
    classes = catalog["testClasses"]
    assert catalog["totalClasses"] == TOTAL_CLASSES[version]
    assert len(classes) == TOTAL_CLASSES[version]
    assert len(catalog["simpleNameIndex"]) == TOTAL_SIMPLE_NAMES[version]
    assert all(re.fullmatch(r"[\w$]+(?:\.[\w$]+)+", name) for name in classes)
    for name in (
        "CodeInventoryServiceTests",
        "ActuatorMappingsControllerTests",
    ):
        assert any(key.endswith(f".{name}") for key in classes)
    assert any(entry["ambiguous"] for entry in catalog["simpleNameIndex"].values())


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_retired_doc_rules_are_marked_and_explained(version: str) -> None:
    rules = {rule["id"]: rule for rule in _load_json("rule-ids.json", version)["rules"]}
    explanations = _load_json("rule-ids-diff.json", version)["explanations"]
    retired = [
        "MEM-CONTENT-004",
        "MEM-FOOTPRINT-004",
        "MEM-HEAP-007",
        "MEM-POOL-006",
        "MEM-THREAD-003",
        "SPRING-CONFIG-001",
        "SPRING-PERF-004",
        "SPRING-PROFILE-001",
        "SPRING-REACTIVE-002",
        "SPRING-WEB-006",
        "PT-A05-045",
        "PT-A05-070",
        "PT-A05-072",
    ]
    for rid in retired:
        assert rules[rid]["retired"] is True
        assert explanations[rid] == rules[rid]["retiredExplanation"]
        assert explanations[rid].startswith(("Retired:", "**Retired.**", "REMOVE"))
        assert len(explanations[rid]) > len("Retired")
    assert rules["QA-CFG-001"]["retired"] is True
    assert "ConfigMapping is recommended" in rules["QA-CFG-001"]["retiredExplanation"]


@pytest.mark.parametrize("version", VERSIONS)
def test_bootui_rule_id_independent_counter_is_reconciled(version: str) -> None:
    rules_data = _load_json("rule-ids.json", version)
    reconciliation = rules_data["reconciliation"]
    exclusions = reconciliation["independentIdsExcluded"]
    additions = reconciliation["fixtureIdsOutsideIndependentCounter"]
    exp = RECONCILIATION_COUNTS[version]
    assert reconciliation["independentUnionCount"] == exp["union"]
    assert reconciliation["fixtureCount"] == len(rules_data["rules"]) == exp["rules"]
    assert len(exclusions) == exp["exclusions"]
    assert len(additions) == exp["additions"]
    assert all(item["source"] and item["reason"] for item in [*exclusions, *additions])
    assert reconciliation["independentUnionCount"] == reconciliation["fixtureCount"] + len(exclusions) - len(additions)


@pytest.mark.parametrize("version", VERSIONS)
def test_catalog_includes_conformance_test_classes(version: str) -> None:
    """The catalog lists test classes outside src/test, e.g. the bootui-conformance base classes in src/main."""
    classes = _load_json("bootui-tests.json", version)["testClasses"]
    name = "io.github.jdubois.bootui.conformance.AbstractMcpConformanceTest"
    assert name in classes, f"{name} is missing from the test catalog"
    methods = set(classes[name])
    for method in (
        "testMcpValidatesJsonrpc",
        "testMcpRequiresJsonContentType",
        "testMcpRejectsBatchRequests",
        "testMcpRejectsOversizedRequestBeforeParsing",
        "testMcpRejectsUnsupportedProtocolVersionHeader",
    ):
        assert method in methods, f"{method} is missing from {name}"
