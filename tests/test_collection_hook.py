"""The repo conftest's SQLAlchemy-mark check, end to end: it still bites, and it parses only collected modules."""

import os
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
PLANTED_LINE = "test_planted.py imports sqlalchemy at module level without pytestmark = pytest.mark.needs_sqlalchemy"
COUNTER = """
from pathlib import Path

import conftest

_check = conftest.sqlalchemy_imports_without_marker
_calls = []


def _counting(source):
    _calls.append(source)
    return _check(source)


conftest.sqlalchemy_imports_without_marker = _counting


def pytest_unconfigure(config):
    Path("count.txt").write_text(str(len(_calls)))
"""


@pytest.fixture
def nested(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A nested run with the repo conftest as a plugin and no CI partition leaking in."""
    paths = [str(TESTS), str(pytester.path), os.environ.get("PYTHONPATH", "")]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(p for p in paths if p))
    monkeypatch.delenv("SHARPIT_SHARD", raising=False)
    monkeypatch.delenv("SHARPIT_GATES_SHARD", raising=False)
    return pytester


# needs_sqlalchemy: without SQLAlchemy, pytest_ignore_collect skips marked modules and never reaches this check
@pytest.mark.needs_sqlalchemy
def test_an_unmarked_sqlalchemy_module_still_fails_collection_with_the_same_text(nested: pytest.Pytester) -> None:
    nested.makepyfile(test_planted="import sqlalchemy\n\n\ndef test_a():\n    assert sqlalchemy\n")
    result = nested.runpytest_subprocess("-p", "conftest", "--collect-only", "-q", "-p", "no:cacheprovider")
    assert result.ret == pytest.ExitCode.INTERRUPTED
    assert PLANTED_LINE in result.outlines


def test_a_single_node_id_run_parses_only_its_own_module(nested: pytest.Pytester) -> None:
    nested.makepyfile(**{f"test_m{i:02d}": "def test_a():\n    pass\n" for i in range(30)})
    nested.makepyfile(counter=COUNTER)
    result = nested.runpytest_subprocess(
        "-p", "conftest", "-p", "counter", "--collect-only", "-q", "-p", "no:cacheprovider", "test_m07.py::test_a"
    )
    assert result.ret == pytest.ExitCode.OK
    assert int((nested.path / "count.txt").read_text()) == 1
