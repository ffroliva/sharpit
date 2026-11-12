"""``GitHubDashboard.refresh`` (BootUI ``GitHubDashboardService.refresh``, W7 Task G2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sharpit.engine.collectors.github.dashboard import GitHubDashboard
from sharpit.engine.collectors.github.detector import Repository
from sharpit.settings import SharpitSettings


def _project(root: Path, remote: str) -> Path:
    git = root / ".git"
    git.mkdir(parents=True)
    (git / "config").write_text(f'[remote "origin"]\n url = {remote}\n[branch "main"]\n merge = refs/heads/main\n')
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    return root


class CountingClient:
    def __init__(self, status: str = "CONNECTED") -> None:
        self.status = status
        self.calls = 0

    def refresh(self, repo: Repository) -> dict[str, Any]:
        self.calls += 1
        return {"status": self.status, "repository": {"fullName": repo.full_name}}


def test_refresh_uses_client_and_caches_report_for_subsequent_reads(tmp_path: Path) -> None:
    # ported: GitHubDashboardServiceTests.refreshUsesClientAndCachesReportForSubsequentReads
    root = _project(tmp_path, "git@github.com:jdubois/boot-ui.git")
    client = CountingClient()
    service = GitHubDashboard(lambda: root, SharpitSettings(), client)
    refreshed = service.refresh()
    cached = service.dashboard()
    assert client.calls == 1
    assert refreshed["status"] == "CONNECTED"
    assert cached is refreshed


def test_refresh_does_not_call_github_when_api_refresh_is_disabled(tmp_path: Path) -> None:
    # ported: GitHubDashboardServiceTests.refreshDoesNotCallGitHubWhenApiRefreshIsDisabled
    root = _project(tmp_path, "https://github.com/jdubois/boot-ui.git")
    client = CountingClient()
    service = GitHubDashboard(lambda: root, SharpitSettings(github_api_enabled=False), client)
    report = service.refresh()
    assert report["status"] == "DISABLED"
    assert client.calls == 0
    assert report["message"] == (
        "GitHub API calls are disabled. Set SHARPIT_GITHUB_API_ENABLED=true to allow the refresh action."
    )
    assert isinstance(report["refreshedAt"], int)
    assert report["connected"] is False
    assert service.dashboard() is report


def test_refresh_error_report_is_not_cached(tmp_path: Path) -> None:
    root = _project(tmp_path, "https://github.com/jdubois/boot-ui.git")
    service = GitHubDashboard(lambda: root, SharpitSettings(), CountingClient("ERROR"))
    assert service.refresh()["status"] == "ERROR"
    assert service.dashboard()["status"] == "READY"


def test_refresh_outside_a_repository_never_calls_the_client(tmp_path: Path) -> None:
    client = CountingClient()
    report = GitHubDashboard(lambda: tmp_path, SharpitSettings(), client).refresh()
    assert report["status"] == "UNAVAILABLE"
    assert client.calls == 0
