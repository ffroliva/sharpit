"""Tests for community and contributor files (lane P1).

Asserts existence and structure of:
- CONTRIBUTING.md
- CODE_OF_CONDUCT.md
- .github/PULL_REQUEST_TEMPLATE.md
- .github/ISSUE_TEMPLATE/bug_report.yml
- .github/ISSUE_TEMPLATE/feature_request.yml
- .github/ISSUE_TEMPLATE/config.yml

Lane ordering note: Lane P2 introduces .github/workflows/dco.yml enforcing
DCO sign-off on pull requests. P2 merges before lane P1.
test_contributing_dco_workflow_documented verifies CONTRIBUTING.md documents
the workflow only when .github/workflows/dco.yml exists and contains Signed-off-by.
On branch docs/0.8.0-p1, test_contributing_dco_workflow_documented is expected
to fail until lane P2 is merged in.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

import pytest

ROOT = Path(__file__).resolve().parents[1]

COMMUNITY_FILES = [
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
]

ISSUE_FORMS = [
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
]

COC_HEADINGS = [
    "Our Pledge",
    "Our Standards",
    "Enforcement Responsibilities",
    "Scope",
    "Enforcement",
    "Enforcement Guidelines",
    "Correction",
    "Warning",
    "Temporary Ban",
    "Permanent Ban",
    "Attribution",
]

FORBIDDEN_WORDS = (
    "Co" + "-Authored-By",
    "Cl" + "aude",
    "Co" + "dex",
    "Ge" + "mini",
    "Anti" + "gravity",
)

VALID_ITEM_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}


class FormItem(TypedDict):
    type: str
    id: str | None
    label: str | None


class ParsedForm(TypedDict):
    has_top_name: bool
    has_top_description: bool
    has_top_body: bool
    items: list[FormItem]


def _parse_issue_form(path: Path) -> ParsedForm:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    has_top_name = any(re.match(r"^name:\s*\S+", line) for line in lines)
    has_top_desc = any(re.match(r"^description:\s*\S+", line) for line in lines)
    has_top_body = any(re.match(r"^body:\s*$", line) for line in lines)

    item_chunks: list[list[str]] = []
    current_chunk: list[str] = []
    in_body = False
    for line in lines:
        if re.match(r"^body:\s*$", line):
            in_body = True
            continue
        if in_body:
            if re.match(r"^\s*-\s*type:\s*", line):
                if current_chunk:
                    item_chunks.append(current_chunk)
                current_chunk = [line]
            elif current_chunk:
                if re.match(r"^\s+", line) or not line.strip():
                    current_chunk.append(line)
                else:
                    item_chunks.append(current_chunk)
                    current_chunk = []
                    in_body = False
    if current_chunk:
        item_chunks.append(current_chunk)

    items: list[FormItem] = []
    for chunk in item_chunks:
        chunk_text = "\n".join(chunk)
        type_match = re.search(r"^\s*-\s*type:\s*(\S+)", chunk_text, re.MULTILINE)
        item_type = type_match.group(1) if type_match else ""
        id_match = re.search(r"^\s+id:\s*(\S+)", chunk_text, re.MULTILINE)
        item_id = id_match.group(1) if id_match else None
        label_match = re.search(r"^\s+label:\s*(.+)", chunk_text, re.MULTILINE)
        item_label = label_match.group(1).strip() if label_match else None
        items.append({"type": item_type, "id": item_id, "label": item_label})

    return {
        "has_top_name": has_top_name,
        "has_top_description": has_top_desc,
        "has_top_body": has_top_body,
        "items": items,
    }


def _contributing_paths() -> list[str]:
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    inline = re.findall(r"(?<!`)`([^`\n]+)`(?!`)", text)
    return [
        t.strip()
        for t in inline
        if not any(c in t for c in " <>\n")
        and ("/" in t or any(t.endswith(ext) for ext in [".md", ".py", ".yml", ".toml", "/"]))
    ]


@pytest.mark.parametrize("rel_path", COMMUNITY_FILES)
def test_community_file_exists(rel_path: str) -> None:
    path = ROOT / rel_path
    assert path.is_file()


def test_code_of_conduct_contents() -> None:
    path = ROOT / "CODE_OF_CONDUCT.md"
    text = path.read_text(encoding="utf-8")
    assert "version 2.1" in text
    assert "[INSERT CONTACT METHOD]" not in text


def test_code_of_conduct_enforcement_contact() -> None:
    path = ROOT / "CODE_OF_CONDUCT.md"
    text = path.read_text(encoding="utf-8")
    contact_instruction = (
        "report it privately through the repository's Security tab, "
        "Report a vulnerability, with a title starting `Conduct report:`"
    )
    assert contact_instruction in text
    assert "issues/new" not in text


@pytest.mark.parametrize("heading", COC_HEADINGS)
def test_coc_headings_present(heading: str) -> None:
    text = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    headings = [
        re.sub(r"^\d+\.\s*", "", line.lstrip("#").strip()) for line in text.splitlines() if line.startswith("#")
    ]
    assert heading in headings


@pytest.mark.parametrize("rel_path", ISSUE_FORMS)
def test_issue_form_structure(rel_path: str) -> None:
    path = ROOT / rel_path
    parsed = _parse_issue_form(path)
    assert parsed["has_top_name"]
    assert parsed["has_top_description"]
    assert parsed["has_top_body"]

    items = parsed["items"]
    non_markdown = [it for it in items if it["type"] != "markdown"]
    assert len(non_markdown) >= 1

    invalid_types = [it["type"] for it in items if it["type"] not in VALID_ITEM_TYPES]
    assert not invalid_types

    ids = [it["id"] for it in items if it["id"] is not None]
    assert len(ids) == len(set(ids))

    missing_labels = [it for it in items if it["type"] != "markdown" and not it["label"]]
    assert not missing_labels


def test_issue_config_structure() -> None:
    path = ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml"
    text = path.read_text(encoding="utf-8")
    assert "blank_issues_enabled: false" in text
    assert "SECURITY.md" in text


def test_bug_report_security_link_and_placeholder() -> None:
    path = ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
    text = path.read_text(encoding="utf-8")
    assert "https://github.com/ffroliva/sharpit/blob/main/SECURITY.md" in text
    assert "../../SECURITY.md" not in text
    assert '"0.8.0"' in text
    assert '"0.7.0"' not in text


def test_contributing_contents() -> None:
    path = ROOT / "CONTRIBUTING.md"
    text = path.read_text(encoding="utf-8")
    assert "git commit -s" in text
    assert "AGENTS.md" in text
    assert "uv run ruff check" in text
    assert "uv run ruff format --check" in text
    assert "uv run pyright" in text
    assert "uv run pytest -q -n auto" in text


@pytest.mark.parametrize("rel_path", _contributing_paths())
def test_contributing_paths_exist(rel_path: str) -> None:
    path = ROOT / rel_path.rstrip("/")
    assert path.exists()


def test_contributing_dco_workflow_documented() -> None:
    """Assert CONTRIBUTING.md documents the DCO workflow only if that workflow exists.

    Lane P2 adds .github/workflows/dco.yml and merges before P1.
    On docs/0.8.0-p1, this test is expected to fail until P2 is merged in.
    """
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    if "workflow enforces the sign-off requirement" in text:
        dco_workflow = ROOT / ".github" / "workflows" / "dco.yml"
        assert dco_workflow.is_file()
        workflow_text = dco_workflow.read_text(encoding="utf-8")
        assert "Signed-off-by" in workflow_text


def test_pull_request_template_contents() -> None:
    path = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
    text = path.read_text(encoding="utf-8")
    assert "summary" in text.lower()
    assert "closes #" in text.lower() or "issue" in text.lower()
    assert "uv run ruff check" in text
    assert "uv run ruff format --check" in text
    assert "uv run pyright" in text
    assert "uv run pytest -q -n auto" in text
    assert "finding" in text
    assert "test" in text
    assert "red" in text
    assert "signed-off-by" in text.lower() or "sign-off" in text.lower()
    assert "attribution" in text.lower()


@pytest.mark.parametrize("rel_path", COMMUNITY_FILES)
@pytest.mark.parametrize("word", FORBIDDEN_WORDS)
def test_no_forbidden_ai_attribution(rel_path: str, word: str) -> None:
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    assert word not in text
