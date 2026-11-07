"""CI sharding by test file: ``SHARPIT_SHARD=i/n`` keeps only the test files of shard ``i`` (1-based).

Every test file lands in exactly one shard, so the shards of one leg together run the whole suite once
(``tests/test_shard.py``). Files with a measured weight for this platform in ``shard_weights.json`` (CI JUnit,
``scripts/ci/shard_weights.py``) are spread longest first onto the lightest shard; every other file goes by a hash of
its path, so a new file never moves the others. ``test_durations.json`` is the pytest-speed baseline and is not used.
Unset, nothing is filtered.
"""

import hashlib
import json
import os
import re
import sys
from functools import cache
from pathlib import Path

import pytest

WEIGHTS = Path(__file__).with_name("shard_weights.json")
_SPEC = pytest.StashKey[tuple[int, int]]()


HEAVY_SECONDS = 30.0  # a file this costly (measured test seconds) competes with a timing test for the runner's cores
HEAVY_PATHS: tuple[str, ...] = ()  # CPU-heavy files not measured yet: heavy from day one (none: the table has them all)
OWN_JOB = (  # each heavier than a shard ceiling alone (487, 386, 418 s): the CI job masking-gates runs them whole
    "tests/masking/test_masking_scales_linearly.py",
    "tests/masking/test_statement_surfaces.py",
    "tests/scripts/test_lane_gate.py",
)
_TIMING_CALL = re.compile(r"^\s+check_budget\(", re.MULTILINE)


@cache
def timing_files() -> frozenset[str]:
    """The files holding an overhead budget test (a paired on/off timing): a busy runner fails them."""
    tests = Path(__file__).parent
    return frozenset(
        p.relative_to(tests.parent).as_posix()
        for p in tests.rglob("test_*.py")
        if _TIMING_CALL.search(p.read_text(encoding="utf-8"))
    )


@cache
def _balanced(n: int, platform: str) -> dict[str, int]:
    """Longest first onto the lightest shard. Heavy files never go on the last shard, and timing files go only there,
    so a budget test never shares a runner with a CPU-heavy file (with n == 1 there is nothing to separate)."""
    table: dict[str, dict[str, float]] = json.loads(WEIGHTS.read_text(encoding="utf-8"))
    durations = dict(table.get(platform) or table["linux"])  # macOS and others: the nearest measured platform
    for rel in HEAVY_PATHS:
        durations.setdefault(rel, 0.0)  # placed (and kept off the timing shard) before the weights know them
    timing = timing_files()
    loads = [0.0] * n
    owners: dict[str, int] = {}
    for rel, seconds in sorted(durations.items(), key=lambda kv: (-kv[1], kv[0])):
        allowed = range(n)
        if n > 1 and (rel in HEAVY_PATHS or seconds >= HEAVY_SECONDS):
            allowed = range(n - 1)
        elif n > 1 and rel in timing:
            allowed = range(n - 1, n)
        lightest = min(allowed, key=lambda i: (loads[i], i))
        loads[lightest] += seconds
        owners[rel] = lightest + 1
    return owners


def shard_of(rel: str, n: int, platform: str = sys.platform) -> int:
    """The shard (1..n) that runs the test file at ``rel``, a POSIX path relative to the rootdir."""
    if owner := _balanced(n, platform).get(rel):
        return owner
    if n > 1 and rel in timing_files():  # a new timing file nobody measured yet: still away from the heavy ones
        return n
    return int(hashlib.sha256(rel.encode()).hexdigest(), 16) % n + 1


def pytest_configure(config: pytest.Config) -> None:
    spec = os.environ.get("SHARPIT_SHARD")
    if not spec:
        return
    try:
        i, n = (int(part) for part in spec.split("/"))
    except ValueError:
        raise pytest.UsageError(f"SHARPIT_SHARD={spec!r}: expected i/n") from None
    if not 1 <= i <= n:
        raise pytest.UsageError(f"SHARPIT_SHARD={spec!r}: expected 1 <= i <= n")
    config.stash[_SPEC] = (i, n)


def pytest_report_header(config: pytest.Config) -> str | None:
    spec = config.stash.get(_SPEC, None)
    return f"sharpit shard {spec[0]}/{spec[1]} (by test file)" if spec else None


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    spec = config.stash.get(_SPEC, None)
    if spec is None or not collection_path.is_file() or not collection_path.name.startswith("test_"):
        return None  # None, never False: False would override every other ignore rule
    rel = collection_path.relative_to(config.rootpath).as_posix()
    if rel in OWN_JOB:
        return True
    return True if shard_of(rel, spec[1]) != spec[0] else None
