"""Tests for community and contributor files (lane P1).

Asserts existence and structure of:
- CONTRIBUTING.md
- CODE_OF_CONDUCT.md
- .github/PULL_REQUEST_TEMPLATE.md
- .github/ISSUE_TEMPLATE/bug_report.yml
- .github/ISSUE_TEMPLATE/feature_request.yml
- .github/ISSUE_TEMPLATE/config.yml
"""

from __future__ import annotations

from pathlib import Path

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


@pytest.mark.parametrize("rel_path", COMMUNITY_FILES)
def test_community_file_exists(rel_path: str) -> None:
    path = ROOT / rel_path
    assert path.is_file()


def test_code_of_conduct_contents() -> None:
    path = ROOT / "CODE_OF_CONDUCT.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "version 2.1" in text
    assert "[INSERT CONTACT METHOD]" not in text


@pytest.mark.parametrize("rel_path", ISSUE_FORMS)
def test_issue_form_structure(rel_path: str) -> None:
    path = ROOT / rel_path
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "name:" in text
    assert "description:" in text
    assert "body:" in text


def test_issue_config_structure() -> None:
    path = ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "blank_issues_enabled: false" in text
    assert "SECURITY.md" in text


def test_contributing_contents() -> None:
    path = ROOT / "CONTRIBUTING.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "git commit -s" in text
    assert "AGENTS.md" in text
    assert "uv run ruff check" in text
    assert "uv run ruff format --check" in text
    assert "uv run pyright" in text
    assert "uv run pytest -q -n auto" in text


def test_pull_request_template_contents() -> None:
    path = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
    assert path.is_file()
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
def test_no_forbidden_ai_attribution(rel_path: str) -> None:
    path = ROOT / rel_path
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    for word in ("Co" + "-Authored-By", "Cl" + "aude", "Co" + "dex", "Ge" + "mini", "Anti" + "gravity"):
        assert word not in text
