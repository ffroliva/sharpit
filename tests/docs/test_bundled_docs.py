"""The offline corpus and public documentation index describe existing files."""

import io
import json
import re
from pathlib import Path

from sharpit.cli.commands import run

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "website/docs"
DECISIONS = ROOT / "docs/decisions"


def test_catalog_covers_the_user_guides_and_all_decisions():
    out, err = io.StringIO(), io.StringIO()
    assert run(["docs", "--json"], {}, False, out, err) == 0, err.getvalue()
    topics = json.loads(out.getvalue())["topics"]
    expected = {
        path.relative_to(ROOT).as_posix()
        for path in (*SITE.glob("*.md"), *DECISIONS.glob("*.md"))
        if path.name != "tutorial.md"
    }
    assert sorted(topic["file"] for topic in topics) == sorted(expected)
    assert len({topic["id"] for topic in topics}) == len(topics)
    decisions = {topic["id"]: Path(topic["file"]).name for topic in topics if topic["file"].startswith("docs/")}
    assert decisions == {
        "decisions": "README.md",
        **{f"decision-{path.stem}": path.name for path in DECISIONS.glob("*.md") if path.name != "README.md"},
    }


def test_decision_index_lists_every_decision_and_its_paths_exist():
    index = DECISIONS / "README.md"
    assert index.is_file()
    pages = {path.name for path in DECISIONS.glob("*.md") if path != index}
    assert {"activation-signals.md", "wsgi-request-target.md"} <= pages
    entries = re.findall(r"^- \[[^\]]+\]\(([^)]+)\)", index.read_text(encoding="utf-8"), re.MULTILINE)
    assert sorted(entries) == sorted(pages)
    for name in pages:
        content = (DECISIONS / name).read_text(encoding="utf-8")
        for section in ("Status", "Decision", "Rationale", "Consequences", "Enforced by"):
            assert f"## {section}\n" in content
        paths = re.findall(r"`((?:src|tests|docs/decisions|website)/[^`]+)`", content)
        assert paths, name
        for path in paths:
            assert (ROOT / path).is_file(), path


def test_llms_txt_links_to_published_pages():
    path = SITE / "llms.txt"
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# sharpit\n\n> ")
    assert "`sharpit docs`" in content
    assert "`sharpit docs --search <term>`" in content
    config = (SITE.parent / "mkdocs.yml").read_text(encoding="utf-8")
    base = re.search(r"^site_url: (.+)$", config, re.MULTILINE)
    assert base is not None
    links = re.findall(r"^- \[[^\]]+\]\(([^)]+)\)", content, re.MULTILINE)
    assert links
    for url in links:
        assert url.startswith(base[1]), url
        page = url.removeprefix(base[1]).rstrip("/") or "index"
        assert (SITE / f"{page}.md").is_file(), url
