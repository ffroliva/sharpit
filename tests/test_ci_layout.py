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


# Weighted test-seconds per shard. Run 43178363371: a shard's pytest step takes ~0.27 s of wall per weighted second on
# Ubuntu (586 s in 158 s) and ~0.31 s on Windows (841 s in 262 s), so these keep each step under ~1.7 minutes. Weights
# from run 43199441634 (after the sqlite heap-walk fix): max loads 313 (Ubuntu, 4 shards) and 294 (Windows, 6). Windows
# is back at its old 305; Ubuntu's old 170 was set against stale weights that summed to half the measured time.
LOAD_CEILING = {"ubuntu-latest": 330.0, "windows-latest": 305.0}


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
    assert "needs: [test-shard, coverage-shard, lint, changes]" in JOBS["test"]
    assert 'needs.lint.result }}" = success' in JOBS["test"]


DOCS_ONLY_EXIT = 'if [ "$CODE_CHANGED" = false ]; then exit 0; fi'
DOCS_ONLY_SONAR = "Docs-only change; Sonar check is a no-op."


def test_the_313_leg_runs_only_under_coverage() -> None:
    """The 3.13 suite ran twice on the same install: plain in test-shard and again under coverage."""
    assert "ubuntu-latest3.13" not in _legs("test-shard")


def test_the_coverage_leg_is_the_313_leg_in_five_shards() -> None:
    assert _legs("coverage-shard") == {"ubuntu-latest3.13": [(i, 5) for i in range(1, 6)]}
    assert "--cov=sharpit --cov-report=" in JOBS["coverage-shard"]


def test_the_required_test_checks_need_the_coverage_leg() -> None:
    """The 3.13 leg runs only under coverage now, so `test` fails when it fails, docs-only changes still exit 0."""
    body = JOBS["test"]
    assert "coverage-shard" in body.split("needs:", 1)[1].splitlines()[0]
    assert DOCS_ONLY_EXIT in body
    assert 'test "${{ needs.coverage-shard.result }}" = success' in body.split(DOCS_ONLY_EXIT, 1)[1]


BUDGET_JOBS = ("test-shard", "coverage-shard", "lowest-shard", "no-sqlalchemy-shard")
BUDGETS_ARGS = "@${{ runner.temp }}/budgets.args"  # the timing files (tests/_shard.py timing_files), one per line
NO_BUDGETS_ARGS = "@${{ runner.temp }}/no-budgets.args"  # --ignore=<timing file>, one per line


@pytest.mark.parametrize("job", BUDGET_JOBS)
def test_the_budget_files_run_alone_after_the_parallel_step(job: str) -> None:
    """Budget tests time capture on vs off: beside xdist workers still draining they fail on CI only, so every leg
    runs them in their own `-n 0` step on its last shard, after the parallel step, which ignores them (each test once).
    The coverage leg keeps them in its parallel step (their ordinary tests are coverage input; tests/overhead.py::paired
    skips the budget assertions under the tracer) and reruns them unmeasured in the budget step."""
    steps = _split_steps(JOBS[job])
    runs = [step for step in steps if re.search(r"run:.*\bpytest\b", step)]
    parallel = [step for step in runs if "-n auto" in step]
    budgets = [step for step in runs if BUDGETS_ARGS in step]
    assert len(parallel) == 1, parallel
    if job == "coverage-shard":
        assert NO_BUDGETS_ARGS not in parallel[0], "the timing files' ordinary tests left the coverage input"
    else:
        assert NO_BUDGETS_ARGS in parallel[0]
    assert len(budgets) == 1, f"{job}: no step runs the timing files alone"
    assert len(runs) == 2, f"{job}: the timing files run only in the parallel step (ignored) and the budget step"
    assert " -n 0 " in budgets[0]
    assert steps.index(budgets[0]) > steps.index(parallel[0])
    assert "SHARPIT_SHARD" not in budgets[0]
    assert "--cov" not in budgets[0]
    assert "COVERAGE_" not in budgets[0]
    for marker in re.findall(r' -m "[^"]+"', parallel[0]):
        assert marker in budgets[0], marker
    lasts = {n for entries in _legs(job).values() for _, n in entries}
    for n in sorted(lasts):
        assert f"matrix.shard == '{n}/{n}'" in budgets[0], n
    writer = 'scripts/ci/timing_files.py "${{ runner.temp }}"'
    assert writer in JOBS[job]
    assert JOBS[job].index(writer) < JOBS[job].index(parallel[0])
    for kind in ("junit", "overhead", "speed"):
        assert re.search(rf"name: {kind}-{job}-\S*budgets$", JOBS[job], re.MULTILINE), kind


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


