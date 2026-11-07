"""SHARPIT_SHARD=i/n splits the suite by test file: every test runs in exactly one shard."""

import json
import re
from pathlib import Path

import pytest

import _shard
from _shard import shard_loads, shard_of, split_files

TESTS = Path(__file__).parent
FILES = [  # tests/live (the CI live job) and _shard.OWN_JOB (the masking-gates job) belong to no shard
    p.relative_to(TESTS.parent).as_posix()
    for p in TESTS.rglob("test_*.py")
    if p.relative_to(TESTS).parts[0] != "live" and p.relative_to(TESTS.parent).as_posix() not in _shard.OWN_JOB
]


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
CI = (TESTS.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
CI_COUNTS = sorted({int(n) for line in CI.splitlines() if "shard:" in line for n in re.findall(r"\d+/(\d+)", line)})


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize("n", CI_COUNTS)  # the shard counts ci.yml really runs
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
    assert max(loads) <= floor * 4 / 3, f"shard loads {[round(x) for x in loads]}, floor {floor:.0f}"


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_almost_every_real_test_file_has_a_measured_weight(platform: str) -> None:
    """A file with no weight is placed by hash, blind to its cost; one 66 s file landing on a loaded shard is a tail."""
    unmeasured = [f for f in FILES if f not in WEIGHTS[platform]]
    assert len(unmeasured) <= len(FILES) // 20, (
        f"{len(unmeasured)} of {len(FILES)} files unmeasured: refresh the weights"
    )


# A CPU-heavy file competes with a paired on/off timing test for the same cores; the budget tests then fail on the
# shard that holds both (security-logs hook, 2.624 µs against 2.000 µs with noise 0.661 µs, run 41889040828).
HEAVY_SECONDS = 30.0  # measured test seconds; every heavy file is measured now (the two gates left for their own job)
UNMEASURED_HEAVY: tuple[str, ...] = ()
TIMING_FILES = sorted(
    p.relative_to(TESTS.parent).as_posix()
    for p in TESTS.rglob("test_*.py")
    if re.search(r"^\s+check_budget\(", p.read_text(encoding="utf-8"), re.MULTILINE)
)


def test_the_overhead_budget_files_are_found() -> None:
    assert "tests/fastapi/test_capture_overhead.py" in TIMING_FILES
    assert "tests/test_shard.py" not in TIMING_FILES


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize("n", CI_COUNTS)
def test_no_shard_holds_both_a_heavy_file_and_an_overhead_budget_file(platform: str, n: int) -> None:
    heavy = {f for f, seconds in WEIGHTS[platform].items() if seconds >= HEAVY_SECONDS} | set(UNMEASURED_HEAVY)
    heavy_shards = {shard_of(f, n, platform) for f in heavy}
    timing_shards = {shard_of(f, n, platform) for f in TIMING_FILES}
    assert not heavy_shards & timing_shards, f"shards {sorted(heavy_shards & timing_shards)} hold both"


def test_the_shard_counts_are_read_from_ci_yml() -> None:
    assert CI_COUNTS == [3, 4, 5]


def test_the_unmeasured_heavy_files_are_named_in_the_shard_code() -> None:
    assert set(UNMEASURED_HEAVY) <= set(_shard.HEAVY_PATHS)
    assert _shard.timing_files() == set(TIMING_FILES)


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_the_weights_hold_no_file_that_runs_in_its_own_job(platform: str) -> None:
    """An own-job file is no shard's cost: a weight for it would be charged to a shard that never runs it."""
    assert not set(_shard.OWN_JOB) & set(WEIGHTS[platform])


def _file_items(items: set[str], rel: str) -> set[str]:
    return {item for item in items if item.startswith(f"{rel}::")}


def _write_weights(folder: Path, weights: dict[str, float]) -> Path:
    path = folder / "weights.json"
    path.write_text(json.dumps({"linux": weights, "win32": weights}), encoding="utf-8")
    return path


