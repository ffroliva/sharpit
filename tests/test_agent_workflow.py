"""The agent workflow wiring: every /sharpit:* command reads a skill that exists, and no foreign command survives."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = sorted((ROOT / ".claude" / "commands" / "sharpit").glob("*.md"))
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))
SKILL_REF = r"(?<![\w/.~-])skills/([a-z0-9-]+)/SKILL\.md"  # repo-relative only, not ~/.agents/skills/...


def test_workflow_files_exist() -> None:
    assert COMMANDS, "no /sharpit:* commands found"
    assert SKILLS, "no skills found"


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.stem)
def test_command_reads_an_existing_skill(command: Path) -> None:
    targets = re.findall(SKILL_REF, command.read_text(encoding="utf-8"))
    assert targets, f"{command.name} does not point at a skills/<name>/SKILL.md"
    for name in targets:
        assert (ROOT / "skills" / name / "SKILL.md").is_file(), f"{command.name} -> missing skills/{name}/SKILL.md"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skill_frontmatter_name_matches_directory(skill: Path) -> None:
    text = skill.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{skill} has no frontmatter"
    name = re.search(r"^name:\s*(\S+)\s*$", match.group(1), re.MULTILINE)
    assert name
    assert name.group(1) == skill.parent.name


BANNED = ("/gflow:", "origin/develop", "reCAPTCHA", "Sonar")


def test_no_foreign_command_namespace() -> None:
    files = [*COMMANDS, *SKILLS, ROOT / ".claude" / "README.md", ROOT / "skills" / "README.md"]
    files += [p for p in (ROOT / "AGENTS.md", ROOT / "CLAUDE.md", ROOT / "GEMINI.md") if p.is_file()]
    files += sorted((ROOT / "docs").rglob("*.md"))
    offenders = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if path.name == "README.md" and path.parent.name == "skills" and line.startswith("| "):
                continue  # the provenance table names what was dropped, on purpose
            offenders += [f"{path.relative_to(ROOT)}:{number}: {word}" for word in BANNED if word in line]
    assert offenders == []


def test_agents_index_matches_commands() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    index = text.split("## Skills index", 1)[1].split("\n## ", 1)[0]
    listed = {
        name
        for row in index.splitlines()
        if row.startswith("| `")
        for name in re.findall(r"`([a-z-]+)`", row.split("|")[1])
    }
    assert listed == {p.stem for p in COMMANDS}
