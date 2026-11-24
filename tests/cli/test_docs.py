"""Offline documentation command and distribution contract."""

import importlib.resources
import io
import json
import os
from pathlib import Path
from zipfile import ZipFile

import pytest

from sharpit import __version__
from sharpit.cli.commands import run
from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.manifest import Manifest
from sharpit.cli.options import GlobalOptions

ROOT = Path(__file__).resolve().parents[2]
CLI_PAGE = "website/docs/cli.md"


def _reject_client(*args):
    raise AssertionError("Offline docs must not configure or construct an application client")


def _docs(*args):
    out, err = io.StringIO(), io.StringIO()
    code = run(args, {"SHARPIT_URL": "garbage"}, False, out, err, _reject_client)
    return code, out.getvalue(), err.getvalue()


def _catalog():
    code, out, err = _docs("--json", "docs")
    assert code == ExitCodes.SUCCESS, err
    return json.loads(out)


# ported: DocsCommandTests.listsEveryTopicAndItsCoverageWithoutAnApplication
def test_docs_lists_every_topic_offline(monkeypatch, no_side_effects, tmp_path):
    monkeypatch.setattr(GlobalOptions, "to_client_options", _reject_client)
    monkeypatch.chdir(tmp_path)
    code, out, err = _docs("docs")
    assert code == ExitCodes.SUCCESS, err
    assert err == ""
    topics = _catalog()["topics"]
    assert {"cli", "settings", "decisions"} <= {topic["id"] for topic in topics}
    assert out.splitlines() == [
        f"Bundled documentation for sharpit {__version__}:",
        *(f"{topic['id']} - {topic['description']}" for topic in topics),
    ]
    assert _docs("docs", "cli")[0] == ExitCodes.SUCCESS
    assert _docs("docs", "--search", "sharpit")[0] == ExitCodes.SUCCESS


# ported: DocsCommandTests.pagesStayRawMarkdownWhenPipedUnlessJsonIsExplicit
def test_docs_page_stays_raw_when_piped_unless_json_is_explicit():
    source = (ROOT / CLI_PAGE).read_bytes().decode("utf-8")
    assert _docs("docs", "cli") == (ExitCodes.SUCCESS, source, "")
    for args in (("--json", "docs", "cli"), ("docs", "cli", "--json")):
        code, out, err = _docs(*args)
        assert code == ExitCodes.SUCCESS, err
        page = json.loads(out)
        assert list(page) == ["version", "topic", "file", "content"]
        assert page == {"version": __version__, "topic": "cli", "file": CLI_PAGE, "content": source}


# ported: DocsCommandTests.resourcesAreExactCopiesAndOnlyTheAllowListedCorpusIsPackaged
def test_docs_wheel_has_only_the_catalog_files_with_exact_bytes():
    wheel = os.environ.get("SHARPIT_TEST_WHEEL")
    if wheel is None:
        pytest.skip("Requires a built wheel selected by SHARPIT_TEST_WHEEL")
    with ZipFile(wheel) as archive:
        packaged = [name for name in archive.namelist() if name.startswith("sharpit/_docs/")]
        assert packaged, "wheel contains no bundled documentation"
        files = {f"sharpit/_docs/{topic['file']}": ROOT / topic["file"] for topic in _catalog()["topics"]}
        assert sorted(packaged) == sorted(files)
        for name, source in files.items():
            assert archive.read(name) == source.read_bytes()


# ported: DocsCommandTests.literalSearchReturnsSourceLineNumbersInCatalogOrder
def test_docs_literal_search_returns_full_source_lines_in_order():
    query = "SHARPIT"
    code, out, err = _docs("docs", "--search", query, "--json")
    assert code == ExitCodes.SUCCESS, err
    result = json.loads(out)
    assert list(result) == ["version", "query", "matches"]
    assert result["version"] == __version__
    assert result["query"] == query
    expected = [
        {"topic": topic["id"], "file": topic["file"], "line": number, "text": text}
        for topic in _catalog()["topics"]
        for number, text in enumerate((ROOT / topic["file"]).read_text(encoding="utf-8").splitlines(), 1)
        if "sharpit" in text.lower()
    ]
    assert expected
    assert result["matches"] == expected
    assert list(result["matches"][0]) == ["topic", "file", "line", "text"]
    assert _docs("docs", "--search", query)[1].splitlines() == [
        f"{match['file']}:{match['line']}:{match['text']}" for match in expected
    ]
    assert json.loads(_docs("docs", "--search", "unlikely-literal-[.*]-needle", "--json")[1])["matches"] == []


