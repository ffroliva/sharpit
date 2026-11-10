"""The user docs list every MCP tool, every setting and every extra, checked against sharpit's own registries.

Static: the tests read Markdown, ``pyproject.toml`` and the pinned BootUI 2.3.0 fixtures. They import ``sharpit`` only
to list what sharpit itself registers (tools, settings fields, panels), because that is what the docs must describe.
"""

from __future__ import annotations

import dataclasses
import json
import re
import tomllib
from pathlib import Path

from sharpit.engine.panels import PANELS
from sharpit.engine.tools import TOOLS
from sharpit.settings import SharpitSettings

ROOT = Path(__file__).resolve().parent.parent
USER_DOCS = ROOT / "website" / "docs"  # the user docs published at https://ffroliva.github.io/sharpit/
MCP_DOC = USER_DOCS / "mcp.md"
SETTINGS_DOC = USER_DOCS / "settings.md"
INSTALLATION_DOC = USER_DOCS / "installation.md"
SKILL = ROOT / "skills" / "sharpit" / "SKILL.md"
FIXTURES = ROOT / "tests" / "fixtures" / "bootui" / "2.3.0"

_TOKEN = re.compile(r"`([^`\n]+)`")
_HEADING = re.compile(r"^(#+)\s+(.*)$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fixture(name: str, key: str) -> list[dict[str, object]]:
    return json.loads(_read(FIXTURES / name))[key]


def _code_tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text))


def _actions_section(text: str) -> str:
    """The body of the heading that starts with ``Actions`` (any level), up to the next heading; empty if absent."""
    lines = text.splitlines()
    body: list[str] = []
    inside = False
    for line in lines:
        heading = _HEADING.match(line)
        if heading and inside:
            break
        if heading and heading.group(2).startswith("Actions"):
            inside = True
            continue
        if inside:
            body.append(line)
    return "\n".join(body)


def _without(text: str, section: str) -> str:
    return text.replace(section, "") if section else text


def test_every_tool_is_documented() -> None:
    boot = {str(t["name"]): bool(t["action"]) for t in _fixture("tools.json", "tools")}
    registry = {t.name: t.action for t in TOOLS}
    drift = sorted(n for n, action in registry.items() if n in boot and boot[n] != action)
    assert not drift, f"registry action flag differs from the pinned BootUI 2.3.0 tools.json: {drift}"

    problems: list[str] = []
    for doc in (MCP_DOC, SKILL):
        text = _read(doc)
        actions = _actions_section(text)
        in_actions = _code_tokens(actions)
        elsewhere = _code_tokens(_without(text, actions))
        read_missing = sorted(n for n, action in registry.items() if not action and n not in elsewhere)
        action_missing = sorted(n for n, action in registry.items() if action and n not in in_actions)
        label = doc.relative_to(ROOT).as_posix()
        if read_missing:
            problems.append(f"{label}: {len(read_missing)} read tools not documented: {read_missing}")
        if not actions:
            problems.append(f"{label}: no 'Actions' section for the {sum(registry.values())} action tools")
        elif action_missing:
            problems.append(f"{label}: {len(action_missing)} action tools not listed under Actions: {action_missing}")
    assert not problems, "\n".join(problems)


def _documented_envs(text: str) -> set[str]:
    return {t for t in _code_tokens(text) if t.startswith("SHARPIT_")}


def test_every_setting_is_documented() -> None:
    text = _read(SETTINGS_DOC)
    tokens = _code_tokens(text)
    documented = _documented_envs(text)
    fields = [f.name for f in dataclasses.fields(SharpitSettings) if f.name not in {"warnings", "panels"}]
    expected = {f: "SHARPIT_" + f.upper() for f in fields}
    missing = sorted(env for env in expected.values() if env not in documented)
    assert not missing, f"{len(missing)} of {len(expected)} settings not in settings.md: {missing}"

    # the per-panel switches: one row template per flag, and every accepted panel id spelled in capitals
    templates = [f"SHARPIT_PANELS_<ID>_{flag}" for flag in ("ENABLED", "READ_ONLY")]
    missing_templates = [t for t in templates if t not in documented]
    assert not missing_templates, f"per-panel switches not in settings.md: {missing_templates}"
    panel_ids = [p.id.upper().replace("-", "_") for p in PANELS if p.implemented]
    missing_panels = sorted(pid for pid in panel_ids if pid not in tokens)
    assert not missing_panels, f"panel ids not listed for the per-panel switches in settings.md: {missing_panels}"

    # every BootUI 2.3.0 property that sharpit ports is documented under its sharpit name
    ported = {
        "SHARPIT_" + re.sub(r"[.-]", "_", str(p["name"]).removeprefix("bootui.")).upper()
        for p in _fixture("properties.json", "properties")
    } & set(expected.values())
    unported = sorted(ported - documented)
    assert not unported, f"ported BootUI 2.3.0 properties not in settings.md: {unported}"


