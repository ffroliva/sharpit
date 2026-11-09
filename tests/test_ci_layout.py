"""CI layout costs, pinned by count, never by wall clock: where lint runs, how a leg is sharded, the tracer."""

import os
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
    assert "needs: [no-sqlalchemy-shard, changes]" in JOBS["no-sqlalchemy"]
    assert "SHARPIT_SHARD: ${{ matrix.shard }}" in JOBS["no-sqlalchemy-shard"]


def test_the_coverage_shards_use_the_sys_monitoring_tracer() -> None:
    assert "COVERAGE_CORE: sysmon" in JOBS["coverage-shard"]


LOAD_CEILING = {"ubuntu-latest": 170.0, "windows-latest": 305.0}  # weighted test-seconds: ~0.3 s of wall per second


@pytest.mark.parametrize("leg", [leg for leg in _legs("test-shard") if leg])
def test_no_test_shard_carries_more_weighted_test_time_than_the_ceiling(leg: str) -> None:
    """The costliest shard sets the leg's wall; the ceiling is what a shard count must keep it under."""
    from _shard import shard_loads

    platform = "win32" if leg.startswith("windows") else "linux"
    n = _legs("test-shard")[leg][0][1]
    loads = shard_loads(n, platform)  # the planner's own prediction: a split file's tests spread over shards 1..n-1
    ceiling = LOAD_CEILING["windows-latest" if platform == "win32" else "ubuntu-latest"]
    assert max(loads) <= ceiling, f"{leg}: {n} shards, loads {loads}"


def test_the_required_test_check_still_fails_when_lint_fails() -> None:
    """Lint left the shards, so the required `test` checks must wait for it or a lint failure would merge."""
    assert "needs: [test-shard, lint, changes]" in JOBS["test"]
    assert 'needs.lint.result }}" = success' in JOBS["test"]


def test_every_pytest_step_uploads_its_junit_and_overhead_records() -> None:
    from scripts.ci.shard_weights import parse_artifact

    pytest_jobs = [
        name
        for name, body in JOBS.items()
        if any(re.search(r"^\s*(?:- )?run:.*pytest\b", line) for line in body.splitlines())
    ]
    assert pytest_jobs
    missing_junit = [
        name
        for name in pytest_jobs
        if any(
            re.search(r"^\s*(?:- )?run:.*pytest\b", line) and "--junitxml=" not in line
            for line in JOBS[name].splitlines()
        )
    ]
    assert not missing_junit, f"pytest steps without JUnit XML: {missing_junit}"
    missing_overhead = [name for name in pytest_jobs if "name: overhead-" not in JOBS[name]]
    assert not missing_overhead, f"pytest jobs without overhead uploads: {missing_overhead}"
    for job in pytest_jobs:
        assert f"name: junit-{job}-" in JOBS[job], job
        assert f"name: overhead-{job}-" in JOBS[job], job
        assert "SHARPIT_OVERHEAD_LOG: ${{ runner.temp }}/overhead.jsonl" in JOBS[job], job
        assert JOBS[job].count("if: always()") >= 2, job
    assert parse_artifact("junit-test-shard-ubuntu-latest-3.12-0") == ("test-shard", "ubuntu-latest-3.12-0")


def test_live_runs_one_job_per_server() -> None:
    live = JOBS["live"]
    for server in ("mysql84", "mysql80", "mariadb", "postgresql", "controls"):
        assert f"server: {server}," in live
    assert "services:" in live
    for key in ("MYSQL84", "MYSQL80", "MARIADB", "POSTGRESQL"):
        assert f"SHARPIT_LIVE_{key}_URL:" in live
    assert "-n 0" not in live


def test_a_docs_only_push_skips_expensive_ci_and_keeps_required_checks() -> None:
    assert "changes" in JOBS
    assert "paths-ignore: [ '**.md', 'website/**']" not in CI.split("permissions:", 1)[0]
    assert "grep -Ev '(^website/|\\.md$)'" in CI
    for job in ("test", "coverage", "sonar", "lowest", "no-sqlalchemy", "ui", "vitest", "wheel"):
        assert "needs.changes.outputs.code" in JOBS[job], job
    for job in (
        "lint",
        "test-shard",
        "coverage-shard",
        "lowest-shard",
        "no-sqlalchemy-shard",
        "masking-gates",
        "live",
        "sharpit-gate",
        "workflow-lint",
    ):
        assert "if: needs.changes.outputs.code == 'true'" in JOBS[job], job


OWN_JOB_FILES = (  # each alone outweighs a shard ceiling (487, 386, 418 s): one job runs them whole, every row
    "tests/masking/test_masking_scales_linearly.py",
    "tests/masking/test_statement_surfaces.py",
    "tests/scripts/test_lane_gate.py",
    "tests/masking/test_gates_bite.py",
)


def test_the_heavy_masking_gates_have_one_job_and_no_shard_collects_them(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nested subprocesses start outside tests/, where the _shard plugin lives.
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(Path(__file__).parent), os.environ.get("PYTHONPATH", ""))))
    for gate in OWN_JOB_FILES:
        assert [name for name, body in JOBS.items() if gate in body] == ["masking-gates"], gate
    for gate in OWN_JOB_FILES:
        path = pytester.path / gate
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def test_row(): pass" + chr(10), encoding="utf-8")
    pytester.makepyfile(test_other="def test_a(): pass")
    for spec in ("1/3", "2/3", "3/3"):
        monkeypatch.setenv("SHARPIT_SHARD", spec)
        result = pytester.runpytest_subprocess("-p", "_shard", "--collect-only", "-q", "-p", "no:cacheprovider")
        for gate in OWN_JOB_FILES:
            assert not [line for line in result.outlines if gate in line], f"shard {spec} collects {gate}"
    monkeypatch.delenv("SHARPIT_SHARD")
    result = pytester.runpytest_subprocess("-p", "_shard", "--collect-only", "-q", "-p", "no:cacheprovider")
    for gate in OWN_JOB_FILES:
        assert f"{gate}::test_row" in result.outlines
