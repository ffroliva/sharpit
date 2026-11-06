"""SHARPIT_SHARD=i/n splits the suite by test file: every test runs in exactly one shard."""

import json
import re
from pathlib import Path

import pytest

import _shard
from _shard import shard_of

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
CI = (TESTS.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
CI_COUNTS = sorted({int(n) for line in CI.splitlines() if "shard:" in line for n in re.findall(r"\d+/(\d+)", line)})


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize("n", CI_COUNTS)  # the shard counts ci.yml really runs
def test_measured_weights_balance_the_shards_within_the_longest_first_bound(platform: str, n: int) -> None:
    weights: dict[str, float] = WEIGHTS[platform]
    loads = [0.0] * n
    for rel, seconds in weights.items():
        loads[shard_of(rel, n, platform) - 1] += seconds
    floor = max(max(weights.values()), sum(weights.values()) / n)  # no split by file beats this
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
