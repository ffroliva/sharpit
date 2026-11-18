import re

from bootui_tools import BOOTUI
from sharpit.cli.manifest import Manifest
from sharpit.engine.tools import COMMANDS, TOOLS


def _tool(name: str):
    tool = Manifest.bundled().by_name(name)
    assert tool is not None
    return tool


# ported: ToolManifestGeneratorTests.everyCatalogToolHasACommandPath
def test_every_tool_has_a_command_path():
    assert set(COMMANDS) == {tool.name for tool in TOOLS}


# ported: ToolManifestGeneratorTests.advisorDetailsProjectRequiredIdSnapshotAndPagingFlags
def test_rule_violations_project_required_id_snapshot_and_paging_flags():
    tools = [tool for tool in Manifest.bundled().tools if tool.schema == "RULE_VIOLATIONS"]
    assert len(tools) == 5
    for tool in tools:
        assert tool.takes_id, tool.name
        assert tool.takes_scan_id, tool.name
        assert tool.takes_offset, tool.name
        assert tool.takes_limit, tool.name
        assert not tool.takes_query, tool.name
        assert tool.command.endswith(" violations"), tool.name
        assert not tool.action, tool.name
        assert tool.arguments == ("id", "scanId", "offset", "limit"), tool.name
        assert tool.required == ("id", "scanId"), tool.name


# ported: ToolManifestGeneratorTests.agentStatusTakesAQueryButNoLimitBecauseItListsEveryMatchingSensor
# The description words BootUI asserts ("overflow", "another request's context") are the Java agent's; sharpit's
# description names the sensors it has, so the check is on the schema and the description text itself.
def test_agent_status_takes_a_query_but_no_limit():
    status = _tool("get_agent_status")
    assert status.schema == "QUERY"
    assert status.takes_query
    assert not status.takes_limit
    assert "Query with a sensor id" in status.description
    assert status.description == next(tool.description for tool in TOOLS if tool.name == "get_agent_status")


# ported: ToolManifestGeneratorTests.noTwoToolsShareACommandPath
def test_paths_unique():
    paths = [tool.command for tool in Manifest.bundled().tools]
    assert len(paths) == len(set(paths))


# ported: ToolManifestGeneratorTests.noCommandPathIsAPrefixOfAnotherSoEveryLeafIsReachable
def test_no_path_prefixes():
    paths = [tool.command for tool in Manifest.bundled().tools]
    assert not any(other.startswith(path + " ") for path in paths for other in paths)


# ported: ToolManifestGeneratorTests.noCommandPathShadowsABuiltInCommand
def test_no_path_shadows_builtins():
    builtins = ("tools", "mcp", "help", "--version")
    assert not any(p == b or p.startswith(b + " ") for p in COMMANDS.values() for b in builtins)


# ported: ToolManifestGeneratorTests.commandPathsUseOnlyCharactersAShellDoesNotNeedQuotedFor
def test_paths_need_no_shell_quotes():
    assert all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*(?: [a-z0-9]+(?:-[a-z0-9]+)*)*", p) for p in COMMANDS.values())


# ported: ToolManifestGeneratorTests.theBundledManifestDescribesEveryToolTheCatalogDeclares
def test_bundled_describes_every_tool():
    manifest = Manifest.bundled()
    assert {t.name for t in manifest.tools} == {t.name for t in TOOLS}
    for source in TOOLS:
        item = _tool(source.name)
        assert (item.panel, item.action, item.description) == (source.panel, source.action, source.description)
        assert item.summary.strip(), source.name
        assert item.description.startswith(item.summary), source.name


# theManifestRecordsStackSpecificToolsSoHelpCanSaySo is not ported: sharpit has one stack, so the manifest records
# none (deviation row "manifest stacks" in docs/reference/matrix-updates/cli-t4.tsv).


def test_unknown_tool_name_is_none():
    assert Manifest.bundled().by_name("no_such_tool") is None


def test_bundled_manifest_is_loaded_once():
    assert Manifest.bundled() is Manifest.bundled()


def test_bootui_paths_are_preserved():
    for tool in TOOLS:
        if tool.name in BOOTUI:
            assert COMMANDS[tool.name] == BOOTUI[tool.name]["command"], tool.name


def test_exact_name_tools_carry_bootui_schema():
    for name, oracle in BOOTUI.items():
        if name in COMMANDS:
            assert _tool(name).schema == oracle["schema"], name
