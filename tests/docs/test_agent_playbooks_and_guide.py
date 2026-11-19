"""Verify that every tool, command, rule and link the playbooks and guide cite exists and resolves.

# ported: AgentPlaybookTests.bothPayloadsDiscoverEveryStructuredPlaybook
# ported: AgentPlaybookTests.relativeSkillLinksStayInsideEachInstalledPayloadAndResolve
# ported: AgentPlaybookTests.documentedToolTablesUseRealCatalogToolsAndCliPaths
# ported: AgentPlaybookTests.optionGuardRejectsFlagsNotSupportedByTheToolSchema
# derived: PlaybookAndGuideToolCitationsTests
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from sharpit.cli.commands import _build_root_parser
from sharpit.cli.manifest import Manifest
from sharpit.engine.tools import TOOLS, Tool

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOKS_DIR = ROOT / "skills" / "sharpit" / "references" / "playbooks"
REFERENCES_DIR = ROOT / "skills" / "sharpit" / "references"
AI_AGENTS_DOC = ROOT / "website" / "docs" / "ai-agents.md"

PLAYBOOKS = [
    "application-checkup",
    "database-efficiency",
    "slow-endpoint",
    "errors-and-hidden-failures",
    "verify-my-changes",
    "python-performance-and-memory",
]

VALID_TOOLS: set[str] = {t.name for t in TOOLS}
TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}

TOOL_PREFIXES = ("get_", "enable_", "disable_", "clear_", "record_")
TOOL_SUFFIXES = ("_scan", "_report", "_read")
ALLOW_LIST: dict[str, str] = {
    # Non-tool identifiers matching tool prefix/suffix conventions that appear in docs
}

LINK_PATTERN = re.compile(r"\[[^\]\n]+\]\(([^)\s]+)\)")
SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:.*")
TOOL_ROW_PATTERN = re.compile(r"^\|\s*`([a-z][a-z0-9_]+)`\s*\|\s*`sharpit\s+([^`]+)`", re.MULTILINE)
CLI_OPTION_PATTERN = re.compile(r"--([a-z][a-z-]+)")
RULE_ID_PATTERN = re.compile(r"\b[A-Z]+(?:-[A-Z0-9]+)+-\d{3}\b")

GLOBAL_CLI_FLAGS = {"json", "url", "token", "transport", "api-path", "timeout", "fail-on"}


def _collect_all_registered_rule_ids() -> set[str]:
    rule_ids: set[str] = set()

    from sharpit.engine.collectors.architecture.report import RULES as arch_rules

    for r in arch_rules:
        rule_ids.add(r.id if hasattr(r, "id") else (r.definition.id if hasattr(r, "definition") else str(r)))

    from sharpit.engine.collectors.database_advisor.report import RULES as db_rules

    for r in db_rules:
        rule_ids.add(r.id if hasattr(r, "id") else (r.definition.id if hasattr(r, "definition") else str(r)))

    from sharpit.engine.collectors.fastapi_advisor.report import RULES as fa_rules

    for r in fa_rules:
        rule_ids.add(r.id if hasattr(r, "id") else (r.definition.id if hasattr(r, "definition") else str(r)))

    from sharpit.engine.collectors.restapi.rules import RULE_IDS as ra_rule_ids
    from sharpit.engine.collectors.restapi.rules import RULES as ra_rules

    for r in ra_rules:
        rule_ids.add(r.id if hasattr(r, "id") else (r.definition.id if hasattr(r, "definition") else str(r)))
    rule_ids.update(ra_rule_ids)

    from sharpit.engine.collectors.security.report import RULES as sec_rules

    for r in sec_rules:
        rule_ids.add(r.id if hasattr(r, "id") else (r.definition.id if hasattr(r, "definition") else str(r)))

    return rule_ids


ALL_REGISTERED_RULE_IDS: set[str] = _collect_all_registered_rule_ids()


def get_playbook_and_doc_files() -> list[Path]:
    files = [
        ROOT / "skills" / "sharpit" / "SKILL.md",
        *sorted(REFERENCES_DIR.rglob("*.md")),
        ROOT / "plugins" / "sharpit" / "skills" / "sharpit" / "SKILL.md",
        *sorted((ROOT / "plugins" / "sharpit" / "skills" / "sharpit" / "references").rglob("*.md")),
    ]
    if AI_AGENTS_DOC.is_file():
        files.append(AI_AGENTS_DOC)
    return files


def _heading_id(heading: str) -> str:
    cleaned = re.sub(r"^#+\s+", "", heading).lower().strip()
    cleaned = re.sub(r"[^\w\s-]", "", cleaned)
    return re.sub(r"\s+", "-", cleaned)


def _looks_like_tool(ident: str) -> bool:
    return ident.startswith(TOOL_PREFIXES) or ident.endswith(TOOL_SUFFIXES)


def _extract_backticked_tools(text: str) -> set[str]:
    tools: set[str] = set()
    for m in re.finditer(r"`([a-zA-Z0-9_]+)`", text):
        ident = m.group(1)
        if _looks_like_tool(ident):
            tools.add(ident)
    return tools


def _extract_table_tools(text: str) -> set[str]:
    tools: set[str] = set()
    in_table = False
    tool_col_idx = -1
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            in_table = False
            tool_col_idx = -1
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not in_table:
            for idx, c in enumerate(cells):
                if c.lower() in ("tool", "mcp tool", "mcp tools", "tool name"):
                    tool_col_idx = idx
                    in_table = True
                    break
        elif not all(set(c).issubset({"-", ":", " "}) for c in cells) and 0 <= tool_col_idx < len(cells):
            val = cells[tool_col_idx].strip("`").strip()
            if re.match(r"^[a-z][a-z0-9_]+$", val):
                tools.add(val)
    return tools


def extract_cited_mcp_tools(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return _extract_backticked_tools(text) | _extract_table_tools(text)


def extract_cited_sharpit_commands(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"`sharpit\s+([^`]+)`", text)


def normalize_command_for_parsing(cmd: str) -> list[str]:
    normalized = cmd.strip()
    if normalized in ("--help", "<command> --help"):
        return ["--help"]

    replacements = {
        "<id>": "dummy-id",
        "<scan-id>": "dummy-scan-id",
        "<route>": "/api/test",
        "<name>": "dummy-name",
        "<url>": "http://127.0.0.1:8000",
        "<action>": "scan",
    }
    for placeholder, val in replacements.items():
        normalized = normalized.replace(placeholder, val)

    return shlex.split(normalized)


def resolve_command_to_tool(cmd_str: str, manifest: Manifest) -> str | None:
    parts = shlex.split(cmd_str)
    if parts and parts[0] == "sharpit":
        parts = parts[1:]
    specs = sorted(manifest.command_specs, key=lambda x: len(x[0]), reverse=True)
    for path, tool in specs:
        if len(parts) >= len(path) and tuple(parts[: len(path)]) == path:
            return tool.name
    return None


def assert_command_options(tool_name: str, command: str) -> None:
    tool = TOOLS_BY_NAME.get(tool_name)
    assert tool is not None, f"Unknown tool {tool_name}"
    tool_properties = set(tool.input_schema.get("properties", {}).keys())
    for option in CLI_OPTION_PATTERN.findall(command):
        if option in GLOBAL_CLI_FLAGS:
            continue
        argument = "scanId" if option == "scan-id" else option
        assert argument in tool_properties, (
            f"sharpit {command} uses --{option}, which {tool_name} does not advertise in {tool_properties}"
        )


def test_playbook_files_exist() -> None:
    expected_playbooks = [
        "README.md",
        "application-checkup.md",
        "database-efficiency.md",
        "slow-endpoint.md",
        "errors-and-hidden-failures.md",
        "verify-my-changes.md",
        "python-performance-and-memory.md",
    ]
    for pb in expected_playbooks:
        assert (PLAYBOOKS_DIR / pb).is_file(), f"Missing playbook {pb}"
    assert AI_AGENTS_DOC.is_file(), "Missing website/docs/ai-agents.md"


# ported: AgentPlaybookTests.bothPayloadsDiscoverEveryStructuredPlaybook
def test_both_payloads_discover_every_structured_playbook() -> None:
    for root_path in [ROOT / "skills" / "sharpit", ROOT / "plugins" / "sharpit" / "skills" / "sharpit"]:
        skill_text = (root_path / "SKILL.md").read_text(encoding="utf-8")
        index_text = (root_path / "references" / "playbooks" / "README.md").read_text(encoding="utf-8")
        for playbook in PLAYBOOKS:
            assert f"(references/playbooks/{playbook}.md)" in skill_text, f"{root_path} SKILL.md missing {playbook}"
            assert f"({playbook}.md)" in index_text, f"{root_path} README.md missing {playbook}"
            playbook_path = root_path / "references" / "playbooks" / f"{playbook}.md"
            assert playbook_path.is_file(), f"Missing {playbook_path}"
            content = playbook_path.read_text(encoding="utf-8")
            for section in [
                "## Goal and entry",
                "## Prerequisites",
                "## Investigation",
                "## Fix and verify",
                "## Stop and report",
                "(README.md)",
            ]:
                assert section in content, f"{root_path.name}/{playbook} must contain '{section}'"


# ported: AgentPlaybookTests.relativeSkillLinksStayInsideEachInstalledPayloadAndResolve
def test_relative_skill_links_stay_inside_each_installed_payload_and_resolve() -> None:
    for root_str in ["skills/sharpit", "plugins/sharpit/skills/sharpit"]:
        skill_dir = (ROOT / root_str).resolve()
        for md_file in sorted(skill_dir.rglob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            for m in LINK_PATTERN.finditer(content):
                link = m.group(1)
                if SCHEME_PATTERN.match(link):
                    continue
                parts = link.split("#", 1)
                target_path = md_file if not parts[0] else (md_file.parent / parts[0]).resolve()
                assert target_path.is_relative_to(skill_dir), (
                    f"{md_file.relative_to(ROOT)} links to {link} outside the installed skill"
                )
                assert target_path.is_file(), f"{md_file.relative_to(ROOT)} links to missing file {link}"
                if len(parts) == 2 and parts[1]:
                    heading_slug = parts[1]
                    headings = [
                        _heading_id(line)
                        for line in target_path.read_text(encoding="utf-8").splitlines()
                        if line.startswith("#")
                    ]
                    assert heading_slug in headings, (
                        f"{md_file.relative_to(ROOT)} links to missing heading #{heading_slug} in {target_path.name}"
                    )


# derived: AgentPlaybookTests.relativeSkillLinksStayInsideEachInstalledPayloadAndResolve
@pytest.mark.parametrize("file_path", get_playbook_and_doc_files(), ids=lambda p: p.name)
def test_every_relative_markdown_link_resolves_to_file(file_path: Path) -> None:
    content = file_path.read_text(encoding="utf-8")
    for m in LINK_PATTERN.finditer(content):
        link = m.group(1)
        if SCHEME_PATTERN.match(link):
            continue
        parts = link.split("#", 1)
        target = file_path if not parts[0] else (file_path.parent / parts[0]).resolve()
        assert target.is_file(), f"{file_path.name} links to nonexistent target: {link}"
        if len(parts) == 2 and parts[1]:
            heading_slug = parts[1]
            headings = [
                _heading_id(line) for line in target.read_text(encoding="utf-8").splitlines() if line.startswith("#")
            ]
            assert heading_slug in headings, (
                f"{file_path.name} links to missing heading #{heading_slug} in {target.name}"
            )


# ported: AgentPlaybookTests.documentedToolTablesUseRealCatalogToolsAndCliPaths
def test_documented_tool_tables_use_real_catalog_tools_and_cli_paths() -> None:
    manifest = Manifest.bundled()
    playbooks_dir = ROOT / "skills" / "sharpit" / "references" / "playbooks"
    for playbook in PLAYBOOKS:
        playbook_path = playbooks_dir / f"{playbook}.md"
        text = playbook_path.read_text(encoding="utf-8")
        matches = TOOL_ROW_PATTERN.findall(text)
        assert matches, f"{playbook} must provide concrete MCP/CLI entry points"
        for tool, command in matches:
            assert tool in VALID_TOOLS, f"{playbook} names unknown tool {tool}"
            resolved = resolve_command_to_tool(command, manifest)
            assert resolved == tool, (
                f"{playbook} must map {tool} to its CLI command, got {command} resolving to {resolved}"
            )
            assert_command_options(tool, command)


# ported: AgentPlaybookTests.optionGuardRejectsFlagsNotSupportedByTheToolSchema
def test_option_guard_rejects_flags_not_supported_by_the_tool_schema() -> None:
    assert_command_options("get_http_routes", "http routes --limit 20 --json")
    assert_command_options("get_agent_status", "agent status --query files --json")
    with pytest.raises(AssertionError):
        assert_command_options("get_http_routes", "http routes --query orders --json")
    with pytest.raises(AssertionError):
        assert_command_options("get_agent_status", "agent status --limit 20 --json")


# derived: PlaybookAndGuideToolCitationsTests.test_all_cited_mcp_tools_exist_in_engine_catalog
@pytest.mark.parametrize("file_path", get_playbook_and_doc_files(), ids=lambda p: p.name)
def test_all_cited_mcp_tools_exist_in_engine_catalog(file_path: Path) -> None:
    cited_tools = extract_cited_mcp_tools(file_path)
    assert cited_tools, f"No MCP tools detected in {file_path.name}"
    unknown = cited_tools - (VALID_TOOLS | ALLOW_LIST.keys())
    assert not unknown, f"File {file_path.name} cites unknown MCP tools: {sorted(unknown)}"


# derived: PlaybookAndGuideToolCitationsTests.test_all_table_tool_command_pairs_resolve_to_same_tool
@pytest.mark.parametrize("file_path", get_playbook_and_doc_files(), ids=lambda p: p.name)
def test_all_table_tool_command_pairs_resolve_to_same_tool(file_path: Path) -> None:
    manifest = Manifest.bundled()
    mismatches: list[str] = []
    text = file_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "|" in line and "sharpit " in line:
            b_items = re.findall(r"`([^`]+)`", line)
            tools_in_row = [x for x in b_items if x in TOOLS_BY_NAME]
            cmds_in_row = [x for x in b_items if x.startswith("sharpit ")]
            if tools_in_row and cmds_in_row:
                for tool in tools_in_row:
                    for cmd in cmds_in_row:
                        resolved = resolve_command_to_tool(cmd, manifest)
                        if resolved != tool:
                            mismatches.append(f"{tool} -> {cmd} (resolved to {resolved})")
    assert not mismatches, f"Mismatched tool/command pairs in {file_path.name}: {mismatches}"


# derived: PlaybookAndGuideToolCitationsTests.test_all_cited_cli_commands_parse
@pytest.mark.parametrize("file_path", get_playbook_and_doc_files(), ids=lambda p: p.name)
def test_all_cited_cli_commands_parse(file_path: Path) -> None:
    cited_commands = extract_cited_sharpit_commands(file_path)
    assert cited_commands, f"No sharpit commands detected in {file_path.name}"
    parser, _ = _build_root_parser(manifest=Manifest.bundled())

    failed_commands: list[tuple[str, str]] = []
    for raw_cmd in cited_commands:
        tokens = normalize_command_for_parsing(raw_cmd)
        if tokens == ["--help"]:
            continue
        try:
            parser.parse_args(tokens)
        except SystemExit as exc:
            failed_commands.append((raw_cmd, str(exc)))
        except Exception as exc:  # noqa: BLE001
            failed_commands.append((raw_cmd, str(exc)))

    assert not failed_commands, f"Failed to parse CLI commands in {file_path.name}: {failed_commands}"


# derived: PlaybookAndGuideToolCitationsTests.test_all_cited_rule_ids_exist_in_rule_registries
@pytest.mark.parametrize("file_path", get_playbook_and_doc_files(), ids=lambda p: p.name)
def test_all_cited_rule_ids_exist_in_rule_registries(file_path: Path) -> None:
    text = file_path.read_text(encoding="utf-8")
    rule_ids = set(RULE_ID_PATTERN.findall(text))
    if not rule_ids:
        return
    unknown = rule_ids - ALL_REGISTERED_RULE_IDS
    assert not unknown, f"File {file_path.name} cites unknown rule ids: {sorted(unknown)}"
