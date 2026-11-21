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


def test_bootui_capture_pin_check_is_not_an_optimizable_assert() -> None:
    source = Path(__file__).parents[1] / "scripts" / "capture_bootui.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    guards = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "actual_commit != commit"
    ]
    assert len(guards) == 1, "capture must compare the resolved commit to the pinned commit"
    assert any(isinstance(node, ast.Raise) for node in guards[0].body)


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


def test_capture_classifies_bootui_compat_ids_in_rule_exclusions() -> None:
    from scripts import capture_bootui

    source = "bootui-engine/src/main/java/io/github/jdubois/bootui/engine/compatibility/PlatformCompatibility.java"
    reviewer_union = {"BOOTUI-COMPAT-001", "BOOTUI-COMPAT-010"}
    reviewer_java = {"BOOTUI-COMPAT-001": source, "BOOTUI-COMPAT-010": source}
    try:
        exclusions = capture_bootui._build_rule_exclusions(reviewer_union, set(), reviewer_java)
    except ValueError as exc:
        exclusions = [{"id": f"ERROR: {exc}", "source": "", "reason": ""}]
    assert [item["id"] for item in exclusions] == ["BOOTUI-COMPAT-001", "BOOTUI-COMPAT-010"]
    assert exclusions[0]["source"] == source
    assert "PlatformCompatibility.java" in exclusions[0]["reason"]