SPEED_DIR = "${{ runner.temp }}/speed"


PYTEST_JOBS = [name for name, body in JOBS.items() if re.search(r"^\s*(?:- )?run:.*\bpytest\b", body, re.MULTILINE)]


@pytest.mark.parametrize("job", PYTEST_JOBS)
def test_every_pytest_job_records_fixture_times_and_rebuilds_and_uploads_them(job: str) -> None:
    """pytest-speed step 1 ranks CI's own runs: each pytest run writes fixture times and rebuild counts."""
    runs = [line for line in JOBS[job].splitlines() if re.search(r"^\s*(?:- )?run:.*\bpytest\b", line)]
    assert runs
    for line in runs:
        assert "-p scripts.pytest_speed.fixture_timer --fixture-times=" in line, line
        assert "-p scripts.pytest_speed.rebuild_log --rebuild-log=" in line, line
        assert re.search(r"--fixture-times=\\?\"?(?:\$\{\{ runner\.temp \}\}|\$RUNNER_TEMP)/speed/", line), line
        assert re.search(r"--rebuild-log=\\?\"?(?:\$\{\{ runner\.temp \}\}|\$RUNNER_TEMP)/speed/", line), line
    body = JOBS[job]
    assert body.index(f'os.makedirs(sys.argv[1], exist_ok=True)" "{SPEED_DIR}"') < body.index(runs[0])
    assert f'--values-file "${{{{ runner.temp }}}}/sharpit-canary.txt" "{SPEED_DIR}"' in body
    upload = body.split(f"name: speed-{job}", 1)
    assert len(upload) == 2, f"{job} uploads no speed-{job}-* artifact"
    tail = upload[1].split("\n      - ", 1)[0]
    assert f"path: {SPEED_DIR}" in tail
    assert "retention-days: 7" in tail
    assert "steps.scan-speed.outcome == 'success'" in upload[0].rsplit("\n      - ", 1)[1]


@pytest.mark.parametrize("job", PYTEST_JOBS)
def test_every_pytest_step_that_loads_a_scripts_plugin_can_import_scripts(job: str) -> None:
    """`-p scripts.…` is imported before pytest applies `pythonpath`: only `python -m pytest` puts the repo root on
    sys.path first (PR #135: `No module named 'scripts'` at startup on most shards)."""
    runs = [line for line in JOBS[job].splitlines() if "-p scripts." in line]
    assert runs
    bare = [line.strip() for line in runs if not re.search(r"\bpython -m pytest\b", line)]
    assert not bare, bare


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
    assert "name: junit-masking-gates-${{ matrix.os }}-${{ matrix.part }}" in masking
    assert parse_artifact("junit-masking-gates-ubuntu-latest-scales") == ("masking-gates", "ubuntu-latest-scales")


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
    ):
        assert "if: needs.changes.outputs.code == 'true'" in JOBS[job], job


def test_change_detector_fails_closed_when_git_diff_cannot_resolve_base(tmp_path: Path) -> None:
    lines = CI.splitlines()
    start = lines.index("        run: |", lines.index("      - id: filter")) + 1
    end = next(index for index in range(start, len(lines)) if re.fullmatch(r"  [a-z-]+:", lines[index]))
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


