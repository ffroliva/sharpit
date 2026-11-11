"""Local dashboard state for the GitHub panel."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

from sharpit.engine.collectors.github.detector import Repository, detect_repository
from sharpit.settings import SharpitSettings

_READY_MESSAGE = "Click Connect to load live GitHub metrics and quota state."
_COPILOT_DOCS = "https://docs.github.com/en/rest/copilot/copilot-usage-metrics"


class GitHubClientPort(Protocol):
    def refresh(self, repo: Repository) -> dict[str, Any]: ...


class GitHubDashboard:
    def __init__(
        self,
        start: Callable[[], Path],
        settings: SharpitSettings,
        client: GitHubClientPort | None = None,
    ) -> None:
        self._start = start
        self._settings = settings
        self._client = client
        self.last_report: dict[str, Any] | None = None

    def dashboard(self) -> dict[str, Any]:
        repo = self._repository()
        if not isinstance(repo, Repository):
            return self._unavailable(repo)
        cached = self.last_report
        if cached is not None:
            cached_repo: object = cached.get("repository")
            if isinstance(cached_repo, dict) and cast(dict[str, Any], cached_repo).get("fullName") == repo.full_name:
                return cached
        return self._ready(repo)

    def refresh(self) -> dict[str, Any]:
        repo = self._repository()
        if not isinstance(repo, Repository):
            return self._unavailable(repo)
        if self._client is None:
            return self.dashboard()
        report = self._client.refresh(repo)
        if report.get("status") != "ERROR":
            self.last_report = report
        return report

    def _repository(self) -> Repository | str:
        return detect_repository(self._start(), frozenset(self._settings.github_allowed_api_hosts))

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "unavailableReason": reason,
            "connected": False,
            "status": "UNAVAILABLE",
            "message": reason,
            "refreshedAt": None,
            "repository": None,
            "credential": {"source": "none", "authenticated": False, "login": None, "scopes": None},
            "metrics": [],
            "quotas": [],
            "pullRequests": [],
            "workflowRuns": [],
            "workflows": [],
            "issueBuckets": [],
            "issues": [],
            "securitySignals": [],
            "copilotUsage": {
                "status": "UNAVAILABLE",
                "scope": None,
                "summary": "Copilot usage report unavailable",
                "reportStartDay": None,
                "reportEndDay": None,
                "downloadLinkCount": None,
                "documentationUrl": _COPILOT_DOCS,
                "unavailableReason": "No GitHub repository is available",
            },
            "warnings": [],
        }

    @staticmethod
    def _ready(repo: Repository) -> dict[str, Any]:
        return {
            "available": True,
            "unavailableReason": None,
            "connected": False,
            "status": "READY",
            "message": _READY_MESSAGE,
            "refreshedAt": None,
            "repository": {
                "owner": repo.owner,
                "name": repo.name,
                "fullName": repo.full_name,
                "host": repo.host,
                "apiBaseUrl": repo.api_base_uri,
                "htmlUrl": repo.html_url,
                "defaultBranch": None,
                "localBranch": repo.local_branch,
                "upstreamBranch": repo.upstream_branch,
                "visibility": None,
                "privateRepository": None,
                "fork": None,
                "archived": None,
                "pushedAt": None,
                "stars": None,
                "forks": None,
                "watchers": None,
                "openIssues": None,
                "latestRelease": None,
            },
            "credential": {"source": "not connected", "authenticated": False, "login": None, "scopes": None},
            "metrics": [],
            "quotas": [],
            "pullRequests": [],
            "workflowRuns": [],
            "workflows": [],
            "issueBuckets": [],
            "issues": [],
            "securitySignals": [],
            "copilotUsage": {
                "status": "UNAVAILABLE",
                "scope": None,
                "summary": "Copilot usage report unavailable",
                "reportStartDay": None,
                "reportEndDay": None,
                "downloadLinkCount": None,
                "documentationUrl": _COPILOT_DOCS,
                "unavailableReason": "Connect to GitHub to probe Copilot usage reports",
            },
            "warnings": [],
        }
