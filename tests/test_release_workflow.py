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
