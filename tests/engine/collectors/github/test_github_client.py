"""GitHub token provider and REST client (W7 Task G2). Every request lands on ``FakeTransport``: no test reaches
``api.github.com``, and the ``no_side_effects`` socket block proves it where a test could otherwise slip.

Dropped (JVM-only): none; ``anEmptyEnvironmentNeverYieldsAnEnvironmentSourcedToken`` drives ``gh`` through a fake
runner instead of whatever ``gh`` the build machine has.
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
import threading
import time
import types
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from tests.engine.collectors.github.fakes import SCOPES, client, ok, repository

from sharpit.engine.collectors.github import client as client_module
from sharpit.engine.collectors.github import token as token_module
from sharpit.engine.collectors.github.token import Token, resolve_token

ORG = "jdubois"
REPO = f"/repos/{ORG}/boot-ui"
BUDGET_TEXT = "because the configured GitHub API call budget was reached."


class _Output(io.BytesIO):
    """gh's stdout; ``consumed`` survives ``close()``."""

    consumed = 0
    block: threading.Event | None = None
    delay = 0.0

    def read(self, size: int | None = -1, /) -> bytes:
        time.sleep(self.delay)
        if self.block is not None:
            self.block.wait(3.0)
            return b""
        data = super().read(size)
        self.consumed += len(data)
        return data


class FakeProc:
    """A ``subprocess.Popen`` result: ``stdout`` to read, ``wait`` records its timeout, ``kill`` is counted."""

    def __init__(self, stdout: bytes, returncode: int, hangs: bool, blocks: str = "") -> None:
        self.stdout = _Output(stdout)
        self.returncode = returncode
        self.hangs = hangs or blocks in {"until-killed", "forever", "slow"}
        self.slow = blocks == "slow"
        self.waited: list[float | None] = []
        self.kills = 0
        self.killed = threading.Event()
        # "until-killed": the read ends when kill() runs; "forever": a shim's child keeps stdout open past the kill;
        # "exited": the shim has exited (poll() answers) but its child holds stdout until the tree is killed; all
        # bounded at 3 s so a regression cannot hang the suite. "slow": the read takes 0.3 s, wait() sleeps its timeout
        if blocks in {"until-killed", "exited"}:
            self.stdout.block = self.killed
        elif blocks == "forever":
            self.stdout.block = threading.Event()
        elif blocks == "slow":
            self.stdout.delay = 0.3

    def wait(self, timeout: float | None = None) -> int:
        self.waited.append(timeout)
        if self.slow and not self.kills:
            time.sleep(min(timeout or 0.0, 2.0))
        if self.hangs and not self.kills:
            raise subprocess.TimeoutExpired(["gh"], timeout or 0)
        return self.returncode

    def poll(self) -> int | None:
        return None if self.hangs and not self.kills else self.returncode

    def kill(self) -> None:
        self.kills += 1
        self.killed.set()


class Runner:
    """A ``subprocess.Popen`` stand-in that records its call and answers like ``gh auth token``."""

    def __init__(
        self,
        stdout: bytes = b"cli-token\n",
        returncode: int = 0,
        raises: BaseException | None = None,
        hangs: bool = False,
        blocks: str = "",
    ) -> None:
        self.stdout, self.returncode, self.raises, self.hangs = stdout, returncode, raises, hangs
        self.blocks = blocks
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self.procs: list[FakeProc] = []

    def __call__(self, args: Any, **kwargs: Any) -> FakeProc:
        self.calls.append((args, kwargs))
        if self.raises is not None:
            raise self.raises
        self.procs.append(FakeProc(self.stdout, self.returncode, self.hangs, self.blocks))
        return self.procs[-1]


def _gh_dir(root: Path) -> Path:
    """A directory holding an executable ``gh`` (``gh.exe`` on Windows, where PATHEXT decides)."""
    root.mkdir(parents=True, exist_ok=True)
    gh = root / ("gh.exe" if sys.platform == "win32" else "gh")
    gh.write_bytes(b"")
    gh.chmod(0o755)
    return root


