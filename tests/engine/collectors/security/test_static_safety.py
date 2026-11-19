"""Safety, secrecy, performance, boundary, and non-FastAPI host tests for SEC-STATIC-001."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import SideEffectGuard
from sharpit.engine.collectors.security.report import SecurityService, build_inputs
from sharpit.engine.collectors.security.static_analysis import (
    LIMITATION_TEXT,
    RULE_ID,
    State,
    StaticSecurityAnalysisDetector,
    strip_yaml_comments,
)
from sharpit.engine.spi import SecurityFacts, SecurityModel


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_secret_canary_never_leaked(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A secret canary in inspected files and malformed setup.cfg lines appears nowhere."""
    project = tmp_path / "app_canary"
    canaries = [
        "CANARY_SECRET_PYPROJECT_ALPHA_999",
        "CANARY_SECRET_SETUP_CFG_BRAVO_888",
        "CANARY_SECRET_TOX_CHARLIE_777",
        "CANARY_SECRET_SEMGREP_DELTA_666",
        "CANARY_SECRET_SONAR_ECHO_555",
        "CANARY_SECRET_PRECOMMIT_FOXTROT_444",
        "CANARY_SECRET_REQ_GOLF_333",
        "CANARY_SECRET_WORKFLOW_HOTEL_222",
        "CANARY_MALFORMED_LINE_SECRET_111",
    ]

    # Write files containing canaries (malformed setup.cfg without configured analyzer)
    _write(project / "pyproject.toml", f'[project]\nname = "canary"\ndescription = "{canaries[0]}"\n')
    # Malformed setup.cfg with canary on broken line
    _write(project / "setup.cfg", f"[broken_section\n{canaries[8]}=secret\nkey={canaries[1]}\n")
    _write(project / "tox.ini", f"[testenv]\ndescription = {canaries[2]}\n")
    _write(project / ".pre-commit-config.yaml", f"repos: []\n# {canaries[5]}\n")
    _write(project / "requirements.txt", f"# requirement file with {canaries[6]}\nfastapi\n")
    _write(project / ".github" / "workflows" / "ci.yml", f"name: CI\n# {canaries[7]}\non: [push]\njobs: {{}}\n")

    inputs = build_inputs(
        SecurityModel(False, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        app_settings_stub(project),  # pyright: ignore[reportArgumentType]
    )
    # Force project_root to canary directory
    inputs_with_root = inputs.__class__(
        inputs.model, inputs.facts, inputs.source, inputs.view, inputs.limitations, project_root=project
    )

    with caplog.at_level(logging.DEBUG):
        detector = StaticSecurityAnalysisDetector()
        inspection = detector.inspect(project)
        assert inspection.state == State.INDETERMINATE

        service = SecurityService(
            lambda: inputs_with_root,
            dismissal_store_stub(tmp_path),  # pyright: ignore[reportArgumentType]
            masker_stub(),  # pyright: ignore[reportArgumentType]
            single_flight_stub(),  # pyright: ignore[reportArgumentType]
            max_retained=1000,
        )
        report = service.scan()

    report_str = str(report)
    log_str = caplog.text

    for canary in canaries:
        assert canary not in report_str
        assert canary not in log_str

    # Also test configured project with sonar.login secret
    project2 = tmp_path / "app_canary_sonar"
    _write(project2 / "pyproject.toml", '[project]\nname = "canary2"\n')
    _write(project2 / "sonar-project.properties", f"sonar.projectKey=test\nsonar.login={canaries[4]}\n")
    inputs2 = inputs.__class__(
        inputs.model, inputs.facts, inputs.source, inputs.view, inputs.limitations, project_root=project2
    )
    service2 = SecurityService(
        lambda: inputs2,
        dismissal_store_stub(tmp_path),  # pyright: ignore[reportArgumentType]
        masker_stub(),  # pyright: ignore[reportArgumentType]
        single_flight_stub(),  # pyright: ignore[reportArgumentType]
        max_retained=1000,
    )
    report2 = service2.scan()
    assert canaries[4] not in str(report2)


def test_oversized_file_and_workflow_limits(tmp_path: Path) -> None:
    """1 MiB + 1 byte -> INDETERMINATE; 1 MiB adversarial workflow < 1 s; 65 workflows -> INDETERMINATE."""
    detector = StaticSecurityAnalysisDetector()

    # 1. 1 MiB + 1 byte build file -> INDETERMINATE
    t1 = tmp_path / "oversized"
    _write(t1 / "pyproject.toml", "# " + "a" * (1_048_576 + 1))
    assert detector.inspect(t1).state == State.INDETERMINATE

    # 2. 1 MiB adversarial workflow processed in < 1.0 second
    adversarial = ('name: "test"\nrun: |\n  echo "hello # not comment"\n# comment\n' * 25_000)[: 1024 * 1024]
    start = time.perf_counter()
    cleaned = strip_yaml_comments(adversarial)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0
    assert len(cleaned) > 0

    # 3. 65 workflows -> INDETERMINATE
    t3 = tmp_path / "many_workflows"
    _write(t3 / "pyproject.toml", '[project]\nname = "test"\n')
    wf_dir = t3 / ".github" / "workflows"
    for i in range(65):
        _write(wf_dir / f"wf_{i:02d}.yml", "name: WF\non: [push]\njobs: {}\n")
    assert detector.inspect(t3).state == State.INDETERMINATE


def test_ruff_configuration_matrix(tmp_path: Path) -> None:
    """Ruff cases: select S -> CONFIGURED; ALL with ignore S -> NOT_CONFIGURED; ALL -> CONFIGURED."""
    detector = StaticSecurityAnalysisDetector()

    # Case 1: select = ["S"] -> CONFIGURED
    p1 = tmp_path / "ruff_s"
    _write(p1 / "pyproject.toml", '[project]\nname = "p1"\n\n[tool.ruff.lint]\nselect = ["S"]\n')
    assert detector.inspect(p1).state == State.CONFIGURED

    # Case 2: ALL with ignore = ["S"] -> NOT_CONFIGURED
    p2 = tmp_path / "ruff_all_ignore_s"
    _write(p2 / "pyproject.toml", '[project]\nname = "p2"\n\n[tool.ruff.lint]\nselect = ["ALL"]\nignore = ["S"]\n')
    assert detector.inspect(p2).state == State.NOT_CONFIGURED

    # Case 3: ALL without ignore -> CONFIGURED
    p3 = tmp_path / "ruff_all"
    _write(p3 / "pyproject.toml", '[project]\nname = "p3"\n\n[tool.ruff.lint]\nselect = ["ALL"]\n')
    assert detector.inspect(p3).state == State.CONFIGURED

    # Case 4: separate ruff.toml -> INDETERMINATE
    p4 = tmp_path / "ruff_separate"
    _write(p4 / "pyproject.toml", '[project]\nname = "p4"\n')
    _write(p4 / "ruff.toml", '[lint]\nselect = ["S"]\n')
    assert detector.inspect(p4).state == State.INDETERMINATE

    # Case 5: extend in pyproject.toml -> INDETERMINATE
    p5 = tmp_path / "ruff_extend"
    _write(p5 / "pyproject.toml", '[project]\nname = "p5"\n\n[tool.ruff]\nextend = "other.toml"\n')
    assert detector.inspect(p5).state == State.INDETERMINATE


def test_non_fastapi_host_report_behaviour(tmp_path: Path) -> None:
    """Non-FastAPI host with build file -> PARTIAL with 1 INFO finding; without build file -> DISABLED."""
    # 1. Non-FastAPI host with pyproject.toml without security analyzer
    p1 = tmp_path / "non_fastapi_with_build"
    _write(p1 / "pyproject.toml", '[project]\nname = "test"\nversion = "0.1.0"\n')

    inputs1 = build_inputs(
        SecurityModel(False, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        app_settings_stub(p1),  # pyright: ignore[reportArgumentType]
    )
    inputs1 = inputs1.__class__(
        inputs1.model, inputs1.facts, inputs1.source, inputs1.view, inputs1.limitations, project_root=p1
    )
    service1 = SecurityService(
        lambda: inputs1,
        dismissal_store_stub(tmp_path),  # pyright: ignore[reportArgumentType]
        masker_stub(),  # pyright: ignore[reportArgumentType]
        single_flight_stub(),  # pyright: ignore[reportArgumentType]
        max_retained=1000,
    )
    report1 = service1.scan()
    assert report1["scan"]["status"] == "PARTIAL"
    assert report1["rulesEvaluated"] == 1
    assert len(report1["results"]) == 1
    assert report1["results"][0]["id"] == RULE_ID
    assert report1["results"][0]["severity"] == "INFO"

    # 2. Non-FastAPI host without build file -> DISABLED
    p2 = tmp_path / "non_fastapi_no_build"
    p2.mkdir(parents=True)
    inputs2 = build_inputs(
        SecurityModel(False, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        app_settings_stub(p2),  # pyright: ignore[reportArgumentType]
    )
    inputs2 = inputs2.__class__(
        inputs2.model, inputs2.facts, inputs2.source, inputs2.view, inputs2.limitations, project_root=p2
    )
    service2 = SecurityService(
        lambda: inputs2,
        dismissal_store_stub(tmp_path),  # pyright: ignore[reportArgumentType]
        masker_stub(),  # pyright: ignore[reportArgumentType]
        single_flight_stub(),  # pyright: ignore[reportArgumentType]
        max_retained=1000,
    )
    report2 = service2.scan()
    assert report2["scan"]["status"] == "DISABLED"
    assert report2["results"] == []


def test_fifo_pyproject_posix(tmp_path: Path) -> None:
    """FIFO pyproject (POSIX, skip elsewhere) -> INDETERMINATE within 2 s and next scan is not 409."""
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFOs not supported on this platform")

    fifo_path = tmp_path / "pyproject.toml"
    os.mkfifo(fifo_path)

    detector = StaticSecurityAnalysisDetector()
    start = time.perf_counter()
    inspection = detector.inspect(tmp_path)
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0
    assert inspection.state == State.INDETERMINATE

    inputs = build_inputs(
        SecurityModel(False, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        app_settings_stub(tmp_path),  # pyright: ignore[reportArgumentType]
    )
    inputs = inputs.__class__(
        inputs.model, inputs.facts, inputs.source, inputs.view, inputs.limitations, project_root=tmp_path
    )
    service = SecurityService(
        lambda: inputs,
        dismissal_store_stub(tmp_path),  # pyright: ignore[reportArgumentType]
        masker_stub(),  # pyright: ignore[reportArgumentType]
        single_flight_stub(),  # pyright: ignore[reportArgumentType]
        max_retained=1000,
    )

    report = service.scan()
    assert report["scan"]["status"] == "PARTIAL"
    assert LIMITATION_TEXT in report["evidence"]["limitations"]

    # Next scan runs immediately without 409
    report2 = service.scan()
    assert report2["scan"]["status"] == "PARTIAL"


def test_get_mcp_cli_reads_open_no_files_before_or_after_scan(tmp_path: Path, no_side_effects: SideEffectGuard) -> None:
    """GET /security and MCP/CLI reads never open build or source files; scan does (positive control)."""
    project = tmp_path / "monitored_project"
    _write(project / "pyproject.toml", '[project]\nname = "test"\n')

    inputs = build_inputs(
        SecurityModel(False, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        app_settings_stub(project),  # pyright: ignore[reportArgumentType]
    )
    inputs_with_root = inputs.__class__(
        inputs.model, inputs.facts, inputs.source, inputs.view, inputs.limitations, project_root=project
    )
    service = SecurityService(
        lambda: inputs_with_root,
        dismissal_store_stub(tmp_path),  # pyright: ignore[reportArgumentType]
        masker_stub(),  # pyright: ignore[reportArgumentType]
        single_flight_stub(),  # pyright: ignore[reportArgumentType]
        max_retained=1000,
    )

    no_side_effects.watch_sources(project)

    # 1. Before scan: report() opens 0 project files
    service.report()
    assert no_side_effects.source_reads == []

    # 2. Positive control: scan DOES open project files
    service.scan()
    assert no_side_effects.source_reads != []
    no_side_effects.source_reads.clear()

    # 3. After scan: report() and violations() open 0 project files
    report = service.report()
    assert no_side_effects.source_reads == []
    service.violations(RULE_ID, report["violationDetails"]["scanId"], 0, 100)
    assert no_side_effects.source_reads == []


def test_not_present_model_with_introspection_error_retains_limitations(tmp_path: Path) -> None:
    """Introspection error is kept in message and evidence across all states."""
    p = tmp_path / "app_not_present"
    _write(p / "pyproject.toml", '[project]\nname = "app"\n')

    # Case 1: NOT_CONFIGURED (pyproject without analyzer)
    model = SecurityModel(False, (), (), (), ("FastAPI security could not be read (RuntimeError).",))
    inputs = build_inputs(
        model,
        SecurityFacts(False, None, (), (), ()),
        None,
        app_settings_stub(p),  # pyright: ignore[reportArgumentType]
    )
    inputs_with_root = inputs.__class__(
        inputs.model, inputs.facts, inputs.source, inputs.view, inputs.limitations, project_root=p
    )
    service = SecurityService(
        lambda: inputs_with_root,
        dismissal_store_stub(tmp_path),  # pyright: ignore[reportArgumentType]
        masker_stub(),  # pyright: ignore[reportArgumentType]
        single_flight_stub(),  # pyright: ignore[reportArgumentType]
        max_retained=1000,
    )
    report = service.scan()
    expected_msg = (
        "FastAPI security configuration could not be read: FastAPI security could not be read (RuntimeError)."
    )
    assert expected_msg in report["scan"]["message"]
    assert "FastAPI security could not be read (RuntimeError)." in report["evidence"]["limitations"]

    # Case 2: CONFIGURED
    _write(p / "requirements.txt", "bandit>=1.7\n")
    report2 = service.scan()
    assert "could not be read: FastAPI security could not be read (RuntimeError)." in report2["scan"]["message"]
    assert "FastAPI security could not be read (RuntimeError)." in report2["evidence"]["limitations"]

    # Case 3: INDETERMINATE (oversized requirements.txt)
    _write(p / "requirements.txt", "x\n" * 600_000)
    report3 = service.scan()
    assert "could not be read: FastAPI security could not be read (RuntimeError)." in report3["scan"]["message"]
    assert "FastAPI security could not be read (RuntimeError)." in report3["evidence"]["limitations"]
    assert LIMITATION_TEXT in report3["evidence"]["limitations"]


def test_static_only_report_analyzer_and_disclaimer(tmp_path: Path) -> None:
    """When only the static rule ran (model not present, no discovery error), use static analyzer and disclaimer."""
    p = tmp_path / "static_only"
    _write(p / "pyproject.toml", '[project]\nname = "app"\n')

    inputs = build_inputs(
        SecurityModel(False, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        app_settings_stub(p),  # pyright: ignore[reportArgumentType]
    )
    inputs_with_root = inputs.__class__(
        inputs.model, inputs.facts, inputs.source, inputs.view, inputs.limitations, project_root=p
    )
    service = SecurityService(
        lambda: inputs_with_root,
        dismissal_store_stub(tmp_path),  # pyright: ignore[reportArgumentType]
        masker_stub(),  # pyright: ignore[reportArgumentType]
        single_flight_stub(),  # pyright: ignore[reportArgumentType]
        max_retained=1000,
    )
    report = service.scan()
    assert report["scan"]["analyzer"] == "sharpit Static Security Advisor"
    assert report["disclaimer"] == (
        "This limited check inspects local analyzer configuration only. It does not assess runtime security or"
        " verify that a configured analyzer ran."
    )


def test_rule_description_python_limits() -> None:
    """Rule SEC-STATIC-001 description describes Python limits, not Maven/Gradle."""
    from sharpit.engine.collectors.security.static_analysis import StaticSecurityAnalysisRule

    desc = StaticSecurityAnalysisRule.DESCRIPTION
    assert "Maven" not in desc
    assert "Gradle" not in desc
    assert "ruff.toml" in desc
    assert "-r" in desc
    assert "remote or organization-managed" in desc


def test_build_inputs_derives_project_root_from_app_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """build_inputs derives project_root from app_package without hard-coding."""
    import types

    proj = tmp_path / "pkg_root_test"
    pkg = proj / "src" / "sample_app"
    _write(pkg / "__init__.py", "")
    _write(proj / "pyproject.toml", '[project]\nname = "sample_app"\nversion = "0.1.0"\n')

    mod = types.ModuleType("sample_app")
    mod.__file__ = str(pkg / "__init__.py")
    mod.__path__ = [str(pkg)]

    monkeypatch.setitem(sys.modules, "sample_app", mod)
    monkeypatch.syspath_prepend(str(proj / "src"))

    settings = app_settings_stub("sample_app")
    assert settings.app_package == "sample_app"

    inputs = build_inputs(
        SecurityModel(False, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        settings,
    )
    assert inputs.project_root == proj.resolve()


def test_windows_junction_refusal(tmp_path: Path) -> None:
    """Windows junctions are refused and reported as INDETERMINATE."""
    if sys.platform != "win32":
        pytest.skip("Windows junctions only supported on Windows")
    import _winapi

    outside = tmp_path / "outside_target"
    _write(outside / "ci.yml", "name: CI\n")
    repo = tmp_path / "repo_with_junction"
    _write(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    _write(repo / "pyproject.toml", '[project]\nname = "test"\n')

    github_dir = repo / ".github"
    github_dir.mkdir(parents=True)
    workflows_junc = github_dir / "workflows"
    _winapi.CreateJunction(str(outside), str(workflows_junc))

    detector = StaticSecurityAnalysisDetector()
    assert workflows_junc.is_junction()
    assert detector.inspect(repo).state == State.INDETERMINATE


def test_security_collector_never_imports_architecture() -> None:
    """Security collector never imports architecture collector (architecture rule 3)."""
    from tests.engine.test_import_boundary import collector_violations

    violations = collector_violations()
    assert not any("security" in v and "architecture" in v for v in violations)
    assert violations == []


# Helpers for test stubs
def app_settings_stub(project_root_or_package: Path | str) -> Any:
    from sharpit.settings import SharpitSettings

    pkg = project_root_or_package if isinstance(project_root_or_package, str) else project_root_or_package.name
    return SharpitSettings(app_package=pkg)


def dismissal_store_stub(tmp_path: Path) -> Any:
    from sharpit.engine.advisors.dismissals import DismissalStore

    return DismissalStore(tmp_path / "dismissals_store")


def masker_stub() -> Any:
    from sharpit.engine.masking import Exposure, Masker

    return Masker(Exposure.MASKED, True)


def single_flight_stub() -> Any:
    from sharpit.engine.singleflight import SingleFlight

    return SingleFlight()
