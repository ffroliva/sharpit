"""CI layout costs, pinned by count, never by wall clock: where lint runs, how a leg is sharded, the tracer."""

import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

CI = (Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _jobs() -> dict[str, str]:
    jobs: dict[str, list[str]] = {}
    current = ""
    for line in CI.split("\njobs:\n", 1)[1].splitlines():
        if match := re.fullmatch(r"  ([a-z-]+):", line):
            current = match.group(1)
            jobs[current] = []
        elif current:
            jobs[current].append(line)
    return {name: "\n".join(lines) for name, lines in jobs.items()}


JOBS = _jobs()
SHARD = re.compile(r"shard: \[?(\d+)/(\d+)")


def _legs(job: str) -> dict[str, list[tuple[int, int]]]:
    """Shard entries of a matrix job, grouped by (os, python) leg."""
    legs: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for line in JOBS[job].splitlines():
        if "shard:" not in line:
            continue
        leg = "".join(re.findall(r"(?:os|python): \"?([\w.-]+)", line))
        legs[leg].extend((int(i), int(n)) for i, n in re.findall(r"(\d+)/(\d+)", line))
    return legs


def test_lint_runs_once_in_its_own_job_not_inside_a_test_shard() -> None:
    owners = [name for name, body in JOBS.items() if " ruff check" in body]
    assert owners == ["lint"], "lint inside a shard lengthens that shard's critical path"


def test_pyright_and_format_run_in_the_lint_job_only() -> None:
    for command in (" pyright", " ruff format --check"):
        assert [name for name, body in JOBS.items() if command in body] == ["lint"]


@pytest.mark.parametrize("job", ["test-shard", "coverage-shard", "lowest-shard", "no-sqlalchemy-shard"])
def test_each_leg_of_a_sharded_job_lists_every_shard_exactly_once(job: str) -> None:
    for leg, entries in _legs(job).items():
        totals = {n for _, n in entries}
        assert len(totals) == 1, f"{job} {leg}: mixed shard totals {totals}"
        assert sorted(i for i, _ in entries) == list(range(1, totals.pop() + 1)), f"{job} {leg}: {entries}"


def test_no_sqlalchemy_is_sharded_behind_the_required_check_name() -> None:
    assert "needs: no-sqlalchemy-shard" in JOBS["no-sqlalchemy"]
    assert "SHARPIT_SHARD: ${{ matrix.shard }}" in JOBS["no-sqlalchemy-shard"]


def test_the_coverage_shards_use_the_sys_monitoring_tracer() -> None:
    assert "COVERAGE_CORE: sysmon" in JOBS["coverage-shard"]


LOAD_CEILING = {"ubuntu-latest": 170.0, "windows-latest": 305.0}  # weighted test-seconds: ~0.3 s of wall per second


@pytest.mark.parametrize("leg", [leg for leg in _legs("test-shard") if leg])
def test_no_test_shard_carries_more_weighted_test_time_than_the_ceiling(leg: str) -> None:
    """The costliest shard sets the leg's wall; the ceiling is what a shard count must keep it under."""
    from _shard import shard_of

    platform = "win32" if leg.startswith("windows") else "linux"
    weights: dict[str, float] = json.loads((Path(__file__).parent / "shard_weights.json").read_text("utf-8"))[platform]
    n = _legs("test-shard")[leg][0][1]
    loads = [0.0] * n
    for rel, seconds in weights.items():
        loads[shard_of(rel, n, platform) - 1] += seconds
    ceiling = LOAD_CEILING["windows-latest" if platform == "win32" else "ubuntu-latest"]
    assert max(loads) <= ceiling, f"{leg}: {n} shards, loads {loads}"
