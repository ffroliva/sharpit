"""Tests for the interactive tutorial documentation page.

Verifies:
- Tutorial page exists and is present in the navigation of website/mkdocs.yml.
- Every `sharpit ...` command cited in tutorial.md parses cleanly with sharpit.cli.commands,
  including inline code blocks with custom styles.
- Built site links resolve to valid built files/anchors (via temporary mkdocs build).
- No external URLs are loaded or linked except the GitHub repository link.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
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
    "https://ffroliva.github.io/sharpit",
}

LOCAL_URL_PREFIXES = (
    "http://127.0.0.1:",
    "http://localhost:",
)


@pytest.fixture(scope="module")
def built_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    site_dir = tmp_path_factory.mktemp("built_site")
    mkdocs_bin = shutil.which("mkdocs") or "mkdocs"
    res = subprocess.run(
        [mkdocs_bin, "build", "-f", str(MKDOCS_YML), "-d", str(site_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"mkdocs build failed (rc={res.returncode}):\n{res.stderr}\n{res.stdout}"
    return site_dir


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

    for cmd in sorted(candidates):
        tokens = shlex.split(cmd)
        assert tokens[0] == "sharpit"
        try:
            parsed = parser.parse_args(tokens[1:])
            assert parsed is not None, f"Failed to parse: {cmd}"
        except SystemExit as exc:
            pytest.fail(f"CLI command in tutorial failed to parse: '{cmd}' (exit {exc.code})")


def _tutorial_content(built_html: str) -> str:
    """Extract tutorial article content to validate tutorial links and resources."""
    match = re.search(r"<article\b[^>]*>(.*?)</article>", built_html, re.DOTALL)
    return match.group(1) if match else built_html


def test_built_tutorial_links_resolve_and_no_unapproved_external_urls(built_site: Path) -> None:
    built_tutorial = built_site / "tutorial" / "index.html"
    assert built_tutorial.is_file(), f"Missing built tutorial page at {built_tutorial}"

    full_html = built_tutorial.read_text(encoding="utf-8")
    content = _tutorial_content(full_html)

    # Match href attributes in the tutorial content
    html_links = re.findall(r'href="([^"]+)"', content)
    assert html_links, "No links found in built tutorial content"

    tutorial_dir = built_tutorial.parent

    for link in html_links:
        if link.startswith("#"):
            # Anchor on the same page
            anchor = link[1:]
            assert re.search(rf'id=["\']{re.escape(anchor)}["\']', full_html), (
                f"Anchor '{link}' not found in built tutorial"
            )
            continue

        if link.startswith("http://") or link.startswith("https://"):
            if any(link.startswith(prefix) for prefix in LOCAL_URL_PREFIXES):
                continue
            is_allowed = any(
                link == allowed or link.startswith(allowed + "/") or link.startswith(allowed + "#")
                for allowed in ALLOWED_EXTERNAL_URLS
            )
            assert is_allowed, f"Unapproved external URL found in built tutorial: {link}"
        else:
            # Relative link: resolve relative to built tutorial directory
            clean_path = link.split("#")[0].split("?")[0]
            if not clean_path:
                continue
            target = (tutorial_dir / clean_path).resolve()
            if target.is_dir():
                index_target = target / "index.html"
                assert index_target.is_file(), (
                    f"Relative link '{link}' resolves to directory {target} without index.html"
                )
            else:
                assert target.exists(), f"Relative link '{link}' does not resolve to an existing file in built site"


def test_built_tutorial_loads_no_external_resources(built_site: Path) -> None:
    built_tutorial = built_site / "tutorial" / "index.html"
    assert built_tutorial.is_file(), f"Missing built tutorial page at {built_tutorial}"

    content = _tutorial_content(built_tutorial.read_text(encoding="utf-8"))

    sources = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)["\']', content)
    for src in sources:
        if any(src.startswith(prefix) for prefix in LOCAL_URL_PREFIXES):
            continue
        is_allowed_gh = any(src.startswith(allowed) for allowed in ALLOWED_EXTERNAL_URLS)
        assert is_allowed_gh, f"External resource loaded in built tutorial: {src}"
