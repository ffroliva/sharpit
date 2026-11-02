"""Static and behavioural checks over the composite ``action.yml`` (spec 0.4.0 section 5.3).

No YAML parser is a dependency, so a small reader covers the fixed shape of the file: inputs at two spaces, steps
at four, step keys at six, ``env`` entries and ``run`` lines at eight.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ACTION = Path(__file__).parents[2] / "action.yml"
INPUTS = {
    "pytest-args": "",
    "report-only": "true",
    "baseline": "",
    "fail-on": "",
    "report-path": "sharpit-report.json",
    "install": "pip",
    "runner": "python -m pytest",
}
HEREDOC = re.compile(r"python - <<'PY'\n(.*?)\n\s*PY\n", re.DOTALL)


def _text() -> str:
    return ACTION.read_text(encoding="utf-8")


def _inputs(text: str) -> dict[str, dict[str, str]]:
    block = text.split("\ninputs:\n", 1)[-1].split("\nruns:", 1)[0]
    out: dict[str, dict[str, str]] = {}
    for name, body in re.findall(r"^  ([a-z-]+):\n((?:    .*\n?)+)", block, re.MULTILINE):
        out[name] = dict(re.findall(r'^    (description|default): "?(.*?)"?$', body, re.MULTILINE))
    return out


def _steps(text: str) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    for chunk in re.split(r"^    - ", text.split("\n  steps:\n", 1)[-1], flags=re.MULTILINE)[1:]:
        env = dict(re.findall(r"^        ([A-Z_]+): (.*)$", chunk, re.MULTILINE))
        run = chunk.split("      run: |\n", 1)[1] if "      run: |\n" in chunk else ""
        steps.append({"name": chunk.splitlines()[0], "env": env, "run": run})
    return steps


def _step(fragment: str) -> dict[str, object]:
    return next(
        (s for s in _steps(_text()) if fragment.lower() in str(s["name"]).lower()), {"name": "", "env": {}, "run": ""}
    )


def _script(run: str) -> str:
    match = HEREDOC.search(run)
    return textwrap.dedent(match.group(1)) if match else ""


def _run_argv(extra_env: dict[str, str]) -> list[str]:
    """Execute the Run step's Python with a runner that echoes its argv as JSON; return that argv."""
    exe = Path(sys.executable).as_posix()
    runner = f'"{exe}" -c "import sys, json; print(json.dumps(sys.argv[1:]))"'
    env = {
        "RUNNER": runner,
        "PYTEST_ARGS": "",
        "REPORT_ONLY": "true",
        "BASELINE": "",
        "FAIL_ON": "",
        "REPORT_PATH": "r.json",
    }
    done = subprocess.run(
        [sys.executable, "-c", _script(str(_step("Run")["run"]))],
        env=env | extra_env,
        capture_output=True,
        text=True,
        check=False,
    )
    return json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else []


def test_action_declares_all_inputs_and_defaults() -> None:
    inputs = _inputs(_text())
    assert set(inputs) == set(INPUTS)
    assert {name: spec.get("default") for name, spec in inputs.items()} == INPUTS
    assert all(spec.get("description") for spec in inputs.values())


def test_action_version_is_literal() -> None:
    pins = re.findall(r'pip install "sharpit==([^"]+)"', _text())
    assert len(pins) == 1
    assert re.fullmatch(r"[0-9]+[.][0-9]+[.][0-9]+", pins[0])


def test_action_respects_install_none() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    run = str(_step("Install")["run"])
    none = subprocess.run([bash, "-c", run], env={"INSTALL": "none", "PATH": "/nonexistent"}, check=False)
    bogus = subprocess.run(
        [bash, "-c", run], env={"INSTALL": "pipx", "PATH": "/nonexistent"}, capture_output=True, check=False
    )
    assert none.returncode == 0
    assert bogus.returncode == 1
    assert 'if [ "$INSTALL" = "pip" ]' in run


