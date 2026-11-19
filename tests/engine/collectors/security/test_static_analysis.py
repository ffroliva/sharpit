"""Tests for SEC-STATIC-001 detector (port of BootUI 2.4.0 StaticSecurityAnalysisDetectorTests)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sharpit.engine.collectors.security.static_analysis import (
    LIMITATION_TEXT,
    RULE_ID,
    State,
    StaticSecurityAnalysisDetector,
    StaticSecurityAnalysisRule,
    _split_shell_commands,
    strip_yaml_comments,
)


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
    _write(tmp2 / "ruff.toml", '[lint]\nselect = ["S"]\n')
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
    # ruff.toml makes ruff INDETERMINATE
    _write(p / "ruff.toml", '[lint]\nselect = ["ALL"]\n')
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
    assert StaticSecurityAnalysisRule.RULE_ID in evaluation.evaluated
    assert not any(f.rule_id == StaticSecurityAnalysisRule.RULE_ID for f in evaluation.findings)


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
    assert StaticSecurityAnalysisRule.RULE_ID in evaluation.evaluated
    assert any(f.rule_id == StaticSecurityAnalysisRule.RULE_ID for f in evaluation.findings)


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

