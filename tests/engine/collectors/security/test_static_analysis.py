"""Tests for SEC-STATIC-001 detector (port of BootUI 2.4.0 StaticSecurityAnalysisDetectorTests)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.advisors.dismissals import DismissalStore
from sharpit.engine.collectors.security.report import SecurityService, build_inputs, scan_evaluation
from sharpit.engine.collectors.security.static_analysis import (
    LIMITATION_TEXT,
    RULE_ID,
    State,
    StaticSecurityAnalysisDetector,
    _repository_root,
    _split_shell_commands,
    strip_yaml_comments,
)
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import SecurityFacts, SecurityModel
from sharpit.settings import SharpitSettings


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ported: StaticSecurityAnalysisDetectorTests.reportsUnconfiguredOnlyWhenAReadableBuildFileExists
def test_reports_unconfigured_only_when_a_readable_build_file_exists(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    assert detector.inspect(tmp_path).state == State.NOT_APPLICABLE

    _write(tmp_path / "pyproject.toml", '[project]\nname = "test"\nversion = "0.1.0"\n')
    assert detector.inspect(tmp_path).state == State.NOT_CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.recognizesMavenPluginManagementProfilesAndFindSecBugsDependency
def test_recognizes_bandit_in_pyproject(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "test"\nversion = "0.1.0"\n\n[tool.bandit]\nexclude_dirs = ["tests"]\n',
    )
    assert detector.inspect(tmp_path).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.treatsAnEmptyMavenRelativePathAsNoLocalParentToInspect
def test_treats_pyproject_without_parent_or_analyzer_as_not_configured(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "application"\nversion = "1.0.0"\ndependencies = ["fastapi", "sqlalchemy"]\n',
    )
    assert detector.inspect(tmp_path).state == State.NOT_CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.recognizesMavenSonarAndLocalParentDeclarations
def test_recognizes_sonar_project_properties_and_repo_root(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    module = tmp_path / "module"
    _write(tmp_path / ".git" / "HEAD", "ref: refs/heads/main\n")
    _write(tmp_path / "sonar-project.properties", "sonar.projectKey=test\n")
    _write(module / "pyproject.toml", '[project]\nname = "module"\nversion = "1.0.0"\n')

    assert detector.inspect(module).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.recognizesMavenParentPomInsideRelativePathDirectory
def test_recognizes_repo_root_analyzer_from_submodule(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    module = tmp_path / "module"
    _write(tmp_path / ".git" / "HEAD", "ref: refs/heads/main\n")
    _write(tmp_path / "pyproject.toml", '[tool.bandit]\nexclude_dirs = ["tests"]\n')
    _write(module / "pyproject.toml", '[project]\nname = "submodule"\nversion = "1.0.0"\n')

    assert detector.inspect(module).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.followsMavenParentsThatInheritGroupAndVersion
def test_follows_repo_root_semgrep_config_from_submodule(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    module = tmp_path / "module"
    _write(tmp_path / ".git" / "HEAD", "ref: refs/heads/main\n")
    _write(tmp_path / ".semgrep.yml", "rules:\n  - id: example\n    message: test\n")
    _write(module / "pyproject.toml", '[project]\nname = "submodule"\nversion = "1.0.0"\n')

    assert detector.inspect(module).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.reportsAnUninspectedDefaultParentOutsideTheRepositoryAsIndeterminate
def test_reports_config_symlinked_outside_repo_as_indeterminate(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    outside = tmp_path / "outside"
    repo = tmp_path / "repo"
    _write(outside / "external.yml", "rules: []\n")
    _write(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    _write(repo / "pyproject.toml", '[project]\nname = "test"\n')

    # Symlink to outside
    try:
        (repo / ".semgrep.yml").symlink_to(outside / "external.yml")
    except OSError:
        pytest.skip("Symlinks not supported in this environment")

    assert detector.inspect(repo).state == State.INDETERMINATE


# ported: StaticSecurityAnalysisDetectorTests.doesNotInspectAnUnrelatedPomAsTheDeclaredMavenParent
def test_does_not_inspect_unrelated_file_outside_project_root(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    unrelated = tmp_path / "unrelated"
    project = tmp_path / "project"
    _write(unrelated / "sonar-project.properties", "sonar.projectKey=other\n")
    _write(project / "pyproject.toml", '[project]\nname = "isolated"\n')

    assert detector.inspect(project).state == State.NOT_CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.recognizesGradlePluginsVersionCatalogAliasesAndKnownConfigFiles
def test_recognizes_semgrep_and_setup_cfg_configurations(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(tmp_path / "setup.cfg", "[bandit]\nexclude = tests\n")
    assert detector.inspect(tmp_path).state == State.CONFIGURED

    tmp_path2 = tmp_path / "test2"
    _write(tmp_path2 / "setup.cfg", "[metadata]\nname = pkg\n")
    _write(tmp_path2 / ".semgrep.yml", "rules: []\n")
    assert detector.inspect(tmp_path2).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.recognizesKotlinApplyPluginSyntax
def test_recognizes_bandit_in_requirements_txt(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(tmp_path / "requirements.txt", "fastapi>=0.100.0\nbandit>=1.7.0\nuvicorn\n")
    assert detector.inspect(tmp_path).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.recognizesGroovyNamedArgumentPluginApplication
def test_recognizes_semgrep_in_requirements_txt(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(tmp_path / "requirements-dev.txt", "pytest\nsemgrep\n")
    assert detector.inspect(tmp_path).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.marksUninspectedGradleBuildLogicAsIndeterminate
def test_marks_uninspected_ruff_extend_or_separate_toml_as_indeterminate(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "test"\n\n[tool.ruff]\nextend = "base.toml"\n',
    )
    assert detector.inspect(tmp_path).state == State.INDETERMINATE

    tmp2 = tmp_path / "t2"
    _write(tmp2 / "pyproject.toml", '[project]\nname = "test"\n')
    _write(tmp2 / "ruff.toml", 'extend = "base.toml"\n')
    assert detector.inspect(tmp2).state == State.INDETERMINATE


# ported: StaticSecurityAnalysisDetectorTests.doesNotTreatSpotBugsAnnotationsAsAnAnalyzerPlugin
def test_does_not_treat_unrelated_packages_or_annotations_as_analyzer(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "test"\ndependencies = ["pydantic", "starlette", "cryptography"]\n',
    )
    assert detector.inspect(tmp_path).state == State.NOT_CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.stripsGradleCommentsWithoutTruncatingUrlsOrSlowingOnUnterminatedComments
def test_strips_yaml_comments_without_truncating_urls_or_slowing(tmp_path: Path) -> None:
    text = (
        'name: "CI # not a comment"\n'
        "# Full line comment\n"
        'url: "https://example.com/api#section"\n'
        "key: value # inline comment\n"
    )
    cleaned = strip_yaml_comments(text)
    assert 'name: "CI # not a comment"' in cleaned
    assert 'url: "https://example.com/api#section"' in cleaned
    assert "key: value" in cleaned
    assert "# inline comment" not in cleaned


# ported: StaticSecurityAnalysisDetectorTests.ignoresAnalyzerExamplesInsideGradleStringsAndCatalogComments
def test_ignores_analyzer_names_inside_comments_and_docstrings(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "test"\ndescription = "An app with no bandit analyzer"\n# bandit should be added later\n',
    )
    assert detector.inspect(tmp_path).state == State.NOT_CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.checksGradlePluginStringContextInBoundedTime
def test_checks_yaml_and_config_context_in_bounded_time(tmp_path: Path) -> None:
    # 1 MiB adversarial content: many repeated quotes and hashes
    adversarial = ('"quoted" # comment\n' * 50_000)[: 1024 * 1024]
    cleaned = strip_yaml_comments(adversarial)
    assert cleaned.count("#") == 0


# ported: StaticSecurityAnalysisDetectorTests.recognizesSemgrepAndSonarProjectConfiguration
def test_recognizes_semgrep_and_sonar_project_configuration(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(tmp_path / "pyproject.toml", '[project]\nname = "test"\n')
    _write(tmp_path / "sonar-project.properties", "sonar.projectKey=my-proj\n")
    assert detector.inspect(tmp_path).state == State.CONFIGURED

    tmp2 = tmp_path / "t2"
    _write(tmp2 / "pyproject.toml", '[project]\nname = "test"\n')
    _write(tmp2 / ".semgrep" / "config.yml", "rules: []\n")
    assert detector.inspect(tmp2).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.recognizesRepositoryLevelCodeQlWorkflow
def test_recognizes_repository_level_codeql_workflow(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(tmp_path / "pyproject.toml", '[project]\nname = "test"\n')
    workflow = tmp_path / ".github" / "workflows" / "codeql.yml"
    _write(
        workflow,
        "name: CodeQL\non: [push]\njobs:\n  analyze:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: github/codeql-action/analyze@v3\n",
    )
    assert detector.inspect(tmp_path).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.recognizesAnalyzerWorkflowsWithoutMatchingNamesOrComments
def test_recognizes_analyzer_workflows_without_matching_names_or_comments(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(tmp_path / "pyproject.toml", '[project]\nname = "test"\n')
    workflow = tmp_path / ".github" / "workflows" / "build.yaml"
    _write(
        workflow,
        "name: Build\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: bandit -r src/\n",
    )
    assert detector.inspect(tmp_path).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.
# continuesPastEmptyOversizedAndSymlinkedFilesWhenAnalyzerIsDeclaredElsewhere
def test_continues_past_oversized_and_symlinked_files_when_analyzer_declared_elsewhere(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    # Oversized build file
    _write(tmp_path / "requirements.txt", "x\n" * 600_000)  # > 1 MiB
    # But pyproject declares bandit
    _write(tmp_path / "pyproject.toml", '[tool.bandit]\nexclude_dirs = ["tests"]\n')
    assert detector.inspect(tmp_path).state == State.CONFIGURED


# ported: StaticSecurityAnalysisDetectorTests.treatsWorkflowDirectoriesSymlinkedOutsideTheRepositoryAsIndeterminate
def test_treats_workflow_directories_symlinked_outside_repo_as_indeterminate(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    outside = tmp_path / "outside_workflows"
    _write(outside / "ci.yml", "name: CI\n")
    repo = tmp_path / "repo"
    _write(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    _write(repo / "pyproject.toml", '[project]\nname = "test"\n')

    try:
        (repo / ".github").mkdir(parents=True)
        (repo / ".github" / "workflows").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks not supported in this environment")

    assert detector.inspect(repo).state == State.INDETERMINATE


# ported: StaticSecurityAnalysisDetectorTests.treatsMalformedXmlUnresolvableLocalParentsAndOversizedFilesAsIndeterminate
def test_treats_malformed_build_file_and_oversized_files_as_indeterminate(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    # Malformed TOML syntax
    _write(tmp_path / "pyproject.toml", "[project\nname = invalid\n")
    assert detector.inspect(tmp_path).state == State.INDETERMINATE

    # Oversized pyproject
    tmp2 = tmp_path / "oversized"
    _write(tmp2 / "pyproject.toml", "# " + "a" * (1_048_576 + 10))
    assert detector.inspect(tmp2).state == State.INDETERMINATE


# ported: StaticSecurityAnalysisDetectorTests.staticOnlyAdvisorDoesNotClaimRuntimeEvidenceOrScanOnRead
def test_static_only_advisor_does_not_claim_runtime_evidence_or_scan_on_read(tmp_path: Path) -> None:
    from sharpit.engine.advisors.dismissals import DismissalStore
    from sharpit.engine.collectors.security import Inputs
    from sharpit.engine.collectors.security.report import SecurityService
    from sharpit.engine.masking import Exposure, Masker
    from sharpit.engine.singleflight import SingleFlight
    from sharpit.engine.spi import SecurityFacts, SecurityModel

    _write(tmp_path / "pyproject.toml", '[project]\nname = "test"\nversion = "0.1.0"\n')
    introspections = 0

    def make_inputs() -> Inputs:
        nonlocal introspections
        introspections += 1
        return Inputs(
            model=SecurityModel(False, (), (), (), ()),
            facts=SecurityFacts(False, None, (), (), ()),
            source=None,
            project_root=tmp_path,
        )

    service = SecurityService(
        make_inputs,
        DismissalStore(tmp_path / "dismissals"),
        Masker(Exposure.MASKED, True),
        SingleFlight(),
        max_retained=1000,
    )

    report_pre = service.report()
    assert report_pre["scan"]["status"] == "NOT_SCANNED"
    assert report_pre["results"] == []
    assert introspections == 0

    report_scanned = service.scan()
    assert introspections == 1
    assert report_scanned["scan"]["status"] == "PARTIAL"
    assert report_scanned["rulesEvaluated"] == 1
    assert report_scanned["evidence"]["usable"] is False
    assert len(report_scanned["results"]) == 1
    result = report_scanned["results"][0]
    assert result["id"] == RULE_ID
    assert result["severity"] == "INFO"
    assert result["status"] == "VIOLATION"
    assert "Bandit" in result["recommendation"]
    assert "remote or organization-managed" in result["description"]

    # Rule violations query
    violations = service.violations(RULE_ID, report_scanned["violationDetails"]["scanId"], 0, None)
    assert violations["violationCount"] == 1

    # Add analyzer declaration, scan again
    _write(tmp_path / "sonar-project.properties", "sonar.projectKey=test\n")
    report_cached = service.report()
    assert report_cached["scan"]["status"] == "PARTIAL"
    assert introspections == 1  # cached, no rescan

    report_rescan = service.scan()
    assert report_rescan["results"] == []
    assert introspections == 2


# ported: StaticSecurityAnalysisDetectorTests.staticOnlyAdvisorReportsProjectRootInspectionFailure
def test_static_only_advisor_reports_project_root_inspection_failure(tmp_path: Path) -> None:
    from sharpit.engine.advisors.dismissals import DismissalStore
    from sharpit.engine.collectors.security import Inputs
    from sharpit.engine.collectors.security.report import SecurityService
    from sharpit.engine.masking import Exposure, Masker
    from sharpit.engine.singleflight import SingleFlight
    from sharpit.engine.spi import SecurityFacts, SecurityModel

    # Directory with an oversized build file so inspection fails with INDETERMINATE
    _write(tmp_path / "pyproject.toml", "x" * (1_048_576 + 10))

    service = SecurityService(
        lambda: Inputs(
            model=SecurityModel(False, (), (), (), ()),
            facts=SecurityFacts(False, None, (), (), ()),
            source=None,
            project_root=tmp_path,
        ),
        DismissalStore(tmp_path / "dismissals"),
        Masker(Exposure.MASKED, True),
        SingleFlight(),
        max_retained=1000,
    )

    report = service.scan()
    assert report["scan"]["status"] == "PARTIAL"
    assert "could not be assessed" in report["scan"]["message"]
    assert report["evidence"]["usable"] is False
    assert LIMITATION_TEXT in report["evidence"]["limitations"]
    assert report["results"] == []


def test_pep_508_requirement_variants(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()

    # 1. bandit >= 1.7 in requirements.txt
    p1 = tmp_path / "p1"
    _write(p1 / "requirements.txt", "bandit >= 1.7\n")
    assert detector.inspect(p1).state == State.CONFIGURED

    # 2. bandit ; python_version>'3.8' in requirements.txt
    p2 = tmp_path / "p2"
    _write(p2 / "requirements.txt", "bandit ; python_version>'3.8'\n")
    assert detector.inspect(p2).state == State.CONFIGURED

    # 3. bandit @ git+https://... in requirements.txt
    p3 = tmp_path / "p3"
    _write(p3 / "requirements.txt", "bandit @ git+https://github.com/PyCQA/bandit.git@main\n")
    assert detector.inspect(p3).state == State.CONFIGURED

    # 4. PEP 508 in pyproject dependencies
    p4 = tmp_path / "p4"
    _write(
        p4 / "pyproject.toml",
        '[project]\nname = "p4"\nversion = "0.1.0"\ndependencies = ["bandit >= 1.7"]\n',
    )
    assert detector.inspect(p4).state == State.CONFIGURED

    p5 = tmp_path / "p5"
    _write(
        p5 / "pyproject.toml",
        '[project]\nname = "p5"\nversion = "0.1.0"\n[project.optional-dependencies]\n'
        'dev = ["bandit @ git+https://github.com/PyCQA/bandit.git@main"]\n',
    )
    assert detector.inspect(p5).state == State.CONFIGURED


def test_pep_735_and_build_tool_dependency_groups(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()

    # PEP 735 [dependency-groups]
    p1 = tmp_path / "pep735"
    _write(
        p1 / "pyproject.toml",
        '[project]\nname = "p1"\n\n[dependency-groups]\ndev = ["bandit >= 1.7"]\n',
    )
    assert detector.inspect(p1).state == State.CONFIGURED

    # PEP 735 with include-group dict item
    p1b = tmp_path / "pep735_include"
    _write(
        p1b / "pyproject.toml",
        '[project]\nname = "p1b"\n\n[dependency-groups]\ntest = [{include-group = "lint"}, "bandit"]\n',
    )
    assert detector.inspect(p1b).state == State.CONFIGURED

    # [tool.uv] dev-dependencies
    p2 = tmp_path / "uv_dev"
    _write(
        p2 / "pyproject.toml",
        '[project]\nname = "p2"\n\n[tool.uv]\ndev-dependencies = ["bandit"]\n',
    )
    assert detector.inspect(p2).state == State.CONFIGURED

    # [tool.pdm.dev-dependencies]
    p3 = tmp_path / "pdm_dev"
    _write(
        p3 / "pyproject.toml",
        '[project]\nname = "p3"\n\n[tool.pdm.dev-dependencies]\ndev = ["bandit"]\n',
    )
    assert detector.inspect(p3).state == State.CONFIGURED

    # hatch env dependencies
    p4 = tmp_path / "hatch_env"
    _write(
        p4 / "pyproject.toml",
        '[project]\nname = "p4"\n\n[tool.hatch.envs.default]\ndependencies = ["bandit"]\n',
    )
    assert detector.inspect(p4).state == State.CONFIGURED

    # hatch extra-dependencies
    p5 = tmp_path / "hatch_extra"
    _write(
        p5 / "pyproject.toml",
        '[project]\nname = "p5"\n\n[tool.hatch.envs.lint]\nextra-dependencies = ["semgrep"]\n',
    )
    assert detector.inspect(p5).state == State.CONFIGURED


def test_pre_commit_quoted_ids_and_local_hooks(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()

    # - id: bandit (list item)
    p1 = tmp_path / "pc1"
    _write(
        p1 / ".pre-commit-config.yaml",
        "repos:\n  - repo: https://github.com/PyCQA/bandit\n    rev: 1.7.5\n    hooks:\n      - id: bandit\n",
    )
    assert detector.inspect(p1).state == State.CONFIGURED

    # - id: "bandit" (quoted id)
    p2 = tmp_path / "pc2"
    _write(
        p2 / ".pre-commit-config.yaml",
        'repos:\n  - repo: https://github.com/PyCQA/bandit\n    rev: 1.7.5\n    hooks:\n      - id: "bandit"\n',
    )
    assert detector.inspect(p2).state == State.CONFIGURED

    # - id: 'semgrep' (single quoted)
    p3 = tmp_path / "pc3"
    _write(
        p3 / ".pre-commit-config.yaml",
        "repos:\n  - repo: https://github.com/semgrep/semgrep\n    rev: v1.0.0\n    hooks:\n      - id: 'semgrep'\n",
    )
    assert detector.inspect(p3).state == State.CONFIGURED

    # repo: local hook with entry: bandit
    p4 = tmp_path / "pc4"
    _write(
        p4 / ".pre-commit-config.yaml",
        "repos:\n  - repo: local\n    hooks:\n      - id: run-security\n        name: security\n"
        "        entry: bandit -r src\n        language: system\n",
    )
    assert detector.inspect(p4).state == State.CONFIGURED


def test_monorepo_root_level_candidate_files(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    repo = tmp_path / "monorepo"
    _write(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    subproject = repo / "services" / "api"
    _write(subproject / "pyproject.toml", '[project]\nname = "api"\nversion = "0.1.0"\n')

    # 1. Root-level .pre-commit-config.yaml
    _write(
        repo / ".pre-commit-config.yaml",
        "repos:\n  - repo: https://github.com/PyCQA/bandit\n    rev: 1.7.5\n    hooks:\n      - id: bandit\n",
    )
    assert detector.inspect(subproject).state == State.CONFIGURED
    (repo / ".pre-commit-config.yaml").unlink()

    # 2. Root-level requirements-dev.txt
    _write(repo / "requirements-dev.txt", "bandit>=1.7\n")
    assert detector.inspect(subproject).state == State.CONFIGURED
    (repo / "requirements-dev.txt").unlink()

    # 3. Root-level setup.cfg
    _write(repo / "setup.cfg", "[bandit]\nexclude = /tests\n")
    assert detector.inspect(subproject).state == State.CONFIGURED
    (repo / "setup.cfg").unlink()

    # 4. Root-level tox.ini
    _write(repo / "tox.ini", "[testenv]\ndeps = bandit\n")
    assert detector.inspect(subproject).state == State.CONFIGURED


def test_workflow_and_tox_runner_commands(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()

    # uv run bandit in workflow
    p1 = tmp_path / "w_uv"
    _write(p1 / "pyproject.toml", '[project]\nname = "p1"\n')
    _write(
        p1 / ".github" / "workflows" / "ci.yml",
        "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: uv run bandit -r src/\n",
    )
    assert detector.inspect(p1).state == State.CONFIGURED

    # uvx bandit in workflow
    p2 = tmp_path / "w_uvx"
    _write(p2 / "pyproject.toml", '[project]\nname = "p2"\n')
    _write(
        p2 / ".github" / "workflows" / "ci.yml",
        "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: uvx bandit -r src/\n",
    )
    assert detector.inspect(p2).state == State.CONFIGURED

    # python -m bandit in workflow
    p3 = tmp_path / "w_pym"
    _write(p3 / "pyproject.toml", '[project]\nname = "p3"\n')
    _write(
        p3 / ".github" / "workflows" / "ci.yml",
        "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: python -m bandit -r src/\n",
    )
    assert detector.inspect(p3).state == State.CONFIGURED

    # poetry run bandit in workflow
    p4 = tmp_path / "w_poetry"
    _write(p4 / "pyproject.toml", '[project]\nname = "p4"\n')
    _write(
        p4 / ".github" / "workflows" / "ci.yml",
        "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: poetry run bandit -r src/\n",
    )
    assert detector.inspect(p4).state == State.CONFIGURED

    # pipx run bandit in workflow
    p5 = tmp_path / "w_pipx"
    _write(p5 / "pyproject.toml", '[project]\nname = "p5"\n')
    _write(
        p5 / ".github" / "workflows" / "ci.yml",
        "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: pipx run bandit -r src/\n",
    )
    assert detector.inspect(p5).state == State.CONFIGURED

    # commands in tox.ini using uv run bandit
    p6 = tmp_path / "tox_runner"
    _write(p6 / "tox.ini", "[testenv:lint]\ncommands = uv run bandit -r src\n")
    assert detector.inspect(p6).state == State.CONFIGURED


def test_workflow_bandit_action(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "w_bandit_action"
    _write(p / "pyproject.toml", '[project]\nname = "p"\n')
    _write(
        p / ".github" / "workflows" / "ci.yml",
        "name: CI\non: [push]\njobs:\n  security:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: PyCQA/bandit-action@v1\n",
    )
    assert detector.inspect(p).state == State.CONFIGURED


def test_ruff_toml_does_not_mask_other_analyzers(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "ruff_with_bandit"
    # ruff.toml with extend makes ruff INDETERMINATE
    _write(p / "ruff.toml", 'extend = "base.toml"\n')
    # but pyproject has bandit in dependencies -> CONFIGURED
    _write(
        p / "pyproject.toml",
        '[project]\nname = "app"\nversion = "0.1.0"\ndependencies = ["bandit"]\n',
    )
    assert detector.inspect(p).state == State.CONFIGURED


def test_read_bounded_ctrl_z_binary_mode(tmp_path: Path) -> None:
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "ctrl_z"
    # `# \x1a\nbandit\n` in requirements.txt
    (p / "requirements.txt").parent.mkdir(parents=True, exist_ok=True)
    (p / "requirements.txt").write_bytes(b"# \x1a\nbandit\n")
    assert detector.inspect(p).state == State.CONFIGURED


def test_split_shell_commands_handles_logical_operators() -> None:
    result = _split_shell_commands("a && b || c")
    assert result == ["a", "b", "c"]


def test_project_root_without_pyproject_requirements_bandit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An app with only requirements.txt containing bandit -> CONFIGURED; without bandit -> NOT_CONFIGURED."""
    import sys
    from types import ModuleType

    from sharpit.engine.collectors.security.report import build_inputs, scan_evaluation
    from sharpit.engine.spi import SecurityFacts, SecurityModel
    from sharpit.settings import SharpitSettings

    proj = tmp_path / "app_req_bandit"
    pkg = proj / "myapp"
    pkg.mkdir(parents=True)
    _write(pkg / "__init__.py", "")
    _write(proj / "requirements.txt", "bandit>=1.7\n")

    mod = ModuleType("myapp")
    mod.__file__ = str(pkg / "__init__.py")
    mod.__path__ = [str(pkg)]
    monkeypatch.setitem(sys.modules, "myapp", mod)

    settings = SharpitSettings(app_package="myapp")
    inputs = build_inputs(
        SecurityModel(True, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        settings,
    )
    evaluation = scan_evaluation(inputs)
    assert RULE_ID in evaluation.evaluated
    assert not any(f.rule_id == RULE_ID for f in evaluation.findings)


def test_project_root_without_pyproject_requirements_no_bandit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An app with only requirements.txt without bandit -> NOT_CONFIGURED (finding emitted)."""
    import sys
    from types import ModuleType

    from sharpit.engine.collectors.security.report import build_inputs, scan_evaluation
    from sharpit.engine.spi import SecurityFacts, SecurityModel
    from sharpit.settings import SharpitSettings

    proj = tmp_path / "app_req_no_bandit"
    pkg = proj / "myapp2"
    pkg.mkdir(parents=True)
    _write(pkg / "__init__.py", "")
    _write(proj / "requirements.txt", "fastapi>=0.100\n")

    mod = ModuleType("myapp2")
    mod.__file__ = str(pkg / "__init__.py")
    mod.__path__ = [str(pkg)]
    monkeypatch.setitem(sys.modules, "myapp2", mod)

    settings = SharpitSettings(app_package="myapp2")
    inputs = build_inputs(
        SecurityModel(True, (), (), (), ()),
        SecurityFacts(False, None, (), (), ()),
        None,
        settings,
    )
    evaluation = scan_evaluation(inputs)
    assert RULE_ID in evaluation.evaluated
    assert any(f.rule_id == RULE_ID for f in evaluation.findings)


def test_fail_open_pre_commit_exclude_is_not_hook(tmp_path: Path) -> None:
    """exclude: key containing semgrep/semgrep is not counted as a hook declaration."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "precommit_exclude"
    _write(p / "pyproject.toml", '[project]\nname = "p"\n')
    _write(
        p / ".pre-commit-config.yaml",
        "repos:\n  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v4.4.0\n    hooks:\n      - id: trailing-whitespace\n"
        "        exclude: ^tests/semgrep/semgrep_rules/\n",
    )
    assert detector.inspect(p).state == State.NOT_CONFIGURED


def test_ruff_toml_lint_select_s(tmp_path: Path) -> None:
    """ruff.toml with [lint] select=['S'] -> CONFIGURED."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "ruff_lint_s"
    _write(p / "pyproject.toml", '[project]\nname = "p"\n')
    _write(p / "ruff.toml", '[lint]\nselect = ["S"]\n')
    assert detector.inspect(p).state == State.CONFIGURED


def test_ruff_top_level_s_overridden_by_lint_select_e(tmp_path: Path) -> None:
    """top-level S overridden by lint.select=['E'] -> NOT_CONFIGURED."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "ruff_override"
    _write(p / "pyproject.toml", '[project]\nname = "p"\n')
    _write(p / "ruff.toml", 'select = ["S"]\n\n[lint]\nselect = ["E"]\n')
    assert detector.inspect(p).state == State.NOT_CONFIGURED


def test_bom_requirements_with_bandit(tmp_path: Path) -> None:
    """requirements.txt with UTF-8 BOM containing bandit -> CONFIGURED."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "bom_req"
    p.mkdir(parents=True, exist_ok=True)
    (p / "requirements.txt").write_bytes(b"\xef\xbb\xbfbandit>=1.7\n")
    assert detector.inspect(p).state == State.CONFIGURED


def test_latin1_sonar_project_properties(tmp_path: Path) -> None:
    """sonar-project.properties with Latin-1 bytes decoded leniently -> CONFIGURED."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "latin1_sonar"
    p.mkdir(parents=True, exist_ok=True)
    _write(p / "pyproject.toml", '[project]\nname = "p"\n')
    (p / "sonar-project.properties").write_bytes(b"sonar.projectKey=proj\n# non-utf8: \xe9\n")
    assert detector.inspect(p).state == State.CONFIGURED


@pytest.mark.parametrize(
    "cmd",
    [
        "uv run --python 3.12 bandit",
        "uv run --group dev bandit",
        "uv run --with X bandit",
        "uv run --extra Y bandit",
    ],
)
def test_runner_command_options_skipped(tmp_path: Path, cmd: str) -> None:
    """Runner options and their values are skipped so target command is identified."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / f"cmd_{cmd.replace(' ', '_').replace('-', '_')}"
    _write(p / "pyproject.toml", '[project]\nname = "p"\n')
    _write(
        p / ".github" / "workflows" / "ci.yml",
        f"name: CI\non: [push]\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: {cmd}\n",
    )
    assert detector.inspect(p).state == State.CONFIGURED


def test_tox_envpython_bandit(tmp_path: Path) -> None:
    """tox.ini with commands = {envpython} -m bandit -> CONFIGURED."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "tox_envpython"
    _write(
        p / "tox.ini",
        "[testenv]\ncommands = {envpython} -m bandit -r myapp\n",
    )
    assert detector.inspect(p).state == State.CONFIGURED


def test_report_indeterminate_sets_partial_status_and_limitations(tmp_path: Path) -> None:
    """When static analysis is INDETERMINATE, scan evaluation sets PARTIAL and records the limitation."""
    project = tmp_path / "broken_project"
    _write(project / "pyproject.toml", "[[broken toml syntax\n")

    model = SecurityModel(True, (), (), (), ())
    inputs = build_inputs(
        model,
        SecurityFacts(False, None, (), (), ()),
        None,
        SharpitSettings(app_package=project.name),
    )
    inputs = inputs.__class__(
        inputs.model, inputs.facts, inputs.source, inputs.view, inputs.limitations, project_root=project
    )
    service = SecurityService(
        lambda: inputs,
        DismissalStore(tmp_path / "dismissals"),
        Masker(Exposure.MASKED, True),
        SingleFlight(),
        max_retained=1000,
    )

    report = service.scan()
    assert report["scan"]["status"] == "PARTIAL"
    assert LIMITATION_TEXT in report["evidence"]["limitations"]

    evaluation = scan_evaluation(inputs)
    assert evaluation.status == "PARTIAL"
    assert LIMITATION_TEXT in evaluation.evidence["limitations"]
    assert RULE_ID not in evaluation.evaluated


def test_pyproject_poetry_dict_and_group_dependencies(tmp_path: Path) -> None:
    """Poetry table-format dependencies and group dependencies are recognized as CONFIGURED."""
    detector = StaticSecurityAnalysisDetector()

    # 1. tool.poetry.dependencies as dict
    p1 = tmp_path / "poetry_dict"
    _write(p1 / "pyproject.toml", '[tool.poetry.dependencies]\nbandit = "^1.7"\n')
    assert detector.inspect(p1).state == State.CONFIGURED

    # 2. tool.poetry.group.<name>.dependencies as dict
    p2 = tmp_path / "poetry_group"
    _write(p2 / "pyproject.toml", '[tool.poetry.group.dev.dependencies]\nbandit = "^1.7"\n')
    assert detector.inspect(p2).state == State.CONFIGURED


def test_setup_cfg_options_install_and_extras_require(tmp_path: Path) -> None:
    """setup.cfg options.install_requires and options.extras_require are recognized as CONFIGURED."""
    detector = StaticSecurityAnalysisDetector()

    # 1. options.install_requires
    p1 = tmp_path / "setup_install"
    _write(p1 / "setup.cfg", "[options]\ninstall_requires =\n    bandit>=1.7\n")
    assert detector.inspect(p1).state == State.CONFIGURED

    # 2. options.extras_require
    p2 = tmp_path / "setup_extras"
    _write(p2 / "setup.cfg", "[options.extras_require]\nsec =\n    bandit>=1.7\n")
    assert detector.inspect(p2).state == State.CONFIGURED


def test_ruff_lint_extend_is_indeterminate(tmp_path: Path) -> None:
    """tool.ruff.lint.extend causes inspection to return INDETERMINATE."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "ruff_lint_extend"
    _write(p / "pyproject.toml", '[tool.ruff.lint]\nextend = "base.toml"\n')
    assert detector.inspect(p).state == State.INDETERMINATE


def test_build_files_directories_and_read_errors(tmp_path: Path) -> None:
    """Non-regular files or read errors for build configs result in INDETERMINATE."""
    detector = StaticSecurityAnalysisDetector()

    # 1. setup.py as the only build file -> NOT_CONFIGURED
    p_setup = tmp_path / "only_setup_py"
    _write(p_setup / "setup.py", "from setuptools import setup\nsetup()\n")
    assert detector.inspect(p_setup).state == State.NOT_CONFIGURED

    # 2. setup.cfg is a directory
    p_cfg_dir = tmp_path / "cfg_dir"
    _write(p_cfg_dir / "pyproject.toml", '[project]\nname = "test"\n')
    (p_cfg_dir / "setup.cfg").mkdir(parents=True)
    assert detector.inspect(p_cfg_dir).state == State.INDETERMINATE

    # 3. tox.ini is a directory
    p_tox_dir = tmp_path / "tox_dir"
    _write(p_tox_dir / "pyproject.toml", '[project]\nname = "test"\n')
    (p_tox_dir / "tox.ini").mkdir(parents=True)
    assert detector.inspect(p_tox_dir).state == State.INDETERMINATE

    # 4. .pre-commit-config.yaml is a directory
    p_precommit_dir = tmp_path / "precommit_dir"
    _write(p_precommit_dir / "pyproject.toml", '[project]\nname = "test"\n')
    (p_precommit_dir / ".pre-commit-config.yaml").mkdir(parents=True)
    assert detector.inspect(p_precommit_dir).state == State.INDETERMINATE

    # 5. requirements.txt is a directory
    p_req_dir = tmp_path / "req_dir"
    _write(p_req_dir / "pyproject.toml", '[project]\nname = "test"\n')
    (p_req_dir / "requirements.txt").mkdir(parents=True)
    assert detector.inspect(p_req_dir).state == State.INDETERMINATE

    # 6. sonar-project.properties is a directory
    p_sonar_dir = tmp_path / "sonar_dir"
    _write(p_sonar_dir / "pyproject.toml", '[project]\nname = "test"\n')
    (p_sonar_dir / "sonar-project.properties").mkdir(parents=True)
    assert detector.inspect(p_sonar_dir).state == State.INDETERMINATE

    # 7. .semgrep.yml is a directory
    p_semgrep_dir = tmp_path / "semgrep_dir"
    _write(p_semgrep_dir / "pyproject.toml", '[project]\nname = "test"\n')
    (p_semgrep_dir / ".semgrep.yml").mkdir(parents=True)
    assert detector.inspect(p_semgrep_dir).state == State.INDETERMINATE

    # 8. ruff.toml is a directory
    p_ruff_dir = tmp_path / "ruff_dir"
    _write(p_ruff_dir / "pyproject.toml", '[project]\nname = "test"\n')
    (p_ruff_dir / "ruff.toml").mkdir(parents=True)
    assert detector.inspect(p_ruff_dir).state == State.INDETERMINATE

    # 9. ruff.toml has invalid TOML syntax
    p_ruff_bad = tmp_path / "ruff_bad"
    _write(p_ruff_bad / "pyproject.toml", '[project]\nname = "test"\n')
    _write(p_ruff_bad / "ruff.toml", "[[broken toml\n")
    assert detector.inspect(p_ruff_bad).state == State.INDETERMINATE

    # 10. .pre-commit-config.yaml has invalid UTF-8 bytes
    p_precommit_bad = tmp_path / "precommit_bad"
    _write(p_precommit_bad / "pyproject.toml", '[project]\nname = "test"\n')
    (p_precommit_bad / ".pre-commit-config.yaml").write_bytes(b"\xff\xfe\x00\x00")
    assert detector.inspect(p_precommit_bad).state == State.INDETERMINATE

    # 11. .semgrep.yml has invalid UTF-8 bytes
    p_semgrep_bad = tmp_path / "semgrep_bad"
    _write(p_semgrep_bad / "pyproject.toml", '[project]\nname = "test"\n')
    (p_semgrep_bad / ".semgrep.yml").write_bytes(b"\xff\xfe\x00\x00")
    assert detector.inspect(p_semgrep_bad).state == State.INDETERMINATE


def test_workflow_command_parsing_variants(tmp_path: Path) -> None:
    """Workflow analyzer commands in folded, continuation, compound or quoted forms are identified."""
    detector = StaticSecurityAnalysisDetector()

    def make_wf_proj(name: str, step_yaml: str) -> Path:
        p = tmp_path / name
        _write(p / "pyproject.toml", '[project]\nname = "test"\n')
        _write(
            p / ".github" / "workflows" / "ci.yml",
            f"name: CI\non: [push]\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n{step_yaml}\n",
        )
        return p

    # 1. Folded run block (run: >)
    p1 = make_wf_proj("wf_folded", "      - run: >\n          bandit\n          -r .\n")
    assert detector.inspect(p1).state == State.CONFIGURED

    # 2. Line continuation with backslash in multiline run block
    p2 = make_wf_proj("wf_continuation", "      - run: |\n          bandit \\\n            -r .\n")
    assert detector.inspect(p2).state == State.CONFIGURED

    # 3. Multiline run block with empty lines between statements
    p3 = make_wf_proj("wf_empty_lines", "      - run: |\n\n          echo starting\n\n          bandit -r .\n")
    assert detector.inspect(p3).state == State.CONFIGURED

    # 4. Compound operators || and &&
    p4 = make_wf_proj("wf_compound", "      - run: false || bandit -r .\n")
    assert detector.inspect(p4).state == State.CONFIGURED

    # 5. Quoted run command with escaped quotes
    p5 = make_wf_proj("wf_quoted_escape", '      - run: "bandit -r \\"dir with spaces\\""\n')
    assert detector.inspect(p5).state == State.CONFIGURED

    # 6. Single-quoted run command
    p6 = make_wf_proj("wf_single_quote", "      - run: 'bandit -r ''dir with spaces'''\n")
    assert detector.inspect(p6).state == State.CONFIGURED

    # 7. Runner options: -- and -v
    p7 = make_wf_proj("wf_runner_opts", "      - run: uv run -- bandit -r .\n")
    assert detector.inspect(p7).state == State.CONFIGURED

    p8 = make_wf_proj("wf_runner_flag", "      - run: uv run -v bandit -r .\n")
    assert detector.inspect(p8).state == State.CONFIGURED

    # 8. Semgrep variants: --config=..., -f..., scan, ci
    for sub, cmd in [
        ("semgrep_cfg_eq", "semgrep --config=p/ci"),
        ("semgrep_cfg_sp", "semgrep --config p/ci"),
        ("semgrep_f_sp", "semgrep -f p/ci"),
        ("semgrep_f_join", "semgrep -frule.yml"),
        ("semgrep_scan", "semgrep scan"),
        ("semgrep_ci", "semgrep ci"),
    ]:
        p = make_wf_proj(f"wf_{sub}", f"      - run: {cmd}\n")
        assert detector.inspect(p).state == State.CONFIGURED, f"{sub} expected CONFIGURED"

    # 9. CodeQL variants: database, analyze
    p_codeql_db = make_wf_proj("wf_codeql_db", "      - run: codeql database create ./db --language=python\n")
    assert detector.inspect(p_codeql_db).state == State.CONFIGURED

    p_codeql_an = make_wf_proj("wf_codeql_an", "      - run: codeql analyze ./db\n")
    assert detector.inspect(p_codeql_an).state == State.CONFIGURED

    # 10. Sonar-scanner
    p_sonar = make_wf_proj("wf_sonar", "      - run: sonar-scanner\n")
    assert detector.inspect(p_sonar).state == State.CONFIGURED

    # 11. Workflow directory is a file -> INDETERMINATE
    p_wf_file = tmp_path / "wf_dir_is_file"
    _write(p_wf_file / "pyproject.toml", '[project]\nname = "test"\n')
    _write(p_wf_file / ".github" / "workflows", "not a directory\n")
    assert detector.inspect(p_wf_file).state == State.INDETERMINATE

    # 12. Non-yaml file in workflow directory is skipped
    p_non_yaml = make_wf_proj("wf_non_yaml", "      - run: bandit -r .\n")
    _write(p_non_yaml / ".github" / "workflows" / "notes.txt", "some notes\n")
    assert detector.inspect(p_non_yaml).state == State.CONFIGURED

    # 13. Workflow file is a directory -> INDETERMINATE
    p_wf_sub_dir = tmp_path / "wf_file_is_dir"
    _write(p_wf_sub_dir / "pyproject.toml", '[project]\nname = "test"\n')
    (p_wf_sub_dir / ".github" / "workflows" / "sub.yml").mkdir(parents=True)
    assert detector.inspect(p_wf_sub_dir).state == State.INDETERMINATE

    # 14. Workflow file has invalid UTF-8 bytes -> INDETERMINATE
    p_wf_bad_utf8 = tmp_path / "wf_bad_utf8"
    _write(p_wf_bad_utf8 / "pyproject.toml", '[project]\nname = "test"\n')
    bad_wf = p_wf_bad_utf8 / ".github" / "workflows" / "bad.yml"
    bad_wf.parent.mkdir(parents=True, exist_ok=True)
    bad_wf.write_bytes(b"\xff\xfe\x00\x00")
    assert detector.inspect(p_wf_bad_utf8).state == State.INDETERMINATE

    # 15. Empty run command or runner wrappers only
    p_empty_run = make_wf_proj("wf_empty_run", '      - run: ""\n')
    assert detector.inspect(p_empty_run).state == State.NOT_CONFIGURED

    p_wrapper_only = make_wf_proj("wf_wrapper_only", "      - run: sudo\n")
    assert detector.inspect(p_wrapper_only).state == State.NOT_CONFIGURED

    p_py_m_only = make_wf_proj("wf_py_m_only", "      - run: python -m\n")
    assert detector.inspect(p_py_m_only).state == State.NOT_CONFIGURED


def test_detector_inspect_root_types_and_candidate_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Inspecting non-directories, exceptions, and parent candidates handles all edge conditions."""
    detector = StaticSecurityAnalysisDetector()

    # 1. Root is a file -> NOT_APPLICABLE
    file_root = tmp_path / "regular_file.txt"
    _write(file_root, "not a dir")
    assert detector.inspect(file_root).state == State.NOT_APPLICABLE

    # 2. Unexpected exception in inspect -> INDETERMINATE
    p_exc = tmp_path / "exc_proj"
    _write(p_exc / "pyproject.toml", '[project]\nname = "test"\n')

    def failing_build_files(self: Any, root: Path) -> Any:
        raise RuntimeError("Unexpected inspection failure")

    monkeypatch.setattr(StaticSecurityAnalysisDetector, "_build_files", failing_build_files)
    assert detector.inspect(p_exc).state == State.INDETERMINATE
    monkeypatch.undo()

    # 3. Candidate parent root with ruff.toml selecting S
    repo = tmp_path / "parent_repo_ruff"
    _write(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    _write(repo / "ruff.toml", '[lint]\nselect = ["S"]\n')
    subproj = repo / "services" / "app"
    _write(subproj / "pyproject.toml", '[project]\nname = "sub"\n')
    assert detector.inspect(subproj).state == State.CONFIGURED

    # 4. Candidate parent root with unreadable pyproject (directory named pyproject.toml) -> INDETERMINATE
    repo_bad = tmp_path / "parent_repo_bad_pyproject"
    _write(repo_bad / ".git" / "HEAD", "ref: refs/heads/main\n")
    (repo_bad / "pyproject.toml").mkdir(parents=True)
    subproj_bad = repo_bad / "services" / "app"
    _write(subproj_bad / "pyproject.toml", '[project]\nname = "sub"\n')
    assert detector.inspect(subproj_bad).state == State.INDETERMINATE

    # 5. Candidate parent root where requirements scandir raises OSError -> INDETERMINATE
    repo_scandir = tmp_path / "parent_repo_scandir"
    _write(repo_scandir / ".git" / "HEAD", "ref: refs/heads/main\n")
    subproj_scandir = repo_scandir / "services" / "app"
    _write(subproj_scandir / "pyproject.toml", '[project]\nname = "sub"\n')

    real_scandir = os.scandir

    def failing_parent_scandir(path: Any) -> Any:
        if str(path) == str(repo_scandir):
            raise OSError("Parent scandir failed")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", failing_parent_scandir)
    assert detector.inspect(subproj_scandir).state == State.INDETERMINATE
    monkeypatch.undo()

    # 6. Workflow directory scandir raises OSError -> INDETERMINATE
    p_wf_err = tmp_path / "wf_scandir_err"
    _write(p_wf_err / "pyproject.toml", '[project]\nname = "test"\n')
    wf_dir = p_wf_err / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)

    def failing_wf_scandir(path: Any) -> Any:
        if str(path) == str(wf_dir):
            raise OSError("Workflow scandir error")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", failing_wf_scandir)
    assert detector.inspect(p_wf_err).state == State.INDETERMINATE
    monkeypatch.undo()

    # 7. Candidate exists() raises OSError in _build_files
    p_exists_err = tmp_path / "exists_err"
    p_exists_err.mkdir(parents=True)
    real_exists = Path.exists

    def failing_exists(self: Path) -> bool:
        if self.name == "pyproject.toml":
            raise OSError("Simulated exists failure")
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", failing_exists)
    # No build files found -> NOT_APPLICABLE
    assert detector.inspect(p_exists_err).state == State.NOT_APPLICABLE


def test_symlink_config_files_indeterminate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A build or config file detected as a symlink results in INDETERMINATE."""
    from sharpit.engine.collectors.security import static_analysis

    detector = StaticSecurityAnalysisDetector()

    for name in (
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
        ".pre-commit-config.yaml",
        "requirements.txt",
        "sonar-project.properties",
        ".semgrep.yml",
        "ruff.toml",
    ):
        p = tmp_path / f"sym_{name.replace('.', '_')}"
        _write(p / "pyproject.toml", '[project]\nname = "test"\n')
        target = _write(p / name, "content\n") if name != "pyproject.toml" else p / name

        real_contains = static_analysis.contains_symbolic_link

        def fake_contains(trusted: Path, cand: Path, tgt: Path = target, rc: Any = real_contains) -> bool:
            if str(cand) == str(tgt):
                return True
            return rc(trusted, cand)

        monkeypatch.setattr(static_analysis, "contains_symbolic_link", fake_contains)
        assert detector.inspect(p).state == State.INDETERMINATE, f"{name} expected INDETERMINATE"
        monkeypatch.undo()


def test_pyproject_toml_is_a_directory(tmp_path: Path) -> None:
    """When pyproject.toml is a directory rather than a file, inspection is INDETERMINATE."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "pyproject_is_dir"
    (p / "pyproject.toml").mkdir(parents=True)
    _write(p / "setup.cfg", "[metadata]\nname = test\n")
    assert detector.inspect(p).state == State.INDETERMINATE


def test_workflow_command_parsing_shell_escapes_and_semicolons(tmp_path: Path) -> None:
    """Workflow parsing handles semicolons, escaped quotes in double quotes, and multi-step dedents."""
    detector = StaticSecurityAnalysisDetector()

    p = tmp_path / "wf_multi_and_escape"
    _write(p / "pyproject.toml", '[project]\nname = "test"\n')
    _write(
        p / ".github" / "workflows" / "ci.yml",
        """name: CI
on: [push]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: echo hello; bandit -r "dir\\"escaped"
      - run: a
      - run: |
          echo multi
          bandit -r .
      - run: echo done
""",
    )
    assert detector.inspect(p).state == State.CONFIGURED


def test_repository_root_deep_hierarchy_filesystem_root_stop(tmp_path: Path) -> None:
    """_repository_root stops when climbing past filesystem root or max depth."""
    deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "f"
    deep.mkdir(parents=True, exist_ok=True)
    root = _repository_root(deep)
    assert root == deep


def test_build_files_scandir_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When os.scandir in _build_files raises OSError, existing known build files are still returned."""
    detector = StaticSecurityAnalysisDetector()
    p = tmp_path / "scandir_err_proj"
    _write(p / "pyproject.toml", '[project]\nname = "test"\n')

    real_scandir = os.scandir

    def failing_scandir(path: Any) -> Any:
        if str(path) == str(p):
            raise OSError("Scandir failed")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", failing_scandir)
    files = detector._build_files(p)
    assert len(files) == 1
    assert files[0].name == "pyproject.toml"


@pytest.mark.parametrize("local_config", ["pyproject", "ruff.toml"])
def test_subproject_ruff_config_precedes_repository_config(tmp_path: Path, local_config: str) -> None:
    detector = StaticSecurityAnalysisDetector()
    repo = tmp_path / "repo"
    _write(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    project = repo / "svc"
    local_ruff = '[tool.ruff.lint]\nselect = ["S"]\n' if local_config == "pyproject" else ""
    _write(project / "pyproject.toml", f'[project]\nname = "svc"\n{local_ruff}')
    if local_config == "ruff.toml":
        _write(project / "ruff.toml", '[lint]\nselect = ["S"]\n')
    _write(repo / "ruff.toml", '[lint]\nselect = ["E"]\n')
    assert detector.inspect(project).state == State.CONFIGURED


@pytest.mark.parametrize("runner", ["uv run", "uvx"])
def test_runner_isolated_flag_is_boolean(tmp_path: Path, runner: str) -> None:
    detector = StaticSecurityAnalysisDetector()
    _write(tmp_path / "pyproject.toml", '[project]\nname = "runner"\n')
    _write(
        tmp_path / ".github" / "workflows" / "ci.yml",
        f"name: CI\njobs:\n  test:\n    steps:\n      - run: {runner} --isolated bandit -r src\n",
    )
    assert detector.inspect(tmp_path).state == State.CONFIGURED
