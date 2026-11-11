"""GitHub token provider and REST client (W7 Task G2). Every request lands on ``FakeTransport``: no test reaches
``api.github.com``, and the ``no_side_effects`` socket block proves it where a test could otherwise slip.

Dropped (JVM-only): none; ``anEmptyEnvironmentNeverYieldsAnEnvironmentSourcedToken`` drives ``gh`` through a fake
runner instead of whatever ``gh`` the build machine has.
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.parse
import urllib.request
from typing import Any

import pytest
from tests.engine.collectors.github.fakes import SCOPES, client, ok, repository

from sharpit.engine.collectors.github import client as client_module
from sharpit.engine.collectors.github.token import Token, resolve_token

ORG = "jdubois"
REPO = f"/repos/{ORG}/boot-ui"
BUDGET_TEXT = "because the configured GitHub API call budget was reached."


class Runner:
    """A ``subprocess.run`` stand-in that records its call and answers like ``gh auth token``."""

    def __init__(self, stdout: bytes = b"cli-token\n", returncode: int = 0, raises: BaseException | None = None):
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def __call__(self, args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((args, kwargs))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, None)


def _headers(request: urllib.request.Request) -> dict[str, str]:
    return {name.lower(): value for name, value in request.header_items()}


# ---- token -------------------------------------------------------------------------------------------------------


def test_github_token_is_preferred_over_gh_token() -> None:
    # ported: DefaultGitHubTokenProviderTests.githubTokenIsPreferredOverGhToken
    token = resolve_token(5.0, {"GITHUB_TOKEN": "primary", "GH_TOKEN": "secondary"}, Runner())
    assert token == Token("primary", "GITHUB_TOKEN")


def test_gh_token_is_used_when_github_token_is_absent() -> None:
    # ported: DefaultGitHubTokenProviderTests.ghTokenIsUsedWhenGithubTokenIsAbsent
    token = resolve_token(5.0, {"GH_TOKEN": "secondary"}, Runner())
    assert token == Token("secondary", "GH_TOKEN")


def test_surrounding_whitespace_is_stripped_from_the_environment_value() -> None:
    # ported: DefaultGitHubTokenProviderTests.surroundingWhitespaceIsStrippedFromTheEnvironmentValue
    token = resolve_token(5.0, {"GITHUB_TOKEN": "  padded \n"}, Runner())
    assert token == Token("padded", "GITHUB_TOKEN")


def test_a_blank_environment_token_is_ignored_in_favour_of_the_next_source() -> None:
    # ported: DefaultGitHubTokenProviderTests.aBlankEnvironmentTokenIsIgnoredInFavourOfTheNextSource
    token = resolve_token(5.0, {"GITHUB_TOKEN": "   ", "GH_TOKEN": "secondary"}, Runner())
    assert token == Token("secondary", "GH_TOKEN")


def test_an_empty_environment_never_yields_an_environment_sourced_token() -> None:
    # ported: DefaultGitHubTokenProviderTests.anEmptyEnvironmentNeverYieldsAnEnvironmentSourcedToken
    runner = Runner(b"  cli-token \n")
    token = resolve_token(0.5, {}, runner)
    assert token == Token("cli-token", "gh auth token")
    ((args, kwargs),) = runner.calls
    assert args == ["gh", "auth", "token"]
    assert kwargs["shell"] is False
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["timeout"] == 0.5


@pytest.mark.parametrize(
    "runner",
    [
        Runner(returncode=1),
        Runner(b"   \n"),
        Runner(raises=FileNotFoundError("gh")),
        Runner(raises=subprocess.TimeoutExpired(["gh"], 5.0)),
    ],
    ids=["logged-out", "blank", "not-installed", "hangs"],
)
def test_gh_failures_give_no_token(runner: Runner) -> None:
    assert resolve_token(5.0, {}, runner) is None


def test_a_missing_or_non_positive_timeout_falls_back_to_the_default_instead_of_failing() -> None:
    # ported: DefaultGitHubTokenProviderTests.aMissingOrNonPositiveTimeoutFallsBackToTheDefaultInsteadOfFailing
    assert resolve_token(None, {"GITHUB_TOKEN": "primary"}, Runner()) == Token("primary", "GITHUB_TOKEN")
    for timeout in (None, 0.0, -1.0):
        runner = Runner()
        resolve_token(timeout, {}, runner)
        assert runner.calls[0][1]["timeout"] == 5.0


def test_create_reads_the_real_process_environment_without_throwing(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: DefaultGitHubTokenProviderTests.createReadsTheRealProcessEnvironmentWithoutThrowing
    monkeypatch.setenv("GITHUB_TOKEN", "from-process")
    assert resolve_token(5.0) == Token("from-process", "GITHUB_TOKEN")


def test_token_repr_never_shows_the_value() -> None:
    assert "ghp_canary" not in repr(Token("ghp_canary", "GITHUB_TOKEN"))


# ---- client ------------------------------------------------------------------------------------------------------


RATE = {
    "resources": {
        "core": {"limit": 5000, "used": 50, "remaining": 4950, "reset": 1893456000},
        "search": {"limit": 30, "used": 2, "remaining": 28, "reset": 1893456000},
        "code_scanning_autofix": {"limit": 10, "used": 0, "remaining": 10, "reset": 1893456000},
    }
}
RUNS = {
    "workflow_runs": [
        {
            "id": 9, "workflow_id": 100, "name": "Build", "display_title": "Run tests", "run_number": 41,
            "event": "push", "status": "completed", "conclusion": "failure", "head_branch": "main",
            "triggering_actor": {"login": "alice"}, "html_url": "https://github.com/jdubois/boot-ui/actions/runs/9",
            "created_at": "2026-06-04T07:00:00Z", "run_started_at": "2026-06-04T07:01:00Z",
            "updated_at": "2026-06-04T07:05:00Z",
        },
        {
            "id": 10, "workflow_id": 100, "name": "Build", "display_title": "Run tests", "run_number": 42,
            "event": "push", "status": "completed", "conclusion": "success", "head_branch": "main",
            "triggering_actor": {"login": "alice"}, "html_url": "https://github.com/jdubois/boot-ui/actions/runs/10",
            "created_at": "2026-06-04T08:00:00Z", "run_started_at": "2026-06-04T08:01:00Z",
            "updated_at": "2026-06-04T08:05:00Z",
        },
        {
            "id": 11, "workflow_id": 200, "name": "Build", "display_title": "Manual release", "run_number": 9,
            "event": "workflow_dispatch", "status": "completed", "conclusion": "timed_out", "head_branch": "main",
            "actor": {"login": "bob"}, "html_url": "https://github.com/jdubois/boot-ui/actions/runs/11",
            "created_at": "2026-06-03T08:00:00Z", "run_started_at": "2026-06-03T08:01:00Z",
            "updated_at": "2026-06-03T08:20:00Z",
        },
        {
            "id": 12, "workflow_id": 200, "name": "Build", "display_title": "Feature branch scan", "run_number": 8,
            "event": "push", "status": "completed", "conclusion": "failure", "head_branch": "feature/github-dashboard",
            "actor": {"login": "bob"}, "html_url": "https://github.com/jdubois/boot-ui/actions/runs/12",
            "created_at": "2026-06-02T08:00:00Z", "run_started_at": "2026-06-02T08:01:00Z",
            "updated_at": "2026-06-02T08:20:00Z",
        },
    ]
}  # fmt: skip
WORKFLOWS = {
    "workflows": [
        {
            "id": 100, "name": "Build", "path": ".github/workflows/build.yml", "state": "active",
            "html_url": "https://github.com/jdubois/boot-ui/blob/main/.github/workflows/build.yml",
        },
        {
            "id": 200, "name": "CodeQL", "path": "dynamic/github-code-scanning/codeql", "state": "active",
            "html_url": "https://github.com/jdubois/boot-ui/actions/workflows/github-code-scanning/codeql",
        },
        {
            "id": 300, "name": "Native image", "path": ".github/workflows/native.yml", "state": "active",
            "html_url": "https://github.com/jdubois/boot-ui/blob/main/.github/workflows/native.yml",
        },
    ]
}  # fmt: skip
ISSUES = [
    {
        "number": 7, "title": "Bug", "user": {"login": "carol"}, "comments": 3,
        "html_url": "https://github.com/jdubois/boot-ui/issues/7", "created_at": "2026-03-30T08:00:00Z",
        "updated_at": "2026-04-01T08:30:00Z", "labels": [],
    },
    {"number": 8, "pull_request": {}, "labels": []},
]  # fmt: skip
PULLS = [
    {
        "number": 42, "title": "Add dashboard", "draft": False, "html_url": "https://github.com/jdubois/boot-ui/pull/42",
        "updated_at": "2026-06-04T08:30:00Z", "user": {"login": "alice"}, "labels": [{"name": "feature"}],
    }
]  # fmt: skip


def _copilot(request: urllib.request.Request) -> tuple[int, str, dict[str, str]]:
    if _headers(request).get("x-github-api-version") != "2026-03-10":
        return 400, "", {}
    body = {
        "report_start_day": "2026-05-07",
        "report_end_day": "2026-06-03",
        "download_links": ["https://signed.example/report.ndjson"],
    }
    return ok(body)


def full_routes() -> dict[str, Any]:
    return {
        "/rate_limit": ok(RATE),
        REPO: ok(
            {
                "full_name": "jdubois/boot-ui",
                "html_url": "https://github.com/jdubois/boot-ui",
                "default_branch": "main",
                "visibility": "public",
                "private": False,
                "fork": False,
                "archived": False,
                "pushed_at": "2026-06-04T08:00:00Z",
                "stargazers_count": 12,
                "forks_count": 3,
                "subscribers_count": 4,
                "open_issues_count": 7,
                "owner": {"type": "Organization"},
            }
        ),  # fmt: skip
        f"{REPO}/pulls": ok(PULLS),
        f"{REPO}/issues": ok(ISSUES),
        f"{REPO}/actions/runs": ok(RUNS),
        f"{REPO}/actions/workflows": ok(WORKFLOWS),
        f"{REPO}/dependabot/alerts": ok([{}] * 40),
        f"{REPO}/code-scanning/alerts": ok([]),
        f"{REPO}/secret-scanning/alerts": ok([]),
        f"{REPO}/actions/cache/usage": ok({"active_caches_size_in_bytes": 2048}),
        f"{REPO}/actions/artifacts": ok({"total_count": 5}),
        f"/orgs/{ORG}/settings/billing/actions": ok({"included_minutes": 2000, "total_minutes_used": 125}),
        f"/orgs/{ORG}/copilot/metrics/reports/organization-28-day/latest": _copilot,
    }


def _one(rows: list[dict[str, Any]], key: str, value: object) -> dict[str, Any]:
    found = [row for row in rows if row[key] == value]
    assert len(found) == 1, found
    return found[0]


def test_refresh_loads_repository_metrics_and_dynamic_quota_resources(no_side_effects) -> None:
    # ported: GitHubApiClientTests.refreshLoadsRepositoryMetricsAndDynamicQuotaResources
    github, transport = client(full_routes())
    report = github.refresh(repository())
    assert report["status"] == "CONNECTED"
    assert report["connected"] is True
    assert report["credential"] == {
        "source": "test-token", "authenticated": True, "login": None, "scopes": "repo, workflow"
    }  # fmt: skip
    assert report["repository"]["defaultBranch"] == "main"
    assert [pr["number"] for pr in report["pullRequests"]] == [42]
    assert _one(report["workflowRuns"], "id", 11)["conclusion"] == "timed_out"
    run = _one(report["workflowRuns"], "id", 10)
    assert (run["workflowId"], run["displayTitle"], run["runNumber"], run["actor"]) == (100, "Run tests", 42, "alice")
    assert [w["name"] for w in report["workflows"]] == ["Build", "CodeQL", "Native image"]
    build = _one(report["workflows"], "id", 100)
    assert build["htmlUrl"] == "https://github.com/jdubois/boot-ui/actions/workflows/build.yml"
    assert build["latestRun"]["id"] == 10
    codeql = _one(report["workflows"], "id", 200)
    assert codeql["htmlUrl"] == "https://github.com/jdubois/boot-ui/actions/workflows/github-code-scanning/codeql"
    assert codeql["latestRun"]["id"] == 11
    assert _one(report["workflows"], "id", 300)["latestRun"] is None
    assert _one(report["issueBuckets"], "label", "Stale 30d+")["count"] == 1
    (issue,) = report["issues"]
    assert (issue["number"], issue["title"], issue["author"], issue["comments"]) == (7, "Bug", "carol", 3)
    assert issue["htmlUrl"] == "https://github.com/jdubois/boot-ui/issues/7"
    keys = [q["key"] for q in report["quotas"]]
    for key in ("core", "search", "code_scanning_autofix", "actions-cache", "actions-artifacts", "actions-minutes"):
        assert key in keys
    assert _one(report["quotas"], "key", "code_scanning_autofix")["status"] == "OK"
    failures = _one(report["metrics"], "label", "Workflow failures")
    assert (failures["value"], failures["detail"]) == ("2", "Latest run per workflow/branch")
    assert _one(report["metrics"], "label", "Copilot usage")["value"] == "Available"
    assert report["copilotUsage"]["status"] == "AVAILABLE"
    assert report["copilotUsage"]["downloadLinkCount"] == 1
    assert "signed.example" not in report["copilotUsage"]["summary"]
    assert _one(report["securitySignals"], "label", "Dependabot alerts")["count"] == 40
    assert _one(report["securitySignals"], "label", "Code scanning alerts")["count"] == 0
    assert _one(report["securitySignals"], "label", "Secret scanning alerts")["count"] == 0
    first = _headers(transport.requests[0])
    assert first["authorization"] == "Bearer local-token"
    assert first["accept"] == "application/vnd.github+json"
    assert first["user-agent"] == "sharpit"
    assert first["x-github-api-version"] == "2022-11-28"
    assert transport.paths()[0] == "/rate_limit"


def test_skips_optional_calls_when_core_quota_is_near_safety_threshold(no_side_effects) -> None:
    # ported: GitHubApiClientTests.skipsOptionalCallsWhenCoreQuotaIsNearSafetyThreshold
    rate = {"resources": {"core": {"limit": 60, "used": 59, "remaining": 1, "reset": 1893456000}}}
    github, transport = client({"/rate_limit": ok(rate)}, token=None)
    report = github.refresh(repository())
    assert report["status"] == "QUOTA_PROTECTED"
    assert report["pullRequests"] == []
    assert [q["key"] for q in report["quotas"]] == ["core"]
    (warning,) = report["warnings"]
    assert "safety threshold" in warning
    assert report["credential"]["source"] == "unauthenticated"
    assert transport.paths() == ["/rate_limit"]
    assert "authorization" not in _headers(transport.requests[0])


def test_dependabot_signal_includes_safe_alert_details(no_side_effects) -> None:
    # ported: GitHubApiClientTests.dependabotSignalIncludesSafeAlertDetails
    alert = {
        "number": 7, "state": "open",
        "dependency": {"package": {"ecosystem": "maven", "name": "org.example:lib"}, "manifest_path": "pom.xml"},
        "security_advisory": {
            "ghsa_id": "GHSA-aaaa-bbbb-cccc", "cve_id": "CVE-2026-1234", "summary": "Remote code execution",
            "severity": "high",
        },
        "security_vulnerability": {
            "severity": "critical", "vulnerable_version_range": "< 1.2.3",
            "first_patched_version": {"identifier": "1.2.3"},
        },
        "html_url": "https://github.com/jdubois/boot-ui/security/dependabot/7",
        "created_at": "2026-05-01T08:00:00Z", "updated_at": "2026-05-02T08:00:00Z",
    }  # fmt: skip
    routes = {
        "/rate_limit": ok({"resources": {"core": {"limit": 5000, "used": 50, "remaining": 4950, "reset": 1893456000}}}),
        REPO: ok({"full_name": "jdubois/boot-ui", "default_branch": "main", "owner": {"type": "User"}}),
        f"{REPO}/dependabot/alerts": ok([alert]),
        f"{REPO}/code-scanning/alerts": ok([]),
        f"{REPO}/secret-scanning/alerts": ok([]),
        f"/users/{ORG}/settings/billing/actions": ok({"included_minutes": 0, "total_minutes_used": 0}),
    }
    github, _ = client(routes)
    report = github.refresh(repository())
    dependabot = _one(report["securitySignals"], "label", "Dependabot alerts")
    assert dependabot["count"] == 1
    (found,) = dependabot["alerts"]
    assert (found["packageName"], found["ecosystem"], found["severity"]) == ("org.example:lib", "maven", "critical")
    assert (found["ghsaId"], found["cveId"], found["firstPatchedVersion"]) == (
        "GHSA-aaaa-bbbb-cccc",
        "CVE-2026-1234",
        "1.2.3",
    )
    assert found["htmlUrl"] == "https://github.com/jdubois/boot-ui/security/dependabot/7"
    others = [s for s in report["securitySignals"] if s["label"] != "Dependabot alerts"]
    assert [s["alerts"] for s in others] == [[], []]


def test_github_blocked_host_reads_no_token(monkeypatch: pytest.MonkeyPatch, no_side_effects) -> None:
    # ported: GitHubApiClientTest.rejectsRefreshWhenApiHostIsNotAllowed (BootUI Quarkus)
    def no_process(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError("spawned a process")

    monkeypatch.setattr(subprocess, "Popen", no_process)
    github, transport = client({})
    github._token = no_process  # pyright: ignore[reportPrivateUsage]
    report = github.refresh(repository("ghe.example.com", "https://ghe.example.com/api/v3/"))
    assert report["status"] == "BLOCKED"
    assert "is not allowed" in report["message"]
    assert "SHARPIT_GITHUB_ALLOWED_API_HOSTS" in report["message"]
    assert report["credential"]["source"] == "not connected"
    assert transport.requests == []


@pytest.mark.parametrize("code", [301, 302, 307, 308])
def test_github_client_never_follows_redirects(code: int, no_side_effects) -> None:
    moved = (code, "", {"Location": "https://evil.example/steal"})
    github, transport = client({"/rate_limit": moved, "/steal": ok(RATE)})
    report = github.refresh(repository())
    assert report["status"] == "ERROR"
    assert report["message"] == f"GitHub returned HTTP {code} for rate limits."
    assert len(transport.requests) == 1
    routes = full_routes() | {REPO: moved}
    github, transport = client(routes)
    report = github.refresh(repository())
    assert f"GitHub returned HTTP {code} for repository metadata." in report["warnings"]
    assert {urllib.parse.urlsplit(r.full_url).hostname for r in transport.requests} == {"api.github.com"}


def test_github_last_page_uses_known_host(no_side_effects) -> None:
    link = (
        '<https://evil.example/steal?page=1>; rel="next", <https://evil.example/steal?per_page=100&page=3>; rel="last"'
    )
    routes = full_routes() | {f"{REPO}/dependabot/alerts": ok([{}] * 100, {"Link": link})}

    def final_or_first(request: urllib.request.Request) -> tuple[int, str, dict[str, str]]:
        return ok([{}] * 7) if "page=3" in request.full_url else ok([{}] * 100, {"Link": link})

    routes[f"{REPO}/dependabot/alerts"] = final_or_first
    github, transport = client(routes)
    report = github.refresh(repository())
    assert _one(report["securitySignals"], "label", "Dependabot alerts")["count"] == 207
    finals = [r.full_url for r in transport.requests if "page=3" in r.full_url]
    assert finals == ["https://api.github.com/repos/jdubois/boot-ui/dependabot/alerts?state=open&per_page=100&page=3"]
    assert {urllib.parse.urlsplit(r.full_url).hostname for r in transport.requests} == {"api.github.com"}


@pytest.mark.parametrize(
    "link",
    [
        '<https://api.github.com/x?page=99999999999>; rel="last"',
        '<https://api.github.com/x?page=1_0>; rel="last"',
        '<https://api.github.com/x?page=>; rel="last"',
        '<https://api.github.com/x>; rel="last"',
        'https://api.github.com/x?page=3; rel="last"',
    ],
    ids=["overflow", "underscore", "empty", "no-page", "no-brackets"],
)
def test_github_odd_last_page_links_keep_the_first_page_count(link: str, no_side_effects) -> None:
    routes = full_routes() | {f"{REPO}/dependabot/alerts": ok([{}] * 100, {"Link": link})}
    github, transport = client(routes)
    report = github.refresh(repository())
    assert _one(report["securitySignals"], "label", "Dependabot alerts")["count"] == 100
    assert transport.paths().count(f"{REPO}/dependabot/alerts") == 1


CANARY = "ghp_canary0123456789abcdefghijklmnopqrstu"


def _timeout(_request: urllib.request.Request) -> Any:
    raise TimeoutError("timed out")


@pytest.mark.parametrize(
    "rate",
    [(401, '{"message":"Bad credentials"}', SCOPES), _timeout, ok("{not json")],
    ids=["401", "timeout", "malformed"],
)
def test_github_token_never_in_output(rate: Any, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    github, _ = client({"/rate_limit": rate}, token=CANARY)
    report = github.refresh(repository())
    assert report["status"] == "ERROR"
    assert CANARY not in json.dumps(report)
    assert CANARY not in caplog.text


def test_github_transport_failure_reports_error_with_fixed_text(no_side_effects) -> None:
    github, _ = client(full_routes() | {f"{REPO}/pulls": _timeout})
    report = github.refresh(repository())
    assert report["status"] == "ERROR"
    assert report["message"] == client_module.NETWORK_FAILED
    assert report["warnings"] == [client_module.NETWORK_FAILED]
    assert report["connected"] is False


def test_github_fetched_text_is_scrubbed(no_side_effects) -> None:
    secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    pulls = [dict(PULLS[0], title=f"Fix login token={secret}", labels=[{"name": f"token={secret}"}])]
    github, _ = client(full_routes() | {f"{REPO}/pulls": ok(pulls)})
    report = github.refresh(repository())
    assert len(report["pullRequests"]) == 1
    (pr,) = report["pullRequests"]
    assert pr["title"].startswith("Fix login")
    assert secret not in json.dumps(report)


def test_github_budget_and_body_cap(no_side_effects) -> None:
    github, transport = client(full_routes())
    github.refresh(repository())
    assert len(transport.requests) <= 17
    github, transport = client(full_routes(), github_max_api_calls=3)
    report = github.refresh(repository())
    assert len(transport.requests) == 3
    assert f"Skipped issues {BUDGET_TEXT}" in report["warnings"]
    assert report["status"] == "PARTIAL"
    github, transport = client(full_routes(), github_max_api_calls=0)
    github.refresh(repository())
    assert len(transport.requests) == 1
    cap = client_module.MAX_BODY_BYTES
    exact = json.dumps(RATE).ljust(cap)
    github, _ = client(full_routes() | {"/rate_limit": ok(exact)})
    assert github.refresh(repository())["status"] == "CONNECTED"
    github, _ = client(full_routes() | {"/rate_limit": ok(exact + " ")})
    over = github.refresh(repository())
    assert over["status"] == "ERROR"
    assert over["message"] == client_module.NETWORK_FAILED


def test_github_copilot_no_data_and_user_owner(no_side_effects) -> None:
    routes = full_routes() | {f"/orgs/{ORG}/copilot/metrics/reports/organization-28-day/latest": (204, "", {})}
    github, _ = client(routes)
    report = github.refresh(repository())
    assert report["copilotUsage"]["status"] == "NO_DATA"
    assert _one(report["metrics"], "label", "Copilot usage")["value"] == "No data"
    user = full_routes()
    user[REPO] = ok({"owner": {"type": "User"}})
    user[f"/users/{ORG}/settings/billing/actions"] = ok({"included_minutes": 100, "total_minutes_used": 25})
    github, transport = client(user)
    report = github.refresh(repository())
    assert report["copilotUsage"]["unavailableReason"] == (
        "Copilot organization metrics are only available for organization owners."
    )
    minutes = _one(report["quotas"], "key", "actions-minutes")
    assert (minutes["limit"], minutes["used"], minutes["remaining"], minutes["percentUsed"]) == (100, 25, 75, 25)
    assert not any("copilot" in path for path in transport.paths())


def test_github_non_https_api_base_never_sends_the_token(no_side_effects) -> None:
    github, transport = client({}, github_allowed_api_hosts=("localhost",))
    report = github.refresh(repository("localhost", "http://localhost/"))
    assert report["status"] == "ERROR"
    assert transport.requests == []
