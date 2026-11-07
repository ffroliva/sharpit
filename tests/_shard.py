"""CI sharding: ``SHARPIT_SHARD=i/n`` keeps only the tests of shard ``i`` (1-based).

Every test lands in exactly one shard, so the shards of one leg together run the whole suite once
(``tests/test_shard.py``). Files with a measured weight for this platform in ``shard_weights.json`` (CI JUnit,
``scripts/ci/shard_weights.py``) that exceed one shard's share (``total / n``) are collected on shards ``1..n-1`` and
split deterministically by sorted nodeid (with ``n == 1`` nothing changes); their weight is spread evenly across
``1..n-1`` before the other weighted files are placed longest first onto the lightest shard. Every other file goes by a
hash of its path, so a new file never moves the others. ``test_durations.json`` is the pytest-speed baseline and is not
used. Unset, nothing is filtered.
"""

import hashlib
import json
import os
import sys
from functools import cache
from pathlib import Path

import pytest

WEIGHTS = Path(__file__).with_name("shard_weights.json")
_SPEC = pytest.StashKey[tuple[int, int]]()


def _splits(durations: dict[str, float], n: int) -> frozenset[str]:
    if n <= 1 or not durations:
        return frozenset()
    share = sum(durations.values()) / n
    return frozenset(rel for rel, seconds in durations.items() if seconds > share)


@cache
def _plan(n: int, platform: str, weights: Path) -> tuple[frozenset[str], dict[str, int], tuple[float, ...]]:
    table: dict[str, dict[str, float]] = json.loads(weights.read_text(encoding="utf-8"))
    durations = table.get(platform) or table["linux"]  # macOS and others: the nearest measured platform
    splits = _splits(durations, n)
    if splits and n > 1:
        split_share = sum(durations[rel] for rel in splits) / (n - 1)
        loads = [*([split_share] * (n - 1)), 0.0]
    else:
        loads = [0.0] * n
    owners: dict[str, int] = {}
    for rel, seconds in sorted(durations.items(), key=lambda kv: (-kv[1], kv[0])):
        if rel in splits:
            continue
        lightest = loads.index(min(loads))
        loads[lightest] += seconds
        owners[rel] = lightest + 1
    return splits, owners, tuple(loads)


def split_files(n: int, platform: str = sys.platform) -> frozenset[str]:
    """Weighted test files heavier than one shard's share (total / n): collected on shards 1..n-1 and split by test."""
    return _plan(n, platform, WEIGHTS)[0]


def shard_loads(n: int, platform: str = sys.platform) -> tuple[float, ...]:
    """Predicted weighted test-seconds on each shard (1..n)."""
    return _plan(n, platform, WEIGHTS)[2]


def shard_of(rel: str, n: int, platform: str = sys.platform) -> int:
    """The shard (1..n) that runs the test file at ``rel``, a POSIX path relative to the rootdir."""
    splits, owners, _loads = _plan(n, platform, WEIGHTS)
    if owner := owners.get(rel):
        return owner
    if rel in splits:
        return 1
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
    return f"sharpit shard {spec[0]}/{spec[1]}" if spec else None


def _rel_path(path: Path, root: Path) -> str | None:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else None


def _ignore_rel(rel: str, i: int, n: int) -> bool:
    if rel in split_files(n):
        return n > 1 and i == n
    return shard_of(rel, n) != i


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    spec = config.stash.get(_SPEC, None)
    if spec is None or not collection_path.is_file() or not collection_path.name.startswith("test_"):
        return None  # None, never False: False would override every other ignore rule
    rel = _rel_path(collection_path, config.rootpath)
    return True if rel is not None and _ignore_rel(rel, spec[0], spec[1]) else None


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    spec = config.stash.get(_SPEC, None)
    if spec is None or not (splits := split_files(spec[1])):
        return
    i, n = spec
    span = max(n - 1, 1)
    matched = sorted(
        (item for item in items if _rel_path(item.path, config.rootpath) in splits),
        key=lambda item: item.nodeid,
    )
    dropped = [item for idx, item in enumerate(matched) if idx % span + 1 != i]
    if dropped:
        drop_ids = {id(item) for item in dropped}
        config.hook.pytest_deselected(items=dropped)
        items[:] = [item for item in items if id(item) not in drop_ids]
