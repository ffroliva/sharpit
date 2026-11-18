import json
import re
from pathlib import Path

from sharpit.cli.manifest import Manifest
from sharpit.engine.tools import COMMANDS, TOOLS
from scripts.dev.gen_cli_manifest import generate

# ported: ToolManifestGeneratorTests.everyCatalogToolHasACommandPath
def test_every_tool_has_a_command_path():
    assert set(COMMANDS) == {tool.name for tool in TOOLS}

# ported: ToolManifestGeneratorTests.advisorDetailsProjectRequiredIdSnapshotAndPagingFlags
def test_rule_violations_flags():
    assert Manifest.bundled().by_name("get_rest_api_rule_violations").flags == ("id", "scan-id", "offset", "limit")

# ported: ToolManifestGeneratorTests.agentStatusTakesAQueryButNoLimitBecauseItListsEveryMatchingSensor
def test_agent_status_takes_query_without_limit():
    assert Manifest.bundled().by_name("get_agent_status").flags == ("query",)

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

# ported: ToolManifestGeneratorTests.theCheckedInManifestMatchesTheCatalog
def test_manifest_matches_generation():
    assert (Path(__file__).parents[2] / "src/sharpit/cli/tools.json").read_text(encoding="utf-8") == generate()

# ported: ToolManifestGeneratorTests.theBundledManifestDescribesEveryToolTheCatalogDeclares
def test_bundled_describes_every_tool():
    manifest = Manifest.bundled()
    assert {t.name for t in manifest.tools} == {t.name for t in TOOLS}
    for source in TOOLS:
        item = manifest.by_name(source.name)
        assert (item.panel, item.action, item.description) == (source.panel, source.action, source.description)

# ported: ToolManifestGeneratorTests.theManifestRecordsStackSpecificToolsSoHelpCanSaySo
def test_manifest_has_every_tool_command():
    assert all(Manifest.bundled().by_name(t.name).command == COMMANDS[t.name] for t in TOOLS)

def test_bootui_paths_are_preserved():
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/bootui/2.3.0/tools.json").read_text(encoding="utf-8"))
    by_name = {item["name"]: item["command"] for item in fixture}
    for tool in TOOLS:
        if tool.name in by_name:
            assert COMMANDS[tool.name] == by_name[tool.name]
