"""Tests for the interactive tutorial documentation page.

Verifies:
- Tutorial page exists and is present in the navigation of website/mkdocs.yml.
- Every `sharpit ...` command cited in tutorial.md parses cleanly with sharpit.cli.commands,
  including inline code blocks with custom styles.
- Every link resolves without building the site: raw-HTML links use built URLs (`../page/`) that map to a page under
  `website/docs/`, Markdown links point at existing files, and same-page anchors exist.
- No external URLs are loaded or linked except the GitHub repository link.
"""

from __future__ import annotations

import argparse
import re
import shlex
from pathlib import Path

from sharpit.cli.commands import _build_root_parser
from sharpit.cli.manifest import Manifest

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "website" / "docs"
MKDOCS_YML = ROOT / "website" / "mkdocs.yml"
TUTORIAL_MD = DOCS_DIR / "tutorial.md"

ALLOWED_EXTERNAL_URLS = (
    "https://github.com/ffroliva/sharpit",
    "https://ffroliva.github.io/sharpit",
)

LOCAL_URL_PREFIXES = (
    "http://127.0.0.1:",
    "http://localhost:",
)

HREF = re.compile(r'href="([^"]+)"')
MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
EXTERNAL_RESOURCE = re.compile(r"""(?:src|href)=["'](https?://[^"']+)["']""")


def test_tutorial_page_exists_and_in_nav() -> None:
    assert TUTORIAL_MD.is_file(), f"Missing {TUTORIAL_MD}"
    assert MKDOCS_YML.is_file(), f"Missing {MKDOCS_YML}"

    text = MKDOCS_YML.read_text(encoding="utf-8")
    assert re.search(r"-\s+[^:\n]+:\s*tutorial\.md", text), "tutorial.md is not listed in mkdocs.yml navigation"


def test_all_sharpit_commands_in_tutorial_parse() -> None:
    text = TUTORIAL_MD.read_text(encoding="utf-8")
    manifest = Manifest.bundled()
    parser, _ = _build_root_parser(manifest)

    # Match commands in code blocks and inline code `sharpit ...` or <code ...>sharpit ...</code>
    candidates: set[str] = set()

    for match in re.finditer(r"`sharpit\s+([^`]+)`", text):
        candidates.add(f"sharpit {match.group(1).strip()}")

    for match in re.finditer(r"<code[^>]*>\s*(sharpit\s+[^<\n]+)</code>", text):
        candidates.add(match.group(1).strip())

    for match in re.finditer(r"```(?:bash|sh|console)?\n([^`]+)```", text):
        for line in match.group(1).splitlines():
            line = line.strip()
            if line.startswith("sharpit "):
                candidates.add(line)

    assert candidates, "No sharpit commands found to validate in tutorial.md"

    assert {shlex.split(cmd)[0] for cmd in candidates} == {"sharpit"}
    assert [cmd for cmd in sorted(candidates) if not _parses(parser, shlex.split(cmd)[1:])] == []


def _parses(parser: argparse.ArgumentParser, arguments: list[str]) -> bool:
    try:
        parser.parse_args(arguments)
    except SystemExit:
        return False
    return True


def _is_allowed_external(url: str) -> bool:
    if url.startswith(LOCAL_URL_PREFIXES):
        return True
    return any(url == allowed or url.startswith((allowed + "/", allowed + "#")) for allowed in ALLOWED_EXTERNAL_URLS)


def _built_url_page(link: str) -> Path:
    """`../quickstart/` on the built tutorial page (served at /tutorial/) is the page `quickstart.md`."""
    page = link.split("#")[0].removeprefix("../").strip("/")
    return DOCS_DIR / f"{page}.md" if page else DOCS_DIR / "index.md"


def link_problems(text: str) -> list[str]:
    """Every link in the tutorial source that would not resolve on the built site."""
    problems: list[str] = []
    html_links = HREF.findall(text)
    for link in html_links + MARKDOWN_LINK.findall(text):
        path = link.split("#")[0]
        if link.startswith(("http://", "https://")):
            if not _is_allowed_external(link):
                problems.append(f"unapproved external URL {link}")
        elif link.startswith("#"):
            if not re.search(rf"""id=["']{re.escape(link[1:])}["']""", text):
                problems.append(f"anchor {link} not found")
        elif link in html_links and path.endswith(".md"):
            problems.append(f"raw-HTML link {link} is not rewritten by MkDocs: use the built URL (../page/)")
        elif link in html_links:
            page = _built_url_page(link)
            if not (page.is_file() or (page.with_suffix("") / "index.md").is_file()):
                problems.append(f"{link} has no page {page.name}")
        elif not (TUTORIAL_MD.parent / path).is_file():
            problems.append(f"Markdown link {link} does not resolve")
    return problems


def test_tutorial_links_resolve_without_building_the_site() -> None:
    text = TUTORIAL_MD.read_text(encoding="utf-8")
    assert HREF.findall(text), "No links found in tutorial.md"
    assert link_problems(text) == []


def test_a_raw_html_md_link_a_missing_page_and_a_missing_anchor_are_refused() -> None:
    planted = '<a href="quickstart.md">x</a> <a href="../no-such-page/">y</a> <a href="#nowhere">z</a>'
    problems = link_problems(planted)
    assert len(problems) == 3, problems


def test_tutorial_loads_no_external_resources() -> None:
    text = TUTORIAL_MD.read_text(encoding="utf-8")
    assets = "".join(
        path.read_text(encoding="utf-8")
        for path in (DOCS_DIR / "tutorial").glob("*.*")
        if path.suffix in {".js", ".css", ".html"}
    )
    for url in EXTERNAL_RESOURCE.findall(text + assets):
        assert _is_allowed_external(url), f"External resource in the tutorial: {url}"
    assert "url(http" not in assets.replace(" ", ""), "A stylesheet loads an external resource"