def test_a_split_file_runs_every_item_in_one_shard_and_the_union_is_all_its_items(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = {"test_big.py": 90.0, "test_s1.py": 10.0, "test_s2.py": 10.0, "test_s3.py": 10.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(pytester.path, weights))
    pytester.makepyfile(
        test_big="\n".join(f"def test_{k}(): pass" for k in range(7)) + "\n",
        test_s1="def test_a(): pass\n",
        test_s2="def test_b(): pass\n",
        test_s3="def test_c(): pass\n",
        test_unweighted="def test_u(): pass\n",
    )
    monkeypatch.delenv("SHARPIT_SHARD", raising=False)
    whole = _collected(pytester)
    big_whole = _file_items(whole, "test_big.py")
    shards: list[set[str]] = []
    for i in (1, 2, 3, 4):
        monkeypatch.setenv("SHARPIT_SHARD", f"{i}/4")
        shards.append(_collected(pytester))
    big_shards = [_file_items(s, "test_big.py") for s in shards]
    non_last = big_shards[:-1]
    assert len(big_whole) == 7
    assert big_shards[-1] == set(), "the last shard holds timing tests and must run no item of a split file"
    assert all(non_last), "every shard in 1..n-1 must collect a slice of a split file"
    assert all(len(s) < len(big_whole) for s in non_last), "no single shard may run a whole split file"
    assert sum(len(s) for s in non_last) == len(big_whole), "a split-file item ran in two shards"
    assert set().union(*non_last) == big_whole, "a split-file item ran in no shard"
    assert sum(len(s) for s in shards) == len(whole), "a test ran in more than one shard"
    assert set().union(*shards) == whole, "a test ran in no shard"


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
    assert sum(bool(_file_items(s, "test_over.py")) for s in shards) == 2
    assert _file_items(shards[-1], "test_over.py") == set()
    assert sum(bool(_file_items(s, "test_at.py")) for s in shards) == 1
    assert sum(bool(_file_items(s, "test_under.py")) for s in shards) == 1
    assert sum(bool(_file_items(s, "test_unweighted.py")) for s in shards) == 1
    assert split_files(3) == frozenset({"test_over.py"})


def test_a_split_file_spreads_its_weight_evenly_before_other_files_are_placed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = {"test_over.py": 58.0, "test_fill.py": 29.0, "test_a.py": 10.0, "test_b.py": 10.0, "test_c.py": 10.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(tmp_path, weights))
    assert shard_of("test_fill.py", 3) == 3
    assert {shard_of(f, 3) for f in ("test_a.py", "test_b.py", "test_c.py")} == {1, 2, 3}


@pytest.mark.parametrize("n", [2, 4])
def test_no_item_of_a_split_file_is_on_the_last_shard(
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
    assert split_files(n) == frozenset({"test_big.py"})
    assert _file_items(last, "test_big.py") == set()
    assert _file_items(last, "test_small.py") == {"test_small.py::test_s"}


def test_split_file_items_over_non_last_shards_partition_all_items(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = {"test_big.py": 90.0, "test_small.py": 10.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(pytester.path, weights))
    pytester.makepyfile(
        test_big="\n".join(f"def test_{k}(): pass" for k in range(8)) + "\n",
        test_small="def test_s(): pass\n",
    )
    monkeypatch.delenv("SHARPIT_SHARD", raising=False)
    big_whole = _file_items(_collected(pytester), "test_big.py")
    non_last: list[set[str]] = []
    for i in (1, 2, 3):
        monkeypatch.setenv("SHARPIT_SHARD", f"{i}/4")
        non_last.append(_file_items(_collected(pytester), "test_big.py"))
    ordered = sorted(big_whole)
    assert len(big_whole) == 8
    assert sum(len(s) for s in non_last) == len(big_whole), "duplicate or missing split-file item across 1..n-1"
    assert set().union(*non_last) == big_whole
    assert non_last == [set(ordered[k::3]) for k in range(3)]


def test_predicted_last_shard_load_holds_no_split_weight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    weights = {"test_over.py": 60.0, "test_heavy.py": 35.0, "test_light.py": 15.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(tmp_path, weights))
    assert shard_loads(3)[-1] == pytest.approx(15.0)
    assert shard_loads(3) == pytest.approx((65.0, 30.0, 15.0))


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize("n", [4, 5])
def test_real_predicted_last_shard_load_holds_no_split_weight(platform: str, n: int) -> None:
    weights: dict[str, float] = WEIGHTS[platform]
    splits = split_files(n, platform)
    unsplit_last = sum(s for r, s in weights.items() if r not in splits and shard_of(r, n, platform) == n)
    assert splits
    assert shard_loads(n, platform)[-1] == pytest.approx(unsplit_last)


def test_single_shard_runs_the_whole_suite_unchanged(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = {"test_big.py": 90.0, "test_small.py": 10.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(pytester.path, weights))
    pytester.makepyfile(
        test_big="def test_0(): pass\ndef test_1(): pass\n",
        test_small="def test_s(): pass\n",
        test_unweighted="def test_u(): pass\n",
    )
    monkeypatch.delenv("SHARPIT_SHARD", raising=False)
    whole = _collected(pytester)
    monkeypatch.setenv("SHARPIT_SHARD", "1/1")
    only = _collected(pytester)
    assert split_files(1) == frozenset()
    assert only == whole


def test_heavy_timing_file_keeps_heavy_precedence_off_the_last_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = {"test_both.py": 80.0, "test_budget.py": 5.0, "test_light.py": 15.0}
    monkeypatch.setattr(_shard, "WEIGHTS", _write_weights(tmp_path, weights))
    monkeypatch.setattr(_shard, "timing_files", lambda: frozenset({"test_both.py", "test_budget.py"}))
    assert "test_both.py" not in split_files(3)
    assert shard_of("test_both.py", 3) in {1, 2}
    assert shard_of("test_budget.py", 3) == 3
