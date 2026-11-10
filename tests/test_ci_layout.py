"""CI layout costs, pinned by count, never by wall clock: where lint runs, how a leg is sharded, the tracer."""

import os
import re
import shutil
import subprocess
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import pytest

CI_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
CI = CI_PATH.read_text(encoding="utf-8")


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


def test_full_extras_installs_every_optional_gatekeeper_distribution() -> None:
    from tests.engine.test_import_boundary import GATEKEEPERS

    distributions = {
        "sqlalchemy": "sqlalchemy",
        "alembic": "alembic",
        "pydantic_settings": "pydantic-settings",
        "opentelemetry": "opentelemetry-sdk",
        "pytest": "pytest",
        "_pytest": "pytest",
        "asyncpg": "asyncpg",
        "aiomysql": "aiomysql",
    }
    groups = {"test": set(), "full-extras": set()}
    section = ""
    for line in Path(__file__).parents[1].joinpath("pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("["):
            section = line
        elif section == "[project.optional-dependencies]" and line.startswith("test = ["):
            section = "test"
        elif section == "[dependency-groups]" and line.startswith("full-extras = ["):
            section = "full-extras"
        elif section in groups and '"' in line:
            groups[section].add(line.split('"')[1].split(">=")[0].split("[")[0])
    missing = {
        distribution
        for key, distribution in distributions.items()
        if key in GATEKEEPERS or key in {"asyncpg", "aiomysql"}
        if not any(distribution in group for group in groups.values())
    }
    assert not missing, f"optional gatekeeper distributions absent from test/full-extras: {sorted(missing)}"


def test_the_full_extras_leg_uploads_a_parsed_junit() -> None:
    from scripts.ci.shard_weights import parse_artifact

    shard_body = JOBS["test-shard"]
    sync_lines = [line for line in shard_body.splitlines() if "uv sync" in line]
    assert sync_lines
    assert "matrix.os == 'ubuntu-latest' && matrix.python == '3.14'" in sync_lines[0]
    assert "--group full-extras" in sync_lines[0]
    assert "name: junit-test-shard-${{ matrix.os }}-${{ matrix.python }}-${{ strategy.job-index }}" in shard_body
    assert parse_artifact("junit-test-shard-ubuntu-latest-3.14-0") == (
        "test-shard",
        "ubuntu-latest-3.14-0",
    )
    masking = JOBS["masking-gates"]
    masking_sync = next(line for line in masking.splitlines() if "uv sync" in line)
    assert "matrix.os == 'ubuntu-latest'" in masking_sync
    assert "--group full-extras" in masking_sync
    assert "name: junit-masking-gates-${{ matrix.os }}" in masking
    assert parse_artifact("junit-masking-gates-ubuntu-latest") == ("masking-gates", "ubuntu-latest")


def test_junit_never_carries_captured_output() -> None:
    assert re.search(r"(?m)^\s*junit_logging\s*=\s*['\"]no['\"]\s*$", Path("pyproject.toml").read_text())
    assert not re.search(r"-o\s+junit_logging=", CI)


def test_live_runs_one_job_per_server() -> None:
    live = JOBS["live"]
    for server in ("mysql84", "mysql80", "mariadb", "postgresql", "controls"):
        assert f"server: {server}," in live
    assert "services:" in live
    for key in ("MYSQL84", "MYSQL80", "MARIADB", "POSTGRESQL"):
        assert f"SHARPIT_LIVE_{key}_URL:" in live
    pytest_steps = [line for line in live.splitlines() if re.search(r"^\s*- run:.*pytest\b", line)]
    assert pytest_steps
    assert all(not re.search(r"(?:^|\s)-n\s+0(?:\s|$)", line) for line in pytest_steps)
    assert "--health-cmd" in live
    assert "--health-interval" in live
    assert "--health-retries" in live
    assert "matrix.server == 'mariadb' && 'healthcheck.sh --connect --innodb_initialized'" in live
    assert 'pytest tests/live --live -n auto -k "$LIVE_FILTER"' in live


@pytest.mark.parametrize("job", ["ui", "vitest"])
def test_ui_working_directory_steps_are_guarded_for_absent_ui(job: str) -> None:
    lines = JOBS[job].splitlines()
    ui_steps = [index for index, line in enumerate(lines) if "working-directory: ui" in line]
    assert ui_steps
    for index in ui_steps:
        step = lines[index - 2 : index + 1]
        assert any("hashFiles('ui/package.json')" in guard for guard in step), step


def test_live_leg_pins_keep_the_old_case_totals() -> None:
    rows = [line for line in JOBS["live"].splitlines() if "server:" in line and "required:" in line]
    required = [re.search(r'required: "([^"]+)"', line)[1].split() for line in rows]
    assert sum("test_example_app_records_its_server_family=1" in pins for pins in required) == 2
    assert sum("test_oracle_control=3" in pins for pins in required) == 2
    assert sum("test_a_server_answers=1" in pins for pins in required) == 4
    assert sum("test_a_refused_statement_keeps_its_value_hidden=1" in pins for pins in required) == 5


def _live_leg_filters() -> dict[str, str]:
    result = {}
    for line in JOBS["live"].splitlines():
        if "server:" not in line or "filter:" not in line:
            continue
        server = re.search(r"server: ([\w-]+)", line)[1]
        filter_match = re.search(r'filter: "([^"]+)"|filter: ([^,}]+)', line)
        result[server] = (filter_match[1] or filter_match[2]).strip()
    return result


@pytest.mark.needs_sqlalchemy  # it collects tests/live, which imports the SQLAlchemy stack
@pytest.mark.timeout(300)  # five nested collections; see NESTED_RUN_TESTS
def test_the_live_legs_partition_the_live_tests() -> None:
    root = Path(__file__).parent.parent
    collection_environment = os.environ.copy()
    collection_environment.pop("SHARPIT_SHARD", None)
    collected = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-W",
            "ignore::pytest.PytestDeprecationWarning",
            "-n",
            "0",
            "tests/live",
            "--live",
        ],
        cwd=root,
        env=collection_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    nodeids = [line for line in collected.stdout.splitlines() if line.startswith("tests/live/") and "::" in line]
    assert len(nodeids) >= 21_888, f"live collection unexpectedly small: {len(nodeids)} tests"
    assert collected.returncode == 0, collected.stderr[-2000:]
    assert nodeids
    test_paths = sorted({nodeid.split("[", 1)[0] for nodeid in nodeids})
    selected: dict[str, set[str]] = {}
    for leg, expression in _live_leg_filters().items():
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-W",
                "ignore::pytest.PytestDeprecationWarning",
                "-n",
                "0",
                *test_paths,
                "--live",
                "-k",
                expression,
            ],
            cwd=root,
            env=collection_environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        assert result.returncode == 0, f"{leg}: {result.stderr[-2000:]}"
        selected[leg] = {line for line in result.stdout.splitlines() if line.startswith("tests/live/") and "::" in line}
    assigned = set().union(*selected.values())
    assert assigned == set(nodeids), f"unassigned live tests: {set(nodeids) - assigned}"
    overlaps = {
        (left, right): len(selected[left] & selected[right])
        for index, left in enumerate(selected)
        for right in list(selected)[index + 1 :]
        if selected[left] & selected[right]
    }
    assert not overlaps, f"live leg overlaps: {overlaps}"


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