def test_sonar_needs_the_coverage_leg_not_the_coverage_job() -> None:
    """A separate combine job put its setup and a handoff on the required wall between the coverage leg and Sonar."""
    assert JOBS["sonar"].split("needs:", 1)[1].splitlines()[0].strip() == "[coverage-shard, changes]"


def test_sonar_combines_then_scans_then_ratchets_in_one_job() -> None:
    body = JOBS["sonar"]
    order = [
        DOCS_ONLY_SONAR,
        'test "${{ needs.coverage-shard.result }}" = success',
        "pattern: coverage-data-*",
        "coverage combine coverage-*.data",
        "coverage xml",
        "uses: actions/cache@",
        "uses: SonarSource/sonarqube-scan-action@",
        "scripts/ci/sonar_ratchet.py --pull-request",
    ]
    missing = [marker for marker in order if marker not in body]
    assert not missing, missing
    positions = [body.index(marker) for marker in order]
    assert positions == sorted(positions), dict(zip(order, positions, strict=True))


def test_the_sonar_scanner_cache_is_keyed_and_pinned() -> None:
    body = JOBS["sonar"]
    scan_version = re.search(r"sonarqube-scan-action@[0-9a-f]{40} # (v[\d.]+)", body)
    assert scan_version, "the scan action is not pinned to a SHA"
    cache = next((step for step in _split_steps(body) if "actions/cache@" in step), "")
    assert re.search(r"uses: actions/cache@[0-9a-f]{40} # v[\d.]+", cache), cache
    assert "path: ~/.sonar/cache" in cache
    assert f"key: sonar-${{{{ runner.os }}}}-{scan_version[1]}" in cache


def test_coverage_still_checks_the_coverage_leg_after_the_docs_only_exit() -> None:
    body = JOBS["coverage"]
    assert "Docs-only change; coverage check is a no-op." in body
    assert 'test "${{ needs.coverage-shard.result }}" = success' in body.split("Docs-only change", 1)[1]


def test_superseded_pull_request_runs_are_cancelled_and_main_never_is() -> None:
    """A superseded PR run kept its runners busy for the run that replaced it; a push to main runs to completion."""
    header = CI.split("\njobs:\n", 1)[0]
    assert re.search(r"^concurrency:$", header, re.MULTILINE), "no workflow-level concurrency"
    group = re.search(r"^  group: (.+)$", header, re.MULTILINE)
    assert group, "no concurrency group"
    # GitHub cancels a run WAITING in a group even without cancel-in-progress: a push must never share one
    assert group[1] == "${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
    assert "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in header
    assert "cancel-in-progress: true" not in CI


def test_workflow_lint_and_the_sharpit_gate_run_inside_lint() -> None:
    """Each took a runner and its setup for 11-16 s of work; their steps moved into lint, none removed."""
    assert "workflow-lint" not in JOBS
    assert "sharpit-gate" not in JOBS
    lint = JOBS["lint"]
    for step in (
        "uvx --from actionlint-py==1.7.12.25 actionlint",
        "uvx zizmor@1.32.0 --offline --min-severity medium .github/workflows",
        "pytest examples/fastapi_sqla/tests_gate -k fixed --sharpit --sharpit-junit=sharpit-junit.xml",
        '"! uv run --no-sync python -m pytest examples/fastapi_sqla/tests_gate -k n_plus_one --sharpit',
    ):
        assert step in lint, step


def _matrix_jobs(body: str) -> int:
    """Jobs a matrix expands to: the product of its list keys plus its include rows (each a new combination here)."""
    lines = body.splitlines()
    if "      matrix:" not in lines:
        return 1
    block = []
    for line in lines[lines.index("      matrix:") + 1 :]:
        if len(line) - len(line.lstrip()) <= 6:
            break
        block.append(line)
    lists = [len(m[1].split(",")) for line in block if (m := re.fullmatch(r" {8}\w+: \[(.*)\]", line))]
    product = 1 if lists else 0
    for size in lists:
        product *= size
    return product + sum(1 for line in block if line.startswith("          - "))