# What an app brings itself: sharpit never imports these, it reads them from sys.modules or reads files. The panels are
# the ones that answer "unavailable" without the library (collectors and capture read ``sqla`` / ``otel`` / the
# pydantic-settings gatekeeper). Checked against PANELS below, so a renamed panel breaks the test.
OPTIONAL_LIBRARIES: dict[str, tuple[str, ...]] = {
    "SQLAlchemy": (
        "sql-trace",
        "sqlalchemy-statistics",
        "database-connection-pools",
        "data",
        "transactions",
        "database-advisor",
        "postgresql",
        "mysql",
    ),
    "OpenTelemetry": ("traces",),
    "pydantic-settings": ("config",),
}


def _table(text: str) -> list[list[str]]:
    """The rows (cells, header first) of the first table whose header names Panel, Library and Extra."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not rows and not {"Panel", "Library", "Extra"} <= set(cells):
            continue
        rows.append(cells)
    return [r for r in rows if not all(set(c) <= {"-", ":", " "} for c in r)]


def test_extras_table_matches_panels() -> None:
    pyproject = tomllib.loads(_read(ROOT / "pyproject.toml"))
    extras = set(pyproject["project"]["optional-dependencies"])
    rows = _table(_read(INSTALLATION_DOC))
    assert rows, "installation.md has no 'Panel | Library | Extra' table"

    header, body = rows[0], rows[1:]
    panel_col, library_col, extra_col = header.index("Panel"), header.index("Library"), header.index("Extra")
    listed: set[str] = set()
    for row in body:
        for token in _code_tokens(row[extra_col]):
            match = re.fullmatch(r"sharpit\[([^\]]+)\]", token)
            if match:
                listed.update(name.strip() for name in match.group(1).split(","))
    assert listed == extras, f"extras in the table {sorted(listed)} != pyproject optional-dependencies {sorted(extras)}"

    known = {p.id for p in PANELS}
    unknown = sorted({t for row in body for t in _code_tokens(row[panel_col]) if t not in known})
    assert not unknown, f"panel ids in the table that are not panels: {unknown}"

    missing: list[str] = []
    for library, panels in OPTIONAL_LIBRARIES.items():
        assert set(panels) <= known, f"{library}: not panels: {sorted(set(panels) - known)}"
        for panel in panels:
            rows_for_panel = [r for r in body if panel in _code_tokens(r[panel_col])]
            if not any(library in r[library_col] for r in rows_for_panel):
                missing.append(f"{panel} -> {library}")
    assert not missing, f"panels that need an optional library are not in the table: {missing}"


def test_tool_counts_in_docs_match_registry() -> None:
    reads = sum(not t.action for t in TOOLS)
    actions = sum(t.action for t in TOOLS)
    for doc in (MCP_DOC, SKILL):
        text = _read(doc)
        label = doc.relative_to(ROOT).as_posix()
        read_counts = {int(n) for n in re.findall(r"\b(\d+) (?:\*\*)?read(?:-only)?(?:\*\*)? tools", text)}
        action_counts = {int(n) for n in re.findall(r"\b(\d+) action tools", text)}
        assert read_counts == {reads}, f"{label}: read-tool counts {sorted(read_counts)}, registry has {reads}"
        assert action_counts == {actions}, (
            f"{label}: action-tool counts {sorted(action_counts)}, registry has {actions}"
        )


def test_actions_sections_state_the_read_only_refusal() -> None:
    for doc in (MCP_DOC, SKILL):
        actions = _actions_section(_read(doc))
        label = doc.relative_to(ROOT).as_posix()
        assert "SHARPIT_READ_ONLY" in actions, f"{label}: Actions section does not say global read-only refuses actions"
        assert "_READ_ONLY" in actions.replace("SHARPIT_READ_ONLY", ""), (
            f"{label}: Actions section omits the per-panel read-only refusal"
        )