# ported: DocsCommandTests.invalidArgumentsFailWithoutInventingDocumentation
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--search", " "), "--search must not be blank."),
        (("cli", "--search", "version"), "Choose a topic or --search, not both."),
        (("cli", "settings"), "unrecognized arguments: settings"),
        (("cli", "--fail-on", "high"), "--fail-on"),
    ],
)
def test_docs_invalid_arguments_fail(args, message):
    code, out, err = _docs("docs", *args)
    assert code == ExitCodes.ERROR
    assert out == ""
    assert message in err


@pytest.mark.parametrize("topic", ["../cli.md", "/cli.md", r"C:\cli.md", "CLI.md", "cli ", "CLI"])
def test_docs_unknown_topic_never_reads_a_page(topic, monkeypatch):
    monkeypatch.setattr(importlib.resources, "files", _reject_client)
    message = f"Unknown documentation topic: {topic}. Run 'sharpit docs' to list topics.\n"
    assert _docs("docs", topic) == (ExitCodes.ERROR, "", message)


def test_docs_refuses_root_fail_on():
    code, out, err = _docs("--fail-on", "high", "docs")
    assert code == ExitCodes.ERROR
    assert out == ""
    assert "--fail-on is only supported by tool commands" in err


# ported: DocsCommandTests.localCommandsAreNotDiagnosticToolsAndAppearInHelp
def test_docs_is_in_help_and_absent_from_tool_manifest():
    assert {path[0] for path, _ in Manifest.bundled().command_specs}.isdisjoint({"docs"})
    assert "docs" in _docs("--help")[1]
    assert "No application or network" in " ".join(_docs("docs", "--help")[1].split())


# ported: DocsCommandTests.topicJsonHasDeterministicFieldOrder
def test_docs_list_json_key_order_and_version():
    result = _catalog()
    assert list(result) == ["version", "topics"]
    assert result["version"] == __version__
    assert all(list(topic) == ["id", "title", "description", "file"] for topic in result["topics"])


@pytest.fixture
def bundled_cli_page(tmp_path, monkeypatch):
    page = tmp_path / "_docs" / CLI_PAGE
    page.parent.mkdir(parents=True)
    page.write_bytes("# Help — → 漢字\r\n  a [.*] literal  \r\nthird line\r\n".encode())
    monkeypatch.setattr(importlib.resources, "files", lambda _package: tmp_path)
    return page


@pytest.mark.parametrize("terminal", [False, True])
def test_docs_writes_markdown_on_cp1252_stream(bundled_cli_page, terminal):
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="cp1252", newline="")
    err = io.StringIO()
    assert run(["docs", "cli"], {}, terminal, out, err, _reject_client) == ExitCodes.SUCCESS, err.getvalue()
    content = bundled_cli_page.read_bytes()
    expected = content.decode().encode("cp1252", errors="replace") if terminal else content
    assert raw.getvalue() == expected


def test_docs_search_treats_metacharacters_literally_and_strips_crlf(bundled_cli_page):
    # A literal hit in the only synthetic page; the other pages are ordinary checkout resources.
    for path in (ROOT / "website/docs").glob("*.md"):
        if path.name != "cli.md":
            (bundled_cli_page.parent / path.name).touch()
    decisions = bundled_cli_page.parents[2] / "docs/decisions"
    decisions.mkdir(parents=True)
    for path in (ROOT / "docs/decisions").glob("*.md"):
        (decisions / path.name).touch()
    assert _docs("docs", "--search", "[.*] LITERAL") == (ExitCodes.SUCCESS, f"{CLI_PAGE}:2:  a [.*] literal  \n", "")


def test_docs_outside_a_sharpit_checkout_never_read_the_host_tree(monkeypatch, tmp_path):
    from sharpit.cli import docs_catalog

    module = tmp_path / "src" / "sharpit" / "cli" / "docs_catalog.py"
    module.parent.mkdir(parents=True)
    module.write_text("", encoding="utf-8")
    host_page = tmp_path / "website" / "docs" / "index.md"
    host_page.parent.mkdir(parents=True)
    host_page.write_text("host application page", encoding="utf-8")
    monkeypatch.setattr(docs_catalog, "__file__", str(module))
    monkeypatch.setattr(docs_catalog.resources, "files", lambda _: tmp_path / "no-bundle")
    with pytest.raises(FileNotFoundError, match="Bundled documentation is missing"):
        docs_catalog.read_page("website/docs/index.md")