def test_change_detector_fails_closed_when_git_diff_cannot_resolve_base(tmp_path: Path) -> None:
    lines = CI.splitlines()
    start = lines.index("        run: |", lines.index("      - id: filter")) + 1
    end = next(index for index in range(start, len(lines)) if lines[index].startswith("  lint:"))
    run = textwrap.dedent("\n".join(lines[start:end]))
    output = tmp_path / "change-output"  # absolute: the step runs in the repo root, shared by every xdist worker
    result = subprocess.run(
        [shutil.which("bash") or "bash", "-e", "-c", run],
        cwd=CI_PATH.parents[2],
        env={
            **os.environ,
            "BASE": "not-a-commit",
            "HEAD": "HEAD",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_OUTPUT": output.as_posix(),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        assert not (CI_PATH.parents[2] / output.name).exists(), "the step wrote its output into the repository root"
        assert result.returncode == 0
        assert "code=true" in output.read_text(encoding="utf-8")
    finally:
        output.unlink(missing_ok=True)


@pytest.mark.parametrize("job", ["test", "lowest", "no-sqlalchemy", "masking-gates-check"])
def test_required_checks_fail_when_change_detection_did_not_succeed(job: str) -> None:
    assert 'test "${{ needs.changes.result }}" = success' in JOBS[job], job
    assert 'if [ "$CODE_CHANGED" = false ]; then exit 0; fi' in JOBS[job], job


@pytest.mark.parametrize("job", ["coverage", "sonar", "ui", "vitest", "wheel"])
def test_required_jobs_fail_when_change_detection_did_not_succeed(job: str) -> None:
    assert 'test "${{ needs.changes.result }}" = success' in JOBS[job], job
    assert "needs.changes.outputs.code == 'true'" not in JOBS[job], job


def _assert_gate_aggregator(job: str, matrix_job: str) -> None:
    assert "if: always()" in job
    assert f"needs: [{matrix_job}, changes]" in job
    assert 'test "${{ needs.changes.result }}" = success' in job
    assert 'if [ "$CODE_CHANGED" = false ]; then exit 0; fi' in job
    assert f'test "${{{{ needs.{matrix_job}.result }}}}" = success' in job


def test_live_check_fails_when_a_live_leg_did_not_succeed() -> None:
    assert "live-check" in JOBS, "live-check aggregator is missing"
    assert 'test "${{ needs.live.result }}" = success' in JOBS["live-check"]


def test_every_gate_aggregator_runs_always_and_requires_success() -> None:
    assert "live-check" in JOBS, "live-check aggregator is missing"
    for name, matrix_job in (("masking-gates-check", "masking-gates"), ("live-check", "live")):
        body = JOBS[name]
        _assert_gate_aggregator(body, matrix_job)
        expected = f'test "${{{{ needs.{matrix_job}.result }}}}" = success'
        refused_result_check = body.replace(expected, expected.replace("= success", "= failure || true"))
        with pytest.raises(AssertionError):
            _assert_gate_aggregator(refused_result_check, matrix_job)
        refused_always_condition = body.replace("if: always()", "if: true")
        with pytest.raises(AssertionError):
            _assert_gate_aggregator(refused_always_condition, matrix_job)


def test_ci_can_be_dispatched_and_dispatch_runs_every_job() -> None:
    assert re.search(r"^  workflow_dispatch:", CI, re.MULTILINE), "CI cannot be dispatched for noise runs"
    assert '"$GITHUB_EVENT_NAME" != pull_request && "$GITHUB_EVENT_NAME" != push' in JOBS["changes"]


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


# Windows has no SIGALRM: pytest-timeout's thread method calls os._exit at the deadline, and xdist reports the dead
# worker as "crashed" with no traceback. Tests that run nested git or pytest suites outlive the 60 s default under load.
NESTED_RUN_TESTS = (
    ("tests/scripts/test_lane_gate.py", "test_f5b_leased_log_needs_both_leased_tests"),
    ("tests/masking/test_a12_resolver.py", "test_the_driver_switch_put_back_fails_the_surface_row"),
    ("tests/test_ci_layout.py", "test_the_live_legs_partition_the_live_tests"),
)


@pytest.mark.parametrize(("path", "name"), NESTED_RUN_TESTS, ids=[name for _, name in NESTED_RUN_TESTS])
def test_a_nested_run_test_outlives_the_default_timeout(path: str, name: str) -> None:
    source = (Path(__file__).parent.parent / path).read_text(encoding="utf-8")
    head = source[: source.index(f"def {name}(")].rstrip().splitlines()[-3:]
    marks = [int(found) for line in head for found in re.findall(r"pytest\.mark\.timeout\((\d+)\)", line)]
    assert marks, f"{name} has no timeout mark"
    assert marks[0] >= 300, f"{name} timeout {marks[0]} s"
