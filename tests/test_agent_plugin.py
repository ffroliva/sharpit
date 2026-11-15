"""The agent plugin payload: ``plugins/sharpit``, advertised through a Claude Code, Cursor and Codex marketplace.

BootUI ships the same way: Agent Plugins 1.0.0 manifests (``plugin.json`` + ``mcp.json``) for Cursor and compatible
clients, a Claude Code manifest under ``.claude-plugin/``, and a byte-identical copy of the user-facing skill.

# ported: ClaudeCodePluginPayloadTests.shippedSkillMatchesTheCanonicalSkill
# ported: ClaudeCodePluginPayloadTests.pluginShipsOnlyTheUserFacingSkill
# ported: AgentPluginPayloadTests (manifest shape)
"""

import json
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

import sharpit

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "sharpit"
CLAUDE_MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
CURSOR_MARKETPLACE = ROOT / ".cursor-plugin" / "marketplace.json"
CODEX_MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
AGENT_PLUGIN = PLUGIN / "plugin.json"
CLAUDE_PLUGIN = PLUGIN / ".claude-plugin" / "plugin.json"
MCP_JSON = PLUGIN / "mcp.json"
CANONICAL_SKILL = ROOT / "skills" / "sharpit"
SHIPPED_SKILL = PLUGIN / "skills" / "sharpit"
LOOPBACK = {"127.0.0.1", "localhost"}


def load(path: Path) -> dict[str, Any]:
    assert path.is_file(), f"missing {path.relative_to(ROOT)}"
    return json.loads(path.read_text(encoding="utf-8"))


def files_under(directory: Path) -> dict[str, bytes]:
    assert directory.is_dir(), f"missing {directory.relative_to(ROOT)}"
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in sorted(directory.rglob("*")) if p.is_file()}


@pytest.mark.parametrize("marketplace", [CLAUDE_MARKETPLACE, CURSOR_MARKETPLACE], ids=["claude", "cursor"])
def test_marketplace_advertises_the_plugin_directory(marketplace: Path) -> None:
    data = load(marketplace)
    entry = data["plugins"][0]
    assert data["name"] == "sharpit"
    assert entry["name"] == "sharpit"
    assert entry["source"] == "./plugins/sharpit"
    assert (ROOT / entry["source"]).is_dir()
    assert entry["category"] == "Developer Tools"


@pytest.mark.parametrize("manifest", [AGENT_PLUGIN, CLAUDE_PLUGIN], ids=["agent-plugins", "claude"])
def test_plugin_manifest_names_the_project(manifest: Path) -> None:
    data = load(manifest)
    assert data["name"] == "sharpit"
    assert data["license"] == "Apache-2.0"
    assert data["repository"] == "https://github.com/ffroliva/sharpit"
    assert data["description"]


@pytest.mark.parametrize("manifest", [AGENT_PLUGIN, CLAUDE_PLUGIN], ids=["agent-plugins", "claude"])
def test_manifest_version_matches_the_package(manifest: Path) -> None:
    # The Agent Plugins schema requires a version; src/sharpit/__init__.py stays the source (AGENTS.md).
    assert load(manifest)["version"] == sharpit.__version__


@pytest.mark.parametrize("path", [CLAUDE_MARKETPLACE, CURSOR_MARKETPLACE, CODEX_MARKETPLACE])
def test_no_other_file_carries_a_version(path: Path) -> None:
    data = load(path)
    assert "version" not in data
    assert all("version" not in entry for entry in data.get("plugins", []))


def test_codex_marketplace_advertises_the_plugin_directory() -> None:
    data = load(CODEX_MARKETPLACE)
    entry = data["plugins"][0]
    assert entry["name"] == "sharpit"
    assert entry["source"] == {"source": "local", "path": "./plugins/sharpit"}
    assert (ROOT / entry["source"]["path"]).is_dir()
    assert entry["category"] == "Developer Tools"


def test_agent_plugins_mcp_points_at_the_local_endpoint() -> None:
    server = load(MCP_JSON)["mcpServers"]["sharpit"]
    url = urlsplit(str(server["url"]))
    assert server["type"] == "streamable-http"
    assert url.hostname in LOOPBACK
    assert url.path == "/sharpit/api/mcp"


def test_claude_mcp_defaults_to_the_local_endpoint_and_allows_an_override() -> None:
    server = load(CLAUDE_PLUGIN)["mcpServers"]["sharpit"]
    assert server["type"] == "http"
    assert server["url"].startswith("${SHARPIT_MCP_URL:-http://127.0.0.1:")
    assert server["url"].endswith("/sharpit/api/mcp}")


@pytest.mark.parametrize("path", [MCP_JSON, CLAUDE_PLUGIN])
def test_mcp_config_holds_no_credentials(path: Path) -> None:
    assert path.is_file(), f"missing {path.relative_to(ROOT)}"
    text = path.read_text(encoding="utf-8").lower()
    for word in ("authorization", "bearer", "token", "headers", "secret"):
        assert word not in text


def test_shipped_skill_matches_the_canonical_skill() -> None:
    assert files_under(SHIPPED_SKILL) == files_under(CANONICAL_SKILL)


def test_plugin_ships_only_the_user_facing_skill() -> None:
    assert (PLUGIN / "skills").is_dir(), "missing plugins/sharpit/skills"
    skills = {p.name for p in (PLUGIN / "skills").iterdir()}
    assert skills == {"sharpit"}


def test_plugin_directory_is_not_in_the_wheel() -> None:
    wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"][
        "wheel"
    ]
    assert wheel["packages"] == ["src/sharpit"]
    assert all(pattern.startswith("src/sharpit") for pattern in wheel["include"])


def test_skill_banner_names_the_current_version() -> None:
    first_lines = (CANONICAL_SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()[:14]
    assert f"> **{sharpit.__version__}.**" in " ".join(first_lines)