def test_capture_rules_marks_java_retired_sets_rapi_definitions_and_doc_retired(tmp_path: Path) -> None:
    from scripts import capture_bootui

    bootui_root = tmp_path / "bootui"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    docs_dir = bootui_root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "PENTEST-CHECKS.md").write_text(
        "### PT-A02-005 - Session cookie HttpOnly flag is explicitly disabled\n\n"
        "**Retired.** Duplicate of SEC-SESSION-003.\n\n"
        "| ID | Disposition | Audit result | Sources |\n"
        "| --- | --- | --- | --- |\n"
        "| PT-A02-005 | UPDATE | Earlier audit row. | S07 |\n",
        encoding="utf-8",
    )
    (docs_dir / "REST-API-CHECKS.md").write_text(
        "### RAPI-DOC-001 - Consider explicit operation documentation\n\n"
        "**Retired.** Always SKIPPED.\n\n"
        "| Rule | Change | Source & rationale |\n"
        "| --- | --- | --- |\n"
        "| RAPI-DOC-001 | Reframe as explicit enrichment; INFO retained | Earlier audit. |\n"
        "| RAPI-DOC-001, RAPI-DOC-002 | Retired | OpenAPI generators derive operations. |\n",
        encoding="utf-8",
    )
    db_reg = (
        bootui_root
        / "bootui-engine/src/main/java/io/github/jdubois/bootui/engine/databaseadvisor/DatabaseAdvisorRuleRegistry.java"
    )
    db_reg.parent.mkdir(parents=True)
    db_reg.write_text(
        "package io.github.jdubois.bootui.engine.databaseadvisor;\n"
        "import java.util.Set;\n"
        "final class DatabaseAdvisorRuleRegistry {\n"
        '    static final Set<String> RETIRED_RULE_IDS = Set.of("DB-POOL-004", "DB-SERVER-002");\n'
        "}\n",
        encoding="utf-8",
    )
    sec_reg = (
        bootui_root
        / "bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure"
        / "security/SecurityRuleRegistry.java"
    )
    sec_reg.parent.mkdir(parents=True)
    sec_reg.write_text(
        "package io.github.jdubois.bootui.autoconfigure.security;\n"
        "import java.util.Set;\n"
        "final class SecurityRuleRegistry {\n"
        '    static final Set<String> RETIRED_RULE_IDS = Set.of("SEC-AUTH-003");\n'
        "}\n",
        encoding="utf-8",
    )
    rapi_java = bootui_root / "bootui-engine/src/main/java/io/github/jdubois/bootui/engine/restapi/RestApiRules.java"
    rapi_java.parent.mkdir(parents=True)
    rapi_java.write_text(
        "package io.github.jdubois.bootui.engine.restapi;\n"
        "final class CollectionsUsePluralNounsRule extends AbstractRestApiRule {\n"
        "    CollectionsUsePluralNounsRule() {\n"
        "        super(new RestApiRuleDefinition(\n"
        '            "RAPI-NAME-002",\n'
        '            "Consider plural collection names",\n'
        "            RestApiCategory.NAMING,\n"
        '            "INFO",\n'
        '            "Retired heuristic: an English-language suffix check cannot distinguish"\n'
        '                + " resource collections.",\n'
        '            "Choose names.",\n'
        "            RestApiRuleHelp.RESOURCES_DOCS));\n"
        "    }\n"
        "    @Override\n"
        "    RestApiRuleResultDto doEvaluate(RestApiContext context) {\n"
        "        return RestApiRuleSupport.skipped(\n"
        "            definition(),\n"
        '            "Retired heuristic: literal resource names are valid.");\n'
        "    }\n"
        "}\n"
        "final class ExplicitOperationDocumentationRule extends AbstractRestApiRule {\n"
        "    ExplicitOperationDocumentationRule() {\n"
        "        super(new RestApiRuleDefinition(\n"
        '            "RAPI-DOC-002", "Consider operation documentation", RestApiCategory.ERROR_HANDLING, "INFO",\n'
        '            "Documentation may be generated automatically.", "Add useful detail.",\n'
        "            RestApiRuleHelp.OPENAPI_OPERATION_DOCS));\n"
        "    }\n"
        "    @Override\n"
        "    RestApiRuleResultDto doEvaluate(RestApiContext context) {\n"
        "        return RestApiRuleSupport.skipped(definition(),\n"
        '            "Retired heuristic: generated docs already cover the operation.");\n'
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    capture_bootui._capture_rules(str(bootui_root), str(out_dir))
    rules_data = json.loads((out_dir / "rule-ids.json").read_text(encoding="utf-8"))
    diff_data = json.loads((out_dir / "rule-ids-diff.json").read_text(encoding="utf-8"))
    retired_by_id = {r["id"]: r["retired"] for r in rules_data["rules"]}
    assert retired_by_id == {
        "DB-POOL-004": True,
        "DB-SERVER-002": True,
        "PT-A02-005": True,
        "RAPI-DOC-001": True,
        "RAPI-DOC-002": True,
        "RAPI-NAME-002": True,
        "SEC-AUTH-003": True,
    }
    assert all(r["retiredExplanation"] for r in rules_data["rules"])
    assert next(r for r in rules_data["rules"] if r["id"] == "RAPI-DOC-002")["retiredExplanation"] == (
        "Retired heuristic: generated docs already cover the operation."
    )
    assert next(r for r in rules_data["rules"] if r["id"] == "RAPI-NAME-002")["retiredExplanation"] == (
        "Retired heuristic: literal resource names are valid."
    )
    assert diff_data.get("inDocOnlyCount") == len(diff_data["inDocOnly"])
    assert diff_data.get("inJavaOnlyCount") == len(diff_data["inJavaOnly"])


def test_capture_routes_records_starter_mappings_count_and_excludes_inherited_from_gaps(tmp_path: Path) -> None:
    from scripts import capture_bootui

    bootui_root = tmp_path / "bootui"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    catalog = (
        bootui_root
        / "bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/BootUiApiContractCatalog.java"
    )
    catalog.parent.mkdir(parents=True)
    catalog.write_text('class BootUiApiContractCatalog { void init() { read("overview", "/overview"); } }\n', "utf-8")
    web_dir = bootui_root / "bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/web"
    web_dir.mkdir(parents=True)
    (web_dir / "BaseSessionController.java").write_text(
        'public abstract class BaseSessionController { @PostMapping("/clear") void clear() {} }\n',
        encoding="utf-8",
    )
    (web_dir / "CopilotController.java").write_text(
        '@RequestMapping("/bootui/api/copilot")\npublic class CopilotController extends BaseSessionController {}\n',
        encoding="utf-8",
    )
    (web_dir / "OverviewController.java").write_text(
        '@RequestMapping("/bootui/api")\n'
        "public class OverviewController {\n"
        '    @GetMapping("/overview") void get() {}\n'
        '    @GetMapping("/panels") void panels() {}\n'
        "}\n",
        encoding="utf-8",
    )

    capture_bootui._capture_routes(str(bootui_root), str(out_dir))
    routes = json.loads((out_dir / "routes.json").read_text(encoding="utf-8"))
    cross_check = routes["crossCheck"]
    assert cross_check.get("starterMappingsCount") == 3
    assert len(cross_check["gaps"]) == 2
    assert cross_check["gaps"][0].get("category") == "starter-without-catalog"
    assert cross_check["unpanelledRoutes"] == [
        {
            "controller": "OverviewController.java",
            "source": (
                "bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure"
                "/web/OverviewController.java"
            ),
            "line": 4,
            "verb": "GET",
            "path": "/panels",
            "classification": "framework-introspection",
            "reason": "Framework introspection metadata endpoint",
        }
    ]


def test_capture_properties_reads_defaults_from_source_and_keeps_cli_max(tmp_path: Path) -> None:
    from scripts import capture_bootui

    bootui_root = tmp_path / "bootui"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    props_java = (
        bootui_root
        / "bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/BootUiProperties.java"
    )
    props_java.parent.mkdir(parents=True)
    props_java.write_text(
        "package io.github.jdubois.bootui.autoconfigure;\n"
        "public class BootUiProperties {\n"
        "    public static class DevServices {\n"
        "        private int logTailBytes = 64 * 1024;\n"
        "    }\n"
        "    public static class Cli {\n"
        "        private int maxConcurrentCalls = McpProtocol.DEFAULT_MAX_CONCURRENT_CALLS;\n"
        "        private int maxResults = 200;\n"
        "        private String instancesDir;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    mcp_java = bootui_root / "bootui-engine/src/main/java/io/github/jdubois/bootui/engine/mcp/McpProtocol.java"
    mcp_java.parent.mkdir(parents=True)
    mcp_java.write_text(
        "package io.github.jdubois.bootui.engine.mcp;\n"
        "public final class McpProtocol {\n"
        "    public static final int DEFAULT_MAX_CONCURRENT_CALLS = 20;\n"
        "}\n",
        encoding="utf-8",
    )
    meta_file = bootui_root / "bootui-spring-boot-starter/target/classes/META-INF/spring-configuration-metadata.json"
    meta_file.parent.mkdir(parents=True)
    meta_file.write_text(
        json.dumps(
            {
                "properties": [
                    {
                        "name": "bootui.dev-services.log-tail-bytes",
                        "type": "java.lang.Integer",
                        "sourceType": "io.github.jdubois.bootui.autoconfigure.BootUiProperties$DevServices",
                    },
                    {
                        "name": "bootui.cli.max-concurrent-calls",
                        "type": "java.lang.Integer",
                        "sourceType": "io.github.jdubois.bootui.autoconfigure.BootUiProperties$Cli",
                    },
                    {
                        "name": "bootui.cli.max-results",
                        "type": "java.lang.Integer",
                        "defaultValue": 200,
                        "sourceType": "io.github.jdubois.bootui.autoconfigure.BootUiProperties$Cli",
                    },
                    {
                        "name": "bootui.cli.instances-dir",
                        "type": "java.lang.String",
                        "sourceType": "io.github.jdubois.bootui.autoconfigure.BootUiProperties$Cli",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    capture_bootui._capture_properties(str(bootui_root), str(out_dir))
    props = {p["name"]: p for p in json.loads((out_dir / "properties.json").read_text(encoding="utf-8"))["properties"]}
    assert sorted(props) == [
        "bootui.cli.instances-dir",
        "bootui.cli.max-concurrent-calls",
        "bootui.cli.max-results",
        "bootui.dev-services.log-tail-bytes",
    ]
    assert props["bootui.cli.max-concurrent-calls"]["defaultValue"] == 20
    assert (
        props["bootui.cli.max-concurrent-calls"].get("defaultValueSource")
        == "BootUiProperties.java:7 (McpProtocol.DEFAULT_MAX_CONCURRENT_CALLS)"
    )
    assert props["bootui.dev-services.log-tail-bytes"]["defaultValue"] == 65536
    assert (
        props["bootui.dev-services.log-tail-bytes"].get("defaultValueSource") == "BootUiProperties.java:4 (64 * 1024)"
    )
    assert props["bootui.cli.instances-dir"].get("defaultValueSource") == "BootUiProperties.java:9"
    assert props["bootui.cli.max-results"]["defaultValue"] == 200
    assert props["bootui.cli.max-results"].get("defaultValueSource") == "BootUiProperties.java:8"


def test_capture_tests_handles_windows_long_paths_and_arch_tests(tmp_path: Path) -> None:
    import os
    import shutil

    from scripts import capture_bootui

    bootui_root = tmp_path / "bootui"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rel = (
        "bootui-quarkus-integration-tests/datasource/src/test/java/io/github/jdubois/bootui/quarkus/it/"
        + ("deep_" * 20)
        + "/"
        + (" sub_" * 15).replace(" ", "")
        + "/DeepLongPathTest.java"
    )
    raw_target = bootui_root / rel
    win_root = Path("\\\\?\\" + os.path.abspath(str(bootui_root))) if os.name == "nt" else bootui_root
    win_target = Path("\\\\?\\" + os.path.abspath(str(raw_target))) if os.name == "nt" else raw_target
    try:
        win_target.parent.mkdir(parents=True, exist_ok=True)
        win_target.write_text(
            "package io.github.jdubois.bootui.deep;\n"
            "class DeepLongPathTest {\n"
            "    // @Test void commentedOut() {}\n"
            "    @Test\n"
            "    void standardTest() {}\n"
            "    public void helperNotATest() {}\n"
            "    @ArchTest\n"
            "    static final ArchRule layerRule = null;\n"
            "}\n",
            encoding="utf-8",
        )

        capture_bootui._capture_tests(str(bootui_root), str(out_dir))
        data = json.loads((out_dir / "bootui-tests.json").read_text(encoding="utf-8"))
        assert data["testClasses"] == {"io.github.jdubois.bootui.deep.DeepLongPathTest": ["layerRule", "standardTest"]}
    finally:
        shutil.rmtree(win_root, ignore_errors=True)