def test_the_job_count_never_rises() -> None:
    """Every job pays setup and a slot in a 20-runner pool: lower these pins when a job goes, never raise them."""
    assert len(JOBS) == 18
    assert sum(_matrix_jobs(body) for body in JOBS.values()) == 52


def test_the_required_critical_path_is_listed_before_live() -> None:
    """The shards (Windows first) and the coverage leg set the required wall; the not-required live legs go last."""
    names = list(JOBS)
    assert names[:4] == ["changes", "test-shard", "coverage-shard", "lint"]
    rows = [line for line in JOBS["test-shard"].splitlines() if "shard:" in line]
    assert all("windows-latest" in row for row in rows[:6]), "the Windows shards are the long pole: first"
    assert names[-2:] == ["live", "live-check"]


# CI test-seconds per gate file (spec §1, the report's run). A file cannot be split across rows (an env partition would
# leak into the gates' own nested pytest runs), so the heaviest file on an OS is the ceiling for any row on that OS.
GATE_SECONDS = {
    "windows-latest": {
        "tests/masking/test_gates_bite.py": 745,
        "tests/masking/test_masking_scales_linearly.py": 556,
        "tests/masking/test_statement_surfaces.py": 330,
        "tests/scripts/test_lane_gate.py": 101,
    },
    "ubuntu-latest": {
        "tests/masking/test_gates_bite.py": 294,
        "tests/masking/test_masking_scales_linearly.py": 438,
        "tests/masking/test_statement_surfaces.py": 160,
        "tests/scripts/test_lane_gate.py": 6,
    },
}
GATE_ROW_OSES = ("windows-latest", "ubuntu-latest")  # one gate file group per job on both (owner decision)


def _gate_rows(os_name: str) -> list[list[str]]:
    """The gate files each masking-gates job on ``os_name`` runs: its matrix row's files put into the pytest line."""
    body = JOBS["masking-gates"]
    run = next(line for line in body.splitlines() if re.search(r"run:.*\bpytest\b", line))
    rows = re.findall(r"\{ os: ([\w-]+), part: [\w+-]+, files: \"([^\"]+)\" \}", body)
    if not rows and (oses := re.search(r"^\s+os: \[([^\]]+)\]", body, re.MULTILINE)):
        rows = [(name, "") for name in oses[1].split(", ")]
    return [
        re.findall(r"tests/\S+\.py", run.replace("${{ matrix.files }}", files))
        for name, files in rows
        if name == os_name
    ]


@pytest.mark.parametrize("os_name", GATE_ROW_OSES)
def test_each_os_runs_every_gate_file_in_exactly_one_row(os_name: str) -> None:
    files = [file for row in _gate_rows(os_name) for file in row]
    assert sorted(files) == sorted(OWN_JOB_FILES), os_name


@pytest.mark.parametrize("os_name", GATE_ROW_OSES)
def test_no_gate_row_outweighs_the_heaviest_gate_file(os_name: str) -> None:
    """Rows run in parallel, so the heaviest row sets the wall: no row may carry more than the heaviest file."""
    seconds = GATE_SECONDS[os_name]
    loads = [sum(seconds[file] for file in row) for row in _gate_rows(os_name)]
    assert loads, os_name
    assert max(loads) <= max(seconds.values()), f"{os_name}: row loads {loads}"


def test_masking_gate_artifacts_are_unique_per_row() -> None:
    from scripts.ci.shard_weights import parse_artifact

    body = JOBS["masking-gates"]
    for kind in ("junit", "overhead", "speed"):
        assert f"name: {kind}-masking-gates-${{{{ matrix.os }}}}-${{{{ matrix.part }}}}" in body, kind
    assert parse_artifact("overhead-masking-gates-windows-latest-gates-bite") == (
        "masking-gates",
        "windows-latest-gates-bite",
    )


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


def _split_steps(job_body: str) -> list[str]:
    steps: list[str] = []
    current: list[str] = []
    for line in job_body.splitlines():
        if re.match(r"^\s*-\s+", line):
            if current:
                steps.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        steps.append("\n".join(current))
    return steps


