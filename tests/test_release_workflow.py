"""The tag-triggered release workflow: the only path from a commit to PyPI."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_runs_only_on_version_tags() -> None:
    assert 'tags:\n      - "v*.*.*"' in WORKFLOW
    assert "branches:" not in WORKFLOW


def test_publishes_with_trusted_publishing_not_a_stored_token() -> None:
    assert "id-token: write" in WORKFLOW
    assert "pypa/gh-action-pypi-publish@" in WORKFLOW
    assert "password:" not in WORKFLOW
    assert "secrets." not in WORKFLOW
    assert "name: pypi" in WORKFLOW  # the environment PyPI's trusted publisher is bound to


def test_refuses_unsigned_tags() -> None:
    assert 'git cat-file -t "$TAG"' in WORKFLOW
    assert "BEGIN (PGP|SSH) SIGNATURE" in WORKFLOW


def test_refuses_a_tag_that_does_not_match_the_built_version() -> None:
    # the wheel name carries the version hatch read from __version__, so this checks what actually ships
    assert "dist/sharpit-${TAG#v}-py3-none-any.whl" in WORKFLOW


def test_smoke_tests_the_wheel_before_publishing() -> None:
    assert WORKFLOW.index("scripts/ci/wheel_smoke.py") < WORKFLOW.index("pypa/gh-action-pypi-publish@")


def test_never_restores_a_shared_cache_into_a_release() -> None:
    assert "enable-cache: false" in WORKFLOW


def test_release_uploads_only_wheel_and_sdist() -> None:
    lines = WORKFLOW.splitlines()
    release_idx = next(i for i, line in enumerate(lines) if "softprops/action-gh-release@" in line)
    step_lines = lines[release_idx:]
    files_idx = next(i for i, line in enumerate(step_lines) if line.strip().startswith("files:"))
    files_line = step_lines[files_idx].strip()
    after_colon = files_line.split(":", 1)[1].strip()
    if after_colon and after_colon != "|":
        file_entries = [after_colon]
    else:
        indent = len(step_lines[files_idx]) - len(step_lines[files_idx].lstrip())
        file_entries = []
        for line in step_lines[files_idx + 1 :]:
            if not line.strip():
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= indent:
                break
            file_entries.append(line.strip())
    assert file_entries == ["dist/*.whl", "dist/*.tar.gz"]
    assert "dist/*" not in file_entries


def test_how_it_works_cli_route() -> None:
    doc = (Path(__file__).resolve().parents[1] / "website" / "docs" / "how-it-works.md").read_text(encoding="utf-8")
    assert "/cli/tools/" in doc
    assert "/cli/<tool>" not in doc
