"""Tests for the interactive tutorial documentation page.

Verifies:
- Tutorial page exists and is present in the navigation of website/mkdocs.yml.
- Every `sharpit ...` command cited in tutorial.md parses cleanly with sharpit.cli.commands.
- All internal documentation links resolve to existing files.
- No external URLs are loaded or linked except the GitHub repository link.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from sharpit.cli.commands import _build_root_parser
from sharpit.cli.manifest import Manifest

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "website" / "docs"
MKDOCS_YML = ROOT / "website" / "mkdocs.yml"
TUTORIAL_MD = DOCS_DIR / "tutorial.md"

ALLOWED_EXTERNAL_URLS = {
    "https://github.com/ffroliva/sharpit",
}

LOCAL_URL_PREFIXES = (
    "http://127.0.0.1:",
    "http://localhost:",
)


def test_tutorial_page_exists_and_in_nav() -> None:
    assert TUTORIAL_MD.is_file(), f"Missing {TUTORIAL_MD}"
    assert MKDOCS_YML.is_file(), f"Missing {MKDOCS_YML}"

    text = MKDOCS_YML.read_text(encoding="utf-8")
    assert re.search(r"-\s+[^:\n]+:\s*tutorial\.md", text), "tutorial.md is not listed in mkdocs.yml navigation"


def test_all_sharpit_commands_in_tutorial_parse() -> None:
    text = TUTORIAL_MD.read_text(encoding="utf-8")
    manifest = Manifest.bundled()
    parser, _ = _build_root_parser(manifest)

    # Match commands in code blocks and inline code `sharpit ...` or <code>sharpit ...</code>
    candidates: set[str] = set()

    for match in re.finditer(r"`sharpit\s+([^`]+)`", text):
        candidates.add(f"sharpit {match.group(1).strip()}")

    for match in re.finditer(r"<code>\s*(sharpit\s+[^<\n]+)</code>", text):
        candidates.add(match.group(1).strip())

    for match in re.finditer(r"```(?:bash|sh|console)?\n([^`]+)```", text):
        for line in match.group(1).splitlines():
            line = line.strip()
            if line.startswith("sharpit "):
                candidates.add(line)

    assert candidates, "No sharpit commands found to validate in tutorial.md"

    for cmd in sorted(candidates):
        tokens = shlex.split(cmd)
        assert tokens[0] == "sharpit"
        # Parse args without triggering sys.exit
        try:
            parsed = parser.parse_args(tokens[1:])
            assert parsed is not None, f"Failed to parse: {cmd}"
        except SystemExit as exc:
            pytest.fail(f"CLI command in tutorial failed to parse: '{cmd}' (exit {exc.code})")


def test_tutorial_links_resolve_and_no_unapproved_external_urls() -> None:
    text = TUTORIAL_MD.read_text(encoding="utf-8")

    # Match markdown links: [text](target)
    md_links = re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", text)
    # Match html links: href="..."
    html_links = re.findall(r'href="([^"]+)"', text)

    all_links = sorted(set(md_links + html_links))
    assert all_links, "No links found in tutorial.md"

    for link in all_links:
        if link.startswith("#"):
            # Internal anchor on same page
            continue

        if link.startswith("http://") or link.startswith("https://"):
            # Check if it's local developer console URL
            if any(link.startswith(prefix) for prefix in LOCAL_URL_PREFIXES):
                continue
            # Must be the allowed GitHub repository URL
            is_allowed = any(
                link == allowed or link.startswith(allowed + "/") or link.startswith(allowed + "#")
                for allowed in ALLOWED_EXTERNAL_URLS
            )
            assert is_allowed, f"Unapproved external URL found in tutorial: {link}"
        else:
            # Relative doc link: must exist in DOCS_DIR
            clean_path = link.split("#")[0].split("?")[0]
            if clean_path:
                target = (DOCS_DIR / clean_path).resolve()
                assert target.is_file(), f"Relative link '{link}' does not resolve to a file in {DOCS_DIR}"


def test_tutorial_loads_no_external_resources() -> None:
    text = TUTORIAL_MD.read_text(encoding="utf-8")

    # Check img src, script src, link href for external domains
    sources = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)["\']', text)
    for src in sources:
        # Only local links or GitHub repo link are permitted
        if any(src.startswith(prefix) for prefix in LOCAL_URL_PREFIXES):
            continue
        is_allowed_gh = any(src.startswith(allowed) for allowed in ALLOWED_EXTERNAL_URLS)
        assert is_allowed_gh, f"External resource loaded in tutorial.md: {src}"
