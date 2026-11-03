"""SHARPIT_SHARD=i/n splits the suite by test file: every test runs in exactly one shard."""

import json
from pathlib import Path

import pytest

from _shard import shard_of

TESTS = Path(__file__).parent
FILES = [p.relative_to(TESTS.parent).as_posix() for p in TESTS.rglob("test_*.py")]


def _collected(pytester: pytest.Pytester) -> set[str]:
    result = pytester.runpytest("-p", "_shard", "--collect-only", "-q", "-p", "no:cacheprovider")
    return {line for line in result.outlines if "::" in line}


def test_every_shard_of_the_suite_is_disjoint_and_together_they_are_the_whole_suite(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(12):
        pytester.makepyfile(**{f"test_m{i}": "def test_a(): pass\ndef test_b(): pass\n"})
    pytester.mkpydir("pkg").joinpath("test_deep.py").write_text("def test_c(): pass\n")
    monkeypatch.delenv("SHARPIT_SHARD", raising=False)
    whole = _collected(pytester)
    shards: list[set[str]] = []
    for i in (1, 2, 3):
        monkeypatch.setenv("SHARPIT_SHARD", f"{i}/3")
        shards.append(_collected(pytester))
    assert len(whole) == 25
    assert sum(len(s) for s in shards) == len(whole), "a test ran in more than one shard"
    assert set().union(*shards) == whole, "a test ran in no shard"
    assert all(shards), "a shard collected nothing (pytest exits 5)"


@pytest.mark.parametrize("n", [2, 3, 4])
def test_every_real_test_file_lands_in_exactly_one_nonempty_shard(n: int) -> None:
    owners = {f: shard_of(f, n) for f in FILES}
    assert all(1 <= s <= n for s in owners.values())
    assert set(owners.values()) == set(range(1, n + 1)), "an empty shard makes pytest exit 5"


def test_a_malformed_shard_spec_is_an_error_not_the_whole_suite(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytester.makepyfile(test_one="def test_a(): pass\n")
    monkeypatch.setenv("SHARPIT_SHARD", "3/2")
    result = pytester.runpytest("-p", "_shard", "-q", "-p", "no:cacheprovider")
    assert result.ret != 0


WEIGHTS = json.loads((TESTS / "shard_weights.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize("n", [2, 3, 4])
def test_measured_weights_balance_the_shards_within_the_longest_first_bound(platform: str, n: int) -> None:
    weights: dict[str, float] = WEIGHTS[platform]
    loads = [0.0] * n
    for rel, seconds in weights.items():
        loads[shard_of(rel, n, platform) - 1] += seconds
    floor = max(max(weights.values()), sum(weights.values()) / n)  # no split by file beats this
    assert max(loads) <= floor * 4 / 3, f"shard loads {[round(x) for x in loads]}, floor {floor:.0f}"
