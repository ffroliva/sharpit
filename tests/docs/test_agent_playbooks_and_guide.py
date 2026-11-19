"""Verify that every MCP tool name and CLI command cited in agent playbooks and docs exists and parses.

# ported: PlaybookAndGuideToolCitationsTests
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from sharpit.cli.commands import _build_root_parser
from sharpit.cli.manifest import Manifest
from sharpit.engine.tools import TOOLS

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOKS_DIR = ROOT / "skills" / "sharpit" / "references" / "playbooks"
REFERENCES_DIR = ROOT / "skills" / "sharpit" / "references"
AI_AGENTS_DOC = ROOT / "website" / "docs" / "ai-agents.md"

VALID_TOOLS = {t.name for t in TOOLS}


def get_playbook_and_doc_files() -> list[Path]:
    files = sorted(REFERENCES_DIR.rglob("*.md"))
    files.extend(sorted((ROOT / "plugins" / "sharpit" / "skills" / "sharpit").rglob("*.md")))
    files.append(ROOT / "skills" / "sharpit" / "SKILL.md")
    if AI_AGENTS_DOC.is_file():
        files.append(AI_AGENTS_DOC)
    return files


def extract_cited_mcp_tools(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    tools: set[str] = set()

    # 1. Extract from markdown tables with MCP tool column: | `tool_name` | `sharpit ...` |
    table_matches = re.findall(r"\|\s*`([a-z0-9_]+)`\s*\|\s*`sharpit\s+", text)
    tools.update(table_matches)

    # 2. Extract explicitly backticked tool-style identifiers that match tool naming conventions
    candidate_matches = re.findall(
        r"`(get_[a-z0-9_]+|[a-z0-9_]+_scan|[a-z0-9_]+_report|[a-z0-9_]+_read|enable_[a-z0-9_]+|disable_[a-z0-9_]+)`",
        text,
    )
    tools.update(candidate_matches)
    return tools


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
    }
    for placeholder, val in replacements.items():
        normalized = normalized.replace(placeholder, val)

    return shlex.split(normalized)


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


@pytest.mark.parametrize("file_path", get_playbook_and_doc_files(), ids=lambda p: p.name)
def test_all_cited_mcp_tools_exist_in_engine_catalog(file_path: Path) -> None:
    cited_tools = extract_cited_mcp_tools(file_path)
    assert cited_tools, f"No MCP tools detected in {file_path.name}"
    unknown = cited_tools - VALID_TOOLS
    assert not unknown, f"File {file_path.name} cites unknown MCP tools: {sorted(unknown)}"


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