@pytest.fixture
def gh_env(tmp_path: Path) -> dict[str, str]:
    return {"PATH": str(_gh_dir(tmp_path / "bin"))}


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


def test_an_empty_environment_never_yields_an_environment_sourced_token(gh_env: dict[str, str]) -> None:
    # ported: DefaultGitHubTokenProviderTests.anEmptyEnvironmentNeverYieldsAnEnvironmentSourcedToken
    runner = Runner(b"  cli-token \n")
    token = resolve_token(0.5, gh_env, runner)
    assert token == Token("cli-token", "gh auth token")
    ((args, kwargs),) = runner.calls
    assert Path(args[0]).parent == Path(gh_env["PATH"])
    assert args[1:] == ["auth", "token"]
    assert kwargs["shell"] is False
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["stdin"] == subprocess.DEVNULL
    ((waited,),) = [runner.procs[0].waited]
    assert 0.0 < waited <= 0.5  # what is left of the 0.5 s lookup


@pytest.mark.parametrize(
    "runner",
    [
        Runner(returncode=1),
        Runner(b"   \n"),
        Runner(raises=FileNotFoundError("gh")),
        Runner(hangs=True),
        Runner(b"x" * 5000),
    ],
    ids=["logged-out", "blank", "not-installed", "hangs", "oversized"],
)
def test_gh_failures_give_no_token(runner: Runner, gh_env: dict[str, str]) -> None:
    assert resolve_token(5.0, gh_env, runner) is None
    assert [proc.poll() is not None for proc in runner.procs] == [True] * len(runner.procs)  # none left running


def test_gh_output_is_read_bounded(gh_env: dict[str, str]) -> None:
    runner = Runner(b"x" * 5000)
    assert resolve_token(5.0, gh_env, runner) is None
    assert runner.procs[0].stdout.consumed <= 4097


def test_a_missing_or_non_positive_timeout_falls_back_to_the_default_instead_of_failing(
    gh_env: dict[str, str],
) -> None:
    # ported: DefaultGitHubTokenProviderTests.aMissingOrNonPositiveTimeoutFallsBackToTheDefaultInsteadOfFailing
    assert resolve_token(None, {"GITHUB_TOKEN": "primary"}, Runner()) == Token("primary", "GITHUB_TOKEN")
    for timeout in (None, 0.0, -1.0):
        runner = Runner()
        resolve_token(timeout, gh_env, runner)
        ((waited,),) = [runner.procs[0].waited]
        assert 4.0 < waited <= 5.0