def _parse_step_fields(step_text: str) -> dict[str, str]:
    step: dict[str, str] = {"raw": step_text}
    for field in ("id", "if", "uses", "run", "name", "path"):
        m = re.search(rf"^\s*(?:-\s+)?{field}:\s*(.+)$", step_text, re.MULTILINE)
        if m:
            step[field] = m.group(1).strip()
    return step


def _parse_job_steps(job_body: str) -> list[dict[str, str]]:
    return [_parse_step_fields(text) for text in _split_steps(job_body)]


def _assert_job_upload_steps_scanned(job_name: str, job_body: str) -> None:
    steps = _parse_job_steps(job_body)
    upload_steps_found = 0
    for idx, step in enumerate(steps):
        if "actions/upload-artifact" not in step.get("uses", ""):
            continue
        artifact_name = step.get("name", "")
        if not (artifact_name.startswith(("junit-", "overhead-")) or artifact_name == "sharpit-gate-reports"):
            continue
        upload_steps_found += 1

        step_if = step.get("if", "")
        m = re.fullmatch(r"always\(\) && steps\.([a-zA-Z0-9_-]+)\.outcome == 'success'", step_if)
        assert m, (
            f"{job_name}: upload {artifact_name} if: is {step_if!r}, "
            f"expected \"always() && steps.<id>.outcome == 'success'\""
        )
        scan_id = m.group(1)

        preceding_steps = steps[:idx]
        matching_scan = [s for s in preceding_steps if s.get("id") == scan_id]
        assert matching_scan, f"{job_name}: scan step with id {scan_id} not found before upload {artifact_name}"
        scan_step = matching_scan[-1]
        assert scan_step.get("if") == "always()", f"{job_name}: scan step {scan_id} must run if: always()"
        run_cmd = scan_step.get("run", "")
        assert "scripts/ci/artifact_scan.py" in run_cmd, f"{job_name}: scan step {scan_id} must invoke artifact_scan.py"
        assert "--values-file" in run_cmd, f"{job_name}: scan step {scan_id} must pass --values-file"

        upload_path = step.get("path", "")
        if upload_path and upload_path not in ("|", ">"):
            assert upload_path in run_cmd, f"{job_name}: scan step {scan_id} missing path {upload_path}"
        else:
            for path_line in step["raw"].split("path:", 1)[1].splitlines():
                p = path_line.strip()
                if (
                    p
                    and p not in ("|", ">")
                    and not p.startswith("retention-days")
                    and not p.startswith("if-no-files-found")
                ):
                    assert p in run_cmd, f"{job_name}: scan step {scan_id} missing path {p}"
    assert upload_steps_found > 0, f"{job_name}: expected upload steps"


def test_every_upload_is_preceded_by_the_artifact_scan() -> None:
    target_jobs = [
        name
        for name, body in JOBS.items()
        if any(
            "actions/upload-artifact" in line and any(f"name: {p}" in body for p in ("junit-", "overhead-"))
            for line in body.splitlines()
        )
    ]
    assert target_jobs, "no jobs found with junit or overhead uploads"
    for job_name in target_jobs:
        body = JOBS[job_name]
        _assert_job_upload_steps_scanned(job_name, body)

        planted_body = re.sub(
            r"if:\s*always\(\) && steps\.[a-zA-Z0-9_-]+\.outcome == 'success'",
            "if: always()",
            body,
            count=1,
        )
        with pytest.raises(AssertionError):
            _assert_job_upload_steps_scanned(job_name, planted_body)


def test_a_wall_clock_budget_runs_with_the_timing_files(monkeypatch: pytest.MonkeyPatch) -> None:
    # found on #144 CI: the insights read budget (an absolute 2000 ms, no check_budget call) ran inside a parallel
    # Windows shard and failed at 2088 ms beside busy xdist workers
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent))
    from tests._shard import timing_files  # noqa: PLC0415

    assert "tests/engine/insights/test_insights_service.py" in timing_files()
