"""SHARPIT_SHARD=i/n splits the suite across shards: every test runs in exactly one shard."""

import json
from pathlib import Path

import pytest

import _shard
from _shard import shard_loads, shard_of, split_files

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
    splits = split_files(n)
    owners = {f: shard_of(f, n) for f in FILES if f not in splits}
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
    splits = split_files(n, platform)
    split_each = sum(weights[rel] for rel in splits) / (n - 1)
    loads = [*([split_each] * (n - 1)), 0.0]
    for rel, seconds in weights.items():
        if rel not in splits:
            loads[shard_of(rel, n, platform) - 1] += seconds
    unsplit_max = max((s for r, s in weights.items() if r not in splits), default=0.0)
    floor = max(unsplit_max, sum(weights.values()) / n)
    assert loads == pytest.approx(shard_loads(n, platform))
    assert max(loads) <= floor * 4 / 3, f"shard loads {[round(x) for x in loads]}, floor {floor:.0f}"


def _file_items(items: set[str], rel: str) -> set[str]:
    return {item for item in items if item.startswith(f"{rel}::")}


def _write_weights(folder: Path, weights: dict[str, float]) -> Path:
    path = folder / "weights.json"
    path.write_text(json.dumps({"linux": weights, "win32": weights}), encoding="utf-8")
    return path


def test_split_file_items_over_non_last_shards_partition_all_items(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = {"test_big.py": 90.0, "test_s1.py": 10.0, "test_s2.py": 10.0, "test_s3.py": 10.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(pytester.path, weights))
    pytester.makepyfile(
        test_big="\n".join(f"def test_{k}(): pass" for k in range(8)) + "\n",
        test_s1="def test_a(): pass\n",
        test_s2="def test_b(): pass\n",
        test_s3="def test_c(): pass\n",
        test_unweighted="def test_u(): pass\n",
    )
    monkeypatch.delenv("SHARPIT_SHARD", raising=False)
    whole = _collected(pytester)
    big_whole = _file_items(whole, "test_big.py")
    monkeypatch.setenv("SHARPIT_SHARD", "1/1")
    single = _collected(pytester)
    shards: list[set[str]] = []
    summaries: list[str] = []
    for i in (1, 2, 3, 4):
        monkeypatch.setenv("SHARPIT_SHARD", f"{i}/4")
        res = pytester.runpytest("-p", "_shard", "--collect-only", "-q", "-p", "no:cacheprovider")
        shards.append({line for line in res.outlines if "::" in line})
        summaries.append("\n".join(res.outlines))
    non_last = [_file_items(s, "test_big.py") for s in shards[:-1]]
    ordered = sorted(big_whole)
    assert split_files(1) == frozenset()
    assert single == whole
    assert len(big_whole) == 8
    assert all(non_last), "every shard in 1..n-1 must collect a slice of a split file"
    assert all(len(s) < len(big_whole) for s in non_last), "no single shard may run a whole split file"
    assert sum(len(s) for s in non_last) == len(big_whole), "a split-file item ran in more than one shard"
    assert set().union(*non_last) == big_whole, "a split-file item ran in no shard"
    assert non_last == [set(ordered[k::3]) for k in range(3)]
    assert "5 deselected" in summaries[0]
    assert sum(len(s) for s in shards) == len(whole), "a test ran in more than one shard"
    assert set().union(*shards) == whole, "a test ran in no shard"


@pytest.mark.parametrize("n", [2, 4])
def test_no_item_of_a_split_file_lands_on_the_last_shard(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    weights = {"test_big.py": 90.0, "test_small.py": 10.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(pytester.path, weights))
    pytester.makepyfile(
        test_big="\n".join(f"def test_{k}(): pass" for k in range(6)) + "\n",
        test_small="def test_s(): pass\n",
    )
    monkeypatch.setenv("SHARPIT_SHARD", f"{n}/{n}")
    last = _collected(pytester)
    direct = pytester.runpytest("-p", "_shard", "--collect-only", "-q", "-p", "no:cacheprovider", "test_big.py")
    assert split_files(n) == frozenset({"test_big.py"})
    assert _file_items(last, "test_big.py") == set()
    assert _file_items(last, "test_small.py") == {"test_small.py::test_s"}
    assert {line for line in direct.outlines if "::" in line} == set()


def test_a_file_over_the_share_is_split_and_a_file_under_it_is_not(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = {"test_over.py": 61.0, "test_at.py": 40.0, "test_under.py": 19.0}  # total 120, share 40 for n=3
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(pytester.path, weights))
    body = "def test_1(): pass\ndef test_2(): pass\ndef test_3(): pass\n"
    pytester.makepyfile(test_over=body, test_at=body, test_under=body, test_unweighted=body)
    shards: list[set[str]] = []
    for i in (1, 2, 3):
        monkeypatch.setenv("SHARPIT_SHARD", f"{i}/3")
        shards.append(_collected(pytester))
    assert split_files(3) == frozenset({"test_over.py"})
    assert sum(bool(_file_items(s, "test_over.py")) for s in shards) == 2
    assert _file_items(shards[-1], "test_over.py") == set()
    assert sum(bool(_file_items(s, "test_at.py")) for s in shards) == 1
    assert sum(bool(_file_items(s, "test_under.py")) for s in shards) == 1
    assert sum(bool(_file_items(s, "test_unweighted.py")) for s in shards) == 1


def test_predicted_loads_spread_split_weight_over_non_last_shards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = {"test_over.py": 58.0, "test_fill.py": 29.0, "test_a.py": 10.0, "test_b.py": 10.0, "test_c.py": 10.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(tmp_path, weights))
    assert shard_loads(3) == pytest.approx((39.0, 39.0, 39.0))
    assert shard_of("test_fill.py", 3) == 3
    assert {shard_of(f, 3) for f in ("test_a.py", "test_b.py", "test_c.py")} == {1, 2, 3}


def test_predicted_last_shard_load_holds_no_split_weight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    weights = {"test_over.py": 80.0, "test_unsplit.py": 20.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(tmp_path, weights))
    assert shard_loads(3) == pytest.approx((40.0, 40.0, 20.0))
    assert shard_loads(3)[-1] == pytest.approx(20.0)
    assert shard_loads(1) == pytest.approx((100.0,))
