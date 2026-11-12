from __future__ import annotations

import json
from pathlib import Path

import pytest

from sharpit.engine.collectors.github.dashboard import GitHubDashboard
from sharpit.engine.collectors.github.detector import Repository, detect_repository
from sharpit.settings import SharpitSettings

ALLOWED = frozenset({"api.github.com"})


def _repo(root: Path, remote: str, branch: str = "main") -> Path:
    git = root / ".git"
    git.mkdir(parents=True, exist_ok=True)
    (git / "config").write_text(
        f'[remote "origin"]\n url = {remote}\n[branch "{branch}"]\n merge = refs/heads/{branch}\n'
    )
    (git / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
    return root


def test_detector_https_origin(tmp_path: Path) -> None:
    # ported: GitHubRepositoryDetectorTests.detectsHttpsGithubOrigin
    result = detect_repository(_repo(tmp_path, "https://github.com/acme/app.git"), ALLOWED)
    assert isinstance(result, Repository)
    assert result.full_name == "acme/app"
    assert result.api_base_uri == "https://api.github.com/"


def test_detector_scp_like_origin(tmp_path: Path) -> None:
    # ported: GitHubRepositoryDetectorTests.detectsScpLikeGithubOrigin
    result = detect_repository(_repo(tmp_path, "git@github.com:acme/app.git"), ALLOWED)
    assert isinstance(result, Repository)
    assert result.html_url == "https://github.com/acme/app"


def test_detector_configured_enterprise_host(tmp_path: Path) -> None:
    # ported: GitHubRepositoryDetectorTests.detectsConfiguredEnterpriseHost
    result = detect_repository(_repo(tmp_path, "git@ghe.example.com:team/app.git"), frozenset({"ghe.example.com"}))
    assert isinstance(result, Repository)
    assert result.api_base_uri == "https://ghe.example.com/api/v3/"


def test_detector_rejects_non_github_origin(tmp_path: Path) -> None:
    # ported: GitHubRepositoryDetectorTests.rejectsNonGithubOrigin
    result = detect_repository(_repo(tmp_path, "https://gitlab.com/acme/app.git"), ALLOWED)
    assert result == "Origin remote host is not github.com or an allowed GitHub Enterprise host"


def test_detector_reads_worktree_commondir(tmp_path: Path) -> None:
    common = tmp_path / "common"
    (common / "refs" / "heads").mkdir(parents=True)
    (common / "config").write_text('[remote "origin"]\n url = https://github.com/acme/worktree.git\n')
    (common / "HEAD").write_text("ref: refs/heads/main\n")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    gitdir = common / "worktrees" / "linked"
    gitdir.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n")
    (gitdir / "commondir").write_text("../..\n")
    (gitdir / "HEAD").write_text("ref: refs/heads/feature\n")
    result = detect_repository(worktree, ALLOWED)
    assert isinstance(result, Repository)
    assert result.full_name == "acme/worktree"
    assert result.local_branch == "feature"


def test_detector_walks_up_like_bootui(tmp_path: Path) -> None:
    root = _repo(tmp_path / "project", "https://github.com/acme/app.git")
    child = root / "src" / "pkg"
    child.mkdir(parents=True)
    result = detect_repository(child, ALLOWED)
    assert isinstance(result, Repository)
    assert result.full_name == "acme/app"


def test_dashboard_only_reads_local_repository_state(tmp_path: Path) -> None:
    # ported: GitHubDashboardServiceTests.dashboardOnlyReadsLocalRepositoryState
    root = _repo(tmp_path, "https://github.com/acme/app.git")

    class NoNetwork:
        def refresh(self, _repo: Repository) -> dict[str, object]:
            raise AssertionError("dashboard called GitHub client")

    report = GitHubDashboard(lambda: root, SharpitSettings(), NoNetwork()).dashboard()
    assert report["status"] == "READY"
    assert report["connected"] is False
    assert report["repository"]["fullName"] == "acme/app"
    assert report["credential"]["source"] == "not connected"
    assert report["copilotUsage"]["unavailableReason"] == "Connect to GitHub to probe Copilot usage reports"


def test_dashboard_reports_unavailable_outside_github_repository(tmp_path: Path) -> None:
    # ported: GitHubDashboardServiceTests.reportsUnavailableOutsideGitHubRepository
    report = GitHubDashboard(lambda: tmp_path, SharpitSettings()).dashboard()
    assert report["available"] is False
    assert report["status"] == "UNAVAILABLE"
    assert report["unavailableReason"] == "No local git repository was detected"


def test_github_golden_shape_23(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from examples.fastapi_sample.app import create_app
    from fastapi.testclient import TestClient

    monkeypatch.chdir(tmp_path)
    response = TestClient(create_app(show_banner=False), base_url="http://localhost", client=("127.0.0.1", 50000)).get(
        "/sharpit/api/github"
    )
    golden = Path(__file__).parents[3] / "fixtures/bootui/2.3.0/github/captured.json"
    assert response.status_code == 200
    expected = json.loads(golden.read_text())
    assert set(response.json()) == set(expected)
    assert response.json() == expected


def test_github_refresh_is_not_a_tool() -> None:
    from sharpit.engine.panels04 import tool_definitions

    tools, commands = tool_definitions()
    assert "get_github_dashboard" in {tool.name for tool in tools}
    assert "github" in commands.values()
    assert "github_refresh" not in {tool.name for tool in tools}
    assert "github_refresh" not in commands


def test_detector_api_host_origin_gets_enterprise_api_base(tmp_path: Path) -> None:
    # BootUI apiBaseUri (GitHubRepositoryDetector.java:242-248): only github.com and ssh.github.com use api.github.com/
    result = detect_repository(_repo(tmp_path, "https://api.github.com/o/r"), ALLOWED)
    assert isinstance(result, Repository)
    assert result.api_base_uri == "https://api.github.com/api/v3/"


def test_detector_ssh_github_host_links_to_github_com(tmp_path: Path) -> None:
    # BootUI htmlHost (GitHubRepositoryDetector.java:250-253)
    result = detect_repository(_repo(tmp_path, "ssh://git@ssh.github.com:443/o/r.git"), ALLOWED)
    assert isinstance(result, Repository)
    assert result.html_url == "https://github.com/o/r"


def test_detector_reports_missing_origin(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text('[remote "upstream"]\n url = https://github.com/o/r.git\n')
    assert detect_repository(tmp_path, ALLOWED) == "No GitHub origin remote was detected"


def test_detector_skips_oversized_config(tmp_path: Path) -> None:
    root = _repo(tmp_path, "https://github.com/o/r.git")
    with (root / ".git" / "config").open("a") as config:
        config.write("# " + "x" * (2 * 1024 * 1024) + "\n")
    assert detect_repository(root, ALLOWED) == "No GitHub origin remote was detected"


def test_detector_skips_oversized_head(tmp_path: Path) -> None:
    root = _repo(tmp_path, "https://github.com/o/r.git")
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main" + " " * (2 * 1024 * 1024) + "\n")
    result = detect_repository(root, ALLOWED)
    assert isinstance(result, Repository)
    assert result.local_branch is None


def _detect_or_error(start: Path) -> object:
    """The detector's answer, or the exception it let escape (a 500 on the GET route)."""
    try:
        return detect_repository(start, ALLOWED)
    except (OSError, RuntimeError) as exc:
        return repr(exc)


def test_detector_degrades_when_start_cannot_resolve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def loop(self: Path, strict: bool = False) -> Path:
        raise RuntimeError(f"Symlink loop from {self!r}")

    root = _repo(tmp_path, "https://github.com/o/r.git")
    monkeypatch.setattr(Path, "resolve", loop)
    assert _detect_or_error(root) == "No local git repository was detected"


def test_detector_degrades_when_gitdir_pointer_cannot_resolve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {tmp_path / 'loop'}\n")
    original = Path.resolve

    def resolve(self: Path, strict: bool = False) -> Path:
        if self.name == "loop":
            raise OSError("Too many levels of symbolic links")
        return original(self, strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    assert _detect_or_error(worktree) == "No local git repository was detected"


def test_github_module_tools_are_exactly_the_dashboard() -> None:
    from sharpit.engine.tools04 import github

    assert {tool.name for tool in github.TOOLS} == {"get_github_dashboard"}