def test_action_forwards_report_only_baseline_fail_on_and_report_path() -> None:
    base = ["--sharpit", "--sharpit-report", "r.json"]
    assert _run_argv({}) == [*base, "--sharpit-report-only"]
    full = _run_argv({"REPORT_ONLY": "false", "BASELINE": "b.json", "FAIL_ON": "HIGH"})
    # finding: report-only false must override a sharpit_report_only = true ini setting
    assert full == [
        *base,
        "-o",
        "sharpit_report_only=false",
        "--sharpit-baseline",
        "b.json",
        "--sharpit-fail-on",
        "HIGH",
    ]


def test_action_rejects_invalid_report_only() -> None:
    # finding: report-only "yes" silently gated the build instead of failing the step
    runner = f'"{Path(sys.executable).as_posix()}" -c "print(42)"'
    env = {"RUNNER": runner, "PYTEST_ARGS": "", "REPORT_ONLY": "yes", "BASELINE": "", "FAIL_ON": "", "REPORT_PATH": "r"}
    done = subprocess.run(
        [sys.executable, "-c", _script(str(_step("Run")["run"]))], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 1
    assert "42" not in done.stdout


def test_action_removes_stale_report_before_pytest() -> None:
    # finding: a report left by an earlier step was summarised when pytest wrote none
    run = str(_step("Run")["run"])
    assert 'rm -f "$REPORT_PATH"' in run
    assert run.index('rm -f "$REPORT_PATH"') < run.index("python -")


def test_action_runner_default() -> None:
    assert _inputs(_text()).get("runner", {}).get("default") == "python -m pytest"


def test_action_invokes_summary_cli() -> None:
    run = str(_step("summary")["run"])
    assert 'python -m sharpit.report summary "$REPORT_PATH"' in run
    assert '>> "$GITHUB_STEP_SUMMARY"' in run
    assert "always()" in _text()


def test_action_pytest_args_are_shlex_split_not_shell_evaluated() -> None:
    payload = '-k "a and b" ; echo pwned $(id) `id` | tee x'
    argv = _run_argv({"PYTEST_ARGS": payload})
    assert argv[:9] == ["-k", "a and b", ";", "echo", "pwned", "$(id)", "`id`", "|", "tee"]
    assert "shlex.split" in _script(str(_step("Run")["run"]))


def test_action_has_no_expressions_inside_run_and_all_inputs_use_env() -> None:
    steps = _steps(_text())
    assert steps
    assert all("${{" not in str(s["run"]) for s in steps)
    expression_lines = [line for line in _text().splitlines() if "${{" in line]
    env_entry = re.compile(r"^        [A-Z_]+: [$]{{ inputs[.][a-z-]+ }}$")
    assert expression_lines
    assert all(env_entry.match(line) or line.strip().startswith("if:") for line in expression_lines)
    used = {m for s in steps for m in re.findall(r"inputs[.]([a-z-]+)", " ".join(s["env"].values()))}  # type: ignore[union-attr]
    assert used == set(INPUTS)


def test_action_quotes_every_expansion() -> None:
    steps = [s for s in _steps(_text()) if s["run"]]
    assert steps
    for step in steps:
        bash = HEREDOC.sub("", str(step["run"]))
        for line in bash.splitlines():
            for match in re.finditer(r"[$][{]?[A-Za-z_][A-Za-z0-9_]*[}]?", line):
                assert line[: match.start()].count('"') % 2 == 1, line


def test_action_preserves_windows_paths_in_pytest_args() -> None:
    # finding: POSIX shlex.split turned tests\test_file.py into teststest_file.py on Windows runners
    argv = _run_argv({"RUNNER_OS": "Windows", "PYTEST_ARGS": 'tests\\test_file.py -k "a b"'})
    assert argv[:3] == ["tests\\test_file.py", "-k", "a b"], argv


def test_action_has_no_unquoted_or_expression_run_values() -> None:
    for step in _steps(_text()):
        assert "${{" not in str(step["run"])
        assert "eval " not in str(step["run"])
