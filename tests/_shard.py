"""CI sharding by test file: ``SHARPIT_SHARD=i/n`` keeps only the test files of shard ``i`` (1-based).

Every test file lands in exactly one shard, so the shards of one leg together run the whole suite once
(``tests/test_shard.py``). Files with a recorded duration in ``test_durations.json`` are spread longest first onto
the lightest shard; every other file goes by a hash of its path, so the assignment never depends on which other
files exist. Unset, nothing is filtered.
"""

import hashlib
import json
import os
from functools import cache
from pathlib import Path

import pytest

DURATIONS = Path(__file__).with_name("test_durations.json")
_SPEC = pytest.StashKey[tuple[int, int]]()


@cache
def _balanced(n: int) -> dict[str, int]:
    durations: dict[str, float] = json.loads(DURATIONS.read_text(encoding="utf-8"))
    loads = [0.0] * n
    owners: dict[str, int] = {}
    for rel, seconds in sorted(durations.items(), key=lambda kv: (-kv[1], kv[0])):
        lightest = loads.index(min(loads))
        loads[lightest] += seconds
        owners[rel] = lightest + 1
    return owners


def shard_of(rel: str, n: int) -> int:
    """The shard (1..n) that runs the test file at ``rel``, a POSIX path relative to the rootdir."""
    return _balanced(n).get(rel) or int(hashlib.sha256(rel.encode()).hexdigest(), 16) % n + 1


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
    return True if shard_of(rel, spec[1]) != spec[0] else None
