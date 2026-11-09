"""Verify that pytest cache writes never create temporary directories in the cwd during tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_no_cache_write_lands_in_the_cwd(pytester: pytest.Pytester) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pytester.makeconftest(
        f"""
import sys
sys.path.insert(0, {str(repo_root)!r})
from tests.conftest import pytest_sessionstart
"""
    )
    pytester.makepyfile(
        """
import tempfile
from pathlib import Path

def test_cache_first_write(request):
    created = []
    orig = tempfile.mkdtemp

    def spy(*args, **kwargs):
        res = orig(*args, **kwargs)
        if "pytest-cache-files-" in res and str(Path.cwd()) in res:
            created.append(res)
        return res

    tempfile.mkdtemp = spy
    request.config.cache.set("sharpit/race", "probe")
    assert not created, f"cache write created temp dir in cwd: {created}"
"""
    )
    result = pytester.runpytest("-n", "2", "-q")
    assert result.ret == 0, "\n".join(result.stdout.lines)


def test_the_session_hook_runs_without_the_cache_plugin(pytester: pytest.Pytester) -> None:
    # nested runs and CI legs pass -p no:cacheprovider, which leaves no `cache` attribute on the config
    repo_root = Path(__file__).resolve().parents[1]
    pytester.makeconftest(
        f"""
import sys
sys.path.insert(0, {str(repo_root)!r})
from tests.conftest import pytest_sessionstart
"""
    )
    pytester.makepyfile("def test_ok():\n    pass\n")
    result = pytester.runpytest("-p", "no:cacheprovider", "-q")
    assert result.ret == 0, "\n".join(result.stdout.lines)