def test_create_reads_the_real_process_environment_without_throwing(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: DefaultGitHubTokenProviderTests.createReadsTheRealProcessEnvironmentWithoutThrowing
    monkeypatch.setenv("GITHUB_TOKEN", "from-process")
    assert resolve_token(5.0) == Token("from-process", "GITHUB_TOKEN")


def test_token_repr_never_shows_the_value() -> None:
    assert "ghp_canary" not in repr(Token("ghp_canary", "GITHUB_TOKEN"))


def test_gh_inside_the_working_directory_is_never_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _gh_dir(tmp_path / "app")  # a planted gh in the app's own directory (Windows searches the cwd first)
    monkeypatch.chdir(app)
    _gh_dir(app / "tools")
    for path in ("", ".", str(app), str(app / "tools"), os.pathsep.join([".", str(tmp_path / "empty")])):
        runner = Runner()
        assert resolve_token(5.0, {"PATH": path}, runner) is None
        assert runner.calls == []


def test_gh_is_resolved_to_an_absolute_path_outside_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _gh_dir(tmp_path / "app")
    monkeypatch.chdir(app)
    real = _gh_dir(tmp_path / "bin")
    runner = Runner()
    token = resolve_token(5.0, {"PATH": os.pathsep.join([str(app), str(real)])}, runner)
    assert token == Token("cli-token", "gh auth token")
    assert Path(runner.calls[0][0][0]).parent == real


@pytest.mark.parametrize("blocks", ["until-killed", "forever"])
def test_a_gh_whose_stdout_never_closes_gives_no_token_within_the_timeout(blocks: str, gh_env: dict[str, str]) -> None:
    runner = Runner(blocks=blocks)
    started = time.monotonic()
    assert resolve_token(0.2, gh_env, runner) is None
    elapsed = time.monotonic() - started
    assert elapsed < 1.5  # the read is abandoned at the 0.2 s timeout, not when the pipe finally closes (3 s)
    assert runner.procs[0].kills >= 1


@pytest.mark.skipif(sys.platform != "win32", reason="extended-length paths are Windows-only")
def test_an_extended_length_path_entry_cannot_reach_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _gh_dir(tmp_path / "app")
    monkeypatch.chdir(app)
    runner = Runner()
    assert resolve_token(5.0, {"PATH": "\\\\?\\" + str(app)}, runner) is None
    assert runner.calls == []


def _same_dir_forms(app: Path) -> list[str]:
    plain = str(app)
    return [
        "\\\\?\\GLOBALROOT\\??\\" + plain,  # an NT object-manager path to the same directory
        "\\\\localhost\\" + plain[0] + "$" + plain[2:],  # the admin share of the same drive
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="NT object and admin-share paths are Windows-only")
@pytest.mark.parametrize("form", [0, 1], ids=["globalroot", "admin-share"])
def test_another_spelling_of_the_working_directory_is_refused(
    form: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _gh_dir(tmp_path / "app")
    monkeypatch.chdir(app)
    entry = _same_dir_forms(app)[form]
    if not os.path.isdir(entry):
        pytest.skip(f"{entry} is not reachable on this machine")
    runner = Runner()
    assert resolve_token(5.0, {"PATH": entry}, runner) is None
    assert runner.calls == []


def test_a_shim_that_exits_but_leaves_a_child_on_stdout_is_killed_and_closed(gh_env: dict[str, str]) -> None:
    runner = Runner(blocks="exited")
    started = time.monotonic()
    assert resolve_token(0.3, gh_env, runner) is None
    assert time.monotonic() - started < 1.5
    proc = runner.procs[0]
    assert proc.kills >= 1  # the tree is killed although the shim itself already exited
    assert proc.stdout.closed  # the reader ended (the kill released the pipe) and the pipe was closed


def test_the_whole_token_lookup_is_bounded_by_its_timeout(gh_env: dict[str, str]) -> None:
    runner = Runner(blocks="slow")  # the read takes 0.3 s, then wait() sleeps whatever it is given
    started = time.monotonic()
    resolve_token(0.5, gh_env, runner)
    elapsed = time.monotonic() - started
    assert elapsed < 0.75  # read 0.3 + wait capped at the 0.2 left (+ slack), not read 0.3 + a fresh 0.5 wait


def test_a_failed_reader_start_still_kills_reaps_and_closes(
    gh_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []

    class RecordingTree(token_module._Tree):  # pyright: ignore[reportPrivateUsage]
        def close(self) -> None:
            closed.append(True)
            super().close()

    class NoThread(threading.Thread):
        def start(self) -> None:
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(token_module, "_Tree", RecordingTree)
    monkeypatch.setattr(token_module, "threading", types.SimpleNamespace(Thread=NoThread))
    runner = Runner(hangs=True)
    try:
        result: object = resolve_token(1.0, gh_env, runner)
    except RuntimeError as error:  # an escaped failure is the defect; the assertions below name it
        result = f"raised {error}"
    assert result is None
    proc = runner.procs[0]
    assert proc.kills >= 1
    assert proc.poll() is not None
    assert proc.stdout.closed
    assert closed == [True]


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


def _refresh(github: Any) -> dict[str, Any]:
    """``refresh``, with an escaped exception turned into a report the assertions can name (a crash is not a red)."""
    try:
        return github.refresh(repository())
    except Exception as error:  # noqa: BLE001
        return {"status": f"raised {type(error).__name__}", "message": None, "connected": None}


def _timeout(_request: urllib.request.Request) -> Any:
    raise TimeoutError("timed out")


@pytest.mark.parametrize(
    "rate",
    [
        (401, '{"message":"Bad credentials"}', SCOPES),
        _timeout,
        ok("{not json"),
        ok('{"resources":{"core":{"limit":NaN,"remaining":NaN}}}'),
    ],
    ids=["401", "timeout", "malformed", "nan"],
)
def test_github_token_never_in_output(rate: Any, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    github, _ = client({"/rate_limit": rate}, token=CANARY)
    report = _refresh(github)
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
    assert len(transport.requests) == 13
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


@pytest.mark.parametrize(
    ("route", "body", "key", "field", "value"),
    [
        (f"{REPO}/actions/artifacts", '{"total_count": 1e999}', "actions-artifacts", "used", None),
        (f"{REPO}/actions/cache/usage", '{"active_caches_size_in_bytes": -1e999}', "actions-cache", "used", None),
        (
            f"/orgs/{ORG}/settings/billing/actions",
            '{"included_minutes": 1e999, "total_minutes_used": 5}',
            "actions-minutes",
            "limit",
            None,
        ),
        (f"{REPO}/actions/artifacts", '{"total_count": 1e30}', "actions-artifacts", "used", None),
        (
            f"{REPO}/actions/artifacts",
            '{"total_count": 1000000000000000000000000000000}',
            "actions-artifacts",
            "used",
            None,
        ),
        (f"{REPO}/actions/artifacts", '{"total_count": 9223372036854775807}', "actions-artifacts", "used", 2**63 - 1),
        (f"{REPO}/actions/artifacts", '{"total_count": "42"}', "actions-artifacts", "used", 42),
        (f"{REPO}/actions/artifacts", '{"total_count": "1.5"}', "actions-artifacts", "used", None),
        (f"{REPO}/actions/artifacts", '{"total_count": 7.9}', "actions-artifacts", "used", 7),
        (
            f"{REPO}/actions/artifacts",
            '{"total_count": 9.223372036854775807e18}',
            "actions-artifacts",
            "used",
            2**63 - 1,
        ),
        (f"{REPO}/actions/artifacts", '{"total_count": "+5"}', "actions-artifacts", "used", 5),
        (f"{REPO}/actions/artifacts", '{"total_count": "\\u0663"}', "actions-artifacts", "used", None),
        (f"{REPO}/actions/artifacts", '{"total_count": "' + "1" * 5000 + '"}', "actions-artifacts", "used", None),
        (f"{REPO}/actions/artifacts", '{"total_count": ' + "1" * 5000 + "}", "actions-artifacts", "used", None),
    ],
    ids=[
        "inf",
        "minus-inf",
        "billing-inf",
        "huge-float",
        "huge-int",
        "long-max",
        "int-string",
        "fraction-string",
        "fraction",
        "long-edge-float",
        "plus-string",
        "arabic-digit",
        "5000-digit-string",
        "5000-digit-number",
    ],
)
def test_github_numbers_out_of_long_range_give_the_jackson_default(
    route: str, body: str, key: str, field: str, value: int | None, no_side_effects
) -> None:
    """Jackson 3.1.7 ``asLong(-1)`` (probed): out of range, a non-integer string or a boolean gives the default -1,
    which BootUI's ``nullable`` turns into null; an integer string is parsed and a fraction truncated."""
    github, _ = client(full_routes() | {route: ok(body)})
    report = _refresh(github)
    assert report["status"] == "CONNECTED"
    assert _one(report["quotas"], "key", key)[field] == value


@pytest.mark.parametrize(
    ("route", "body"),
    [
        (f"{REPO}/actions/runs", '{"workflow_runs": [{"id": "x", "workflow_id": 1}]}'),
        (f"{REPO}/actions/workflows", '{"workflows": [{"id": {}}]}'),
        (f"{REPO}/actions/runs", '{"workflow_runs": [{"id": 1e30}]}'),
        (f"{REPO}/pulls", '[{"number": 3000000000}]'),
        (f"{REPO}/issues", '[{"number": true}]'),
        (f"{REPO}/dependabot/alerts", '[{"number": "seven"}]'),
    ],
    ids=[
        "run-id-string",
        "workflow-id-object",
        "run-id-huge",
        "pr-number-over-int",
        "issue-number-bool",
        "alert-number",
    ],
)
def test_github_strict_numbers_fail_the_refresh_like_jackson(route: str, body: str, no_side_effects) -> None:
    """BootUI reads ids with ``asLong()`` and numbers with ``asInt()`` (no default): Jackson 3.1.7 throws
    ``JsonNodeException`` on a non-numeric or out-of-range node, which escapes BootUI's refresh (a 500). sharpit
    reports the whole refresh as ERROR with the fixed text instead."""
    github, _ = client(full_routes() | {route: ok(body)}, token=CANARY)
    report = _refresh(github)
    assert report["status"] == "ERROR"
    assert report["message"] == client_module.UNEXPECTED_FAILURE
    assert CANARY not in json.dumps(report)


def test_github_lenient_numbers_follow_jackson(no_side_effects) -> None:
    """``asInt()``/``asLong()`` on null or a missing field give 0; an integer string is parsed."""
    routes = full_routes() | {
        f"{REPO}/pulls": ok([{"number": "42"}, {"number": None}, {}]),
        f"{REPO}/actions/workflows": ok({"workflows": [{"id": None, "name": "n"}]}),
    }
    github, _ = client(routes)
    report = _refresh(github)
    assert report["status"] == "CONNECTED"
    assert [pr["number"] for pr in report["pullRequests"]] == [42, 0, 0]
    assert [w["id"] for w in report["workflows"]] == [0]


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_github_non_json_number_constants_report_error(constant: str, no_side_effects) -> None:
    rate = ok('{"resources":{"core":{"limit":C,"remaining":C}}}'.replace("C", constant))
    github, _ = client(full_routes() | {"/rate_limit": rate}, token=CANARY)
    report = _refresh(github)
    assert report["status"] == "ERROR"
    assert report["message"] == client_module.NETWORK_FAILED
    assert CANARY not in json.dumps(report)


def test_github_unexpected_failure_is_an_error_report_with_fixed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError(f"leaky {CANARY}")

    monkeypatch.setattr(client_module.m, "pull_requests", boom)
    github, _ = client(full_routes(), token=CANARY)
    report = _refresh(github)
    assert report["status"] == "ERROR"
    assert report["message"] == client_module.UNEXPECTED_FAILURE
    assert report["connected"] is False
    assert CANARY not in json.dumps(report)


class Clock:
    """``time.monotonic`` that moves 11 s on every read."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 11.0
        return self.now


def test_github_refresh_has_an_overall_deadline(no_side_effects) -> None:
    # the read timeout (100 s) is above the deadline, so every read must be capped by the time left
    github, transport = client(full_routes(), github_request_timeout=100.0)
    github.clock = Clock()  # pyright: ignore[reportAttributeAccessIssue]
    report = _refresh(github)
    assert report["status"] == "PARTIAL"
    skipped = [w for w in report["warnings"] if w.endswith("because the GitHub refresh time limit was reached.")]
    assert skipped
    # clock reads: start 11 (deadline 41), token 22, first read 33 -> 8 s left, second read 44 -> skipped
    assert [r.timeout for r in transport.requests] == [8.0]


def test_github_token_lookup_respects_the_refresh_deadline(no_side_effects) -> None:
    seen: list[float] = []

    def tokens(timeout: float) -> Token | None:
        seen.append(timeout)
        return None

    github, _ = client(full_routes(), github_request_timeout=100.0)
    github._token = tokens  # pyright: ignore[reportPrivateUsage]
    github.clock = Clock()  # pyright: ignore[reportAttributeAccessIssue]
    _refresh(github)
    assert seen == [19.0]  # deadline 41 minus the clock read 22, not the 100 s read timeout
