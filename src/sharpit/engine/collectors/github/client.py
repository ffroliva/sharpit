"""GitHub REST client for the refresh action (port of BootUI ``GitHubApiClient``, transport and call order).

The only ``urllib.request`` / ``http.client`` importer for GitHub (AGENTS.md rule 4), used only by
``POST {api}/github/refresh``, never by a read. Safety, beyond BootUI's own:
- the opener never follows a redirect, so the ``Authorization`` header never reaches another host (BootUI's JDK
  client has redirects ``NEVER``); a 3xx is reported as ``GitHub returned HTTP 3xx for <label>.``;
- the last-page request is rebuilt from the configured API base and a parsed page number, never from the ``Link`` URL;
- a transport failure raises nothing out of ``refresh``: it reports ``ERROR`` with a fixed text, never the request.
The opener is injectable for tests and built lazily, like ``vulns/osv.py``.
"""

from __future__ import annotations

import http.client
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sharpit.engine.collectors.github import mapping as m
from sharpit.engine.collectors.github.detector import Repository
from sharpit.engine.collectors.github.token import Token, safe_timeout
from sharpit.settings import SharpitSettings

USER_AGENT = "sharpit"
GITHUB_API_VERSION = "2022-11-28"
COPILOT_API_VERSION = "2026-03-10"
MAX_BODY_BYTES = 2 * 1024 * 1024  # BootUI BoundedBodyReader.GITHUB_MAX_BYTES
NETWORK_FAILED = "Network request failed or timed out while refreshing GitHub data."
UNEXPECTED_FAILURE = "GitHub refresh failed before it completed."
REFRESH_DEADLINE = 30.0  # seconds for the whole refresh, on top of each read's timeout
PARTIAL = "Some GitHub sections are unavailable."
QUOTA_WARNING = "Optional GitHub calls were skipped because the core API quota is near its safety threshold."
QUOTA_MESSAGE = "GitHub rate limits loaded; live repository calls were skipped to preserve remaining quota."
_QUOTA_COPILOT = "Live repository calls were skipped to preserve remaining quota."
_ORGANIZATION = "Organization"
_MAX_INT_DIGITS = 4000  # below sys.get_int_max_str_digits() (4300)
_PAGE_SIZE = 100
_INT_MAX = 2**31 - 1  # Java Integer.parseInt bound on the Link page number
_PAGE_NUMBER = re.compile(r"[+-]?\d+")
_SIGNALS = (
    ("Dependabot alerts", "dependabot/alerts?state=open&per_page=100", True),
    ("Code scanning alerts", "code-scanning/alerts?state=open&per_page=100", False),
    ("Secret scanning alerts", "secret-scanning/alerts?state=open&per_page=100", False),
)


class Opener(Protocol):
    def open(self, fullurl: urllib.request.Request, data: Any = ..., timeout: float | None = ...) -> Any: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None  # urllib then raises HTTPError(3xx): the request is never re-sent anywhere


def no_redirect_opener(*handlers: urllib.request.BaseHandler) -> urllib.request.OpenerDirector:
    """urllib's opener with its redirect handler replaced by one that never follows."""
    return urllib.request.build_opener(_NoRedirect, *handlers)


class _Failed(Exception):
    """Transport failure, oversized or malformed body: the refresh reports ERROR (BootUI's ``IOException``)."""


@dataclass(frozen=True)
class _Response:
    status: int
    json: Any
    headers: Any
    message: str | None

    @property
    def success(self) -> bool:
        return 200 <= self.status < 300

    def header(self, name: str) -> str | None:
        value = None if self.headers is None else self.headers.get(name)
        return value if isinstance(value, str) else None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _positive(value: int, fallback: int) -> int:
    return value if value > 0 else fallback


def _credential(token: Token | None, response: _Response | None, scrub: m.Scrub) -> dict[str, Any]:
    if token is None or not token.value.strip():
        return {"source": "unauthenticated", "authenticated": False, "login": None, "scopes": None}
    scopes = response.header("X-OAuth-Scopes") if response is not None else None
    return {
        "source": token.source,
        "authenticated": True,
        "login": None,
        "scopes": scrub(scopes) if scopes is not None and scopes.strip() else None,
    }


def _empty_sections(copilot: dict[str, Any]) -> dict[str, Any]:
    keys = ("quotas", "pullRequests", "workflowRuns", "workflows", "issueBuckets", "issues", "securitySignals")
    return {**{key: [] for key in keys}, "copilotUsage": copilot}


def _report(head: dict[str, Any], sections: dict[str, Any], metrics: list[Any], warnings: list[str]) -> dict[str, Any]:
    """BootUI ``GitHubDashboardReport``, keys in record order."""
    return {
        "available": True,
        "unavailableReason": None,
        "connected": head["connected"],
        "status": head["status"],
        "message": head["message"],
        "refreshedAt": head["refreshedAt"],
        "repository": head["repository"],
        "credential": head["credential"],
        "metrics": metrics,
        "quotas": sections["quotas"],
        "pullRequests": sections["pullRequests"],
        "workflowRuns": sections["workflowRuns"],
        "workflows": sections["workflows"],
        "issueBuckets": sections["issueBuckets"],
        "issues": sections["issues"],
        "securitySignals": sections["securitySignals"],
        "copilotUsage": sections["copilotUsage"],
        "warnings": list(warnings),
    }


def _last_page(link: str | None) -> int | None:
    """The ``page`` number of the ``rel="last"`` link; only the number is kept, never the link's host or path."""
    for part in (link or "").split(","):
        if 'rel="last"' not in part:
            continue
        start, end = part.find("<"), part.find(">")
        if start < 0 or end <= start:
            return None
        try:
            query = urllib.parse.urlsplit(part[start + 1 : end]).query
        except ValueError:
            return None
        return _query_int(query, "page")
    return None


def _query_int(query: str, name: str) -> int | None:
    for parameter in query.split("&"):
        key, sep, value = parameter.partition("=")
        if not sep or key != name:
            continue
        if not _PAGE_NUMBER.fullmatch(value) or abs(int(value)) > _INT_MAX:
            return None
        return int(value)
    return None


class GitHubApiClient:
    """Implements ``GitHubClientPort``: one bounded, sequential refresh per call, no retry, no redirect."""

    def __init__(
        self,
        settings: SharpitSettings,
        token: Callable[[float], Token | None],
        opener: Opener | None = None,
        *,
        scrub: m.Scrub,
    ) -> None:
        self.settings = settings
        self.scrub = scrub
        self._token = token
        self._opener = opener
        self.timeout = safe_timeout(settings.github_request_timeout)
        self.clock: Callable[[], float] = time.monotonic

    def _open(self) -> Opener:
        if self._opener is None:
            self._opener = no_redirect_opener()
        return self._opener

    def refresh(self, repo: Repository) -> dict[str, Any]:
        refreshed_at = _now_ms()
        host = urllib.parse.urlsplit(repo.api_base_uri).hostname
        if host is None or host.lower() not in {h.lower() for h in self.settings.github_allowed_api_hosts}:
            message = (
                f"GitHub API host {host} is not allowed. Add it to SHARPIT_GITHUB_ALLOWED_API_HOSTS to enable refresh."
            )
            head = self.head(repo, refreshed_at, "BLOCKED", message, None)
            head["credential"] = {"source": "not connected", "authenticated": False, "login": None, "scopes": None}
            return _report(head, _empty_sections(m.unavailable_copilot("GitHub API host is not allowed")), [], [])
        deadline = self.clock() + REFRESH_DEADLINE
        token: Token | None = None
        try:
            # read only once the host is allowed (a blocked host never runs gh), within the refresh deadline
            token = self._token(min(self.timeout, max(0.1, deadline - self.clock())))
            return _Refresh(self, repo, token, deadline).run(refreshed_at)
        except _Failed:
            return self.error(repo, refreshed_at, token, NETWORK_FAILED)
        except Exception:  # noqa: BLE001  # safety net: never a 500, never the exception text (it may hold data)
            return self.error(repo, refreshed_at, token, UNEXPECTED_FAILURE)

    def error(self, repo: Repository, refreshed_at: int, token: Token | None, message: str) -> dict[str, Any]:
        """BootUI ``error``: ``ERROR``, nothing loaded, the fixed message as the only warning."""
        head = self.head(repo, refreshed_at, "ERROR", message, None)
        head["credential"] = _credential(token, None, self.scrub)
        return _report(head, _empty_sections(m.unavailable_copilot(message)), [], [message])

    def head(self, repo: Repository, refreshed_at: int, status: str, message: str | None, node: Any) -> dict[str, Any]:
        connected = status in {"CONNECTED", "PARTIAL", "QUOTA_PROTECTED"}
        return {
            "connected": connected,
            "status": status,
            "message": message,
            "refreshedAt": refreshed_at,
            "repository": m.repository(repo, node, self.scrub),
            "credential": None,
        }

    def send(self, url: str, label: str, api_version: str, token: Token | None, timeout: float) -> _Response:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": api_version,
        }
        if token is not None and token.value.strip():
            headers["Authorization"] = f"Bearer {token.value}"
        if not url.startswith("https://"):  # the detector only builds https API bases; never send a token otherwise
            raise _Failed
        request = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310 (https checked above)
        try:
            with self._open().open(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                response_headers = getattr(response, "headers", None)
                body = bytes(response.read(MAX_BODY_BYTES + 1))
        except urllib.error.HTTPError as error:  # non-2xx, 3xx included (no redirect handler follows it)
            error.close()
            return _Response(error.code, None, error.headers, f"GitHub returned HTTP {error.code} for {label}.")
        except (OSError, ValueError, http.client.HTTPException):  # URLError, timeouts, IncompleteRead...
            raise _Failed from None  # from None: no traceback carries the request or its header
        if len(body) > MAX_BODY_BYTES:
            raise _Failed
        if not 200 <= status < 300:
            return _Response(status, None, response_headers, f"GitHub returned HTTP {status} for {label}.")
        return _Response(status, _parse(body), response_headers, None)


def _reject_constant(name: str) -> Any:
    """``NaN``/``Infinity`` are not JSON; BootUI's Jackson rejects them too."""
    raise ValueError(name)


def _parse_int(digits: str) -> int | float:
    """A JSON integer; one too long for Python's int-digit limit is out of any Jackson range anyway (infinity makes
    ``as_long`` give its default, as Jackson's ``BigIntegerNode.asLong(default)`` does)."""
    return int(digits) if len(digits) <= _MAX_INT_DIGITS else math.inf


def _parse(body: bytes) -> Any:
    if not body.strip():
        return {}
    try:
        return json.loads(body, parse_constant=_reject_constant, parse_int=_parse_int)
    except (ValueError, RecursionError):  # sharpit: BootUI's Jackson 3 throws unchecked here; report ERROR instead
        raise _Failed from None


class _Refresh:
    """One refresh: the call budget, the sections filled so far and the warnings (BootUI ``refresh`` locals)."""

    def __init__(self, client: GitHubApiClient, repo: Repository, token: Token | None, deadline: float) -> None:
        self.client = client
        self.deadline = deadline
        self.settings = client.settings
        self.scrub = client.scrub
        self.repo = repo
        self.token = token
        self.remaining = max(1, self.settings.github_max_api_calls)
        self.warnings: list[str] = []
        self.sections = _empty_sections(m.unavailable_copilot(_QUOTA_COPILOT))
        self.repo_path = f"repos/{m.path_segment(repo.owner)}/{m.path_segment(repo.name)}"

    def get(self, path: str, label: str, api_version: str = GITHUB_API_VERSION) -> _Response:
        if self.remaining <= 0:
            return _Response(
                0, None, None, f"Skipped {label} because the configured GitHub API call budget was reached."
            )
        left = self.deadline - self.client.clock()
        if left <= 0:
            return _Response(0, None, None, f"Skipped {label} because the GitHub refresh time limit was reached.")
        self.remaining -= 1
        url = urllib.parse.urljoin(self.repo.api_base_uri, path)
        return self.client.send(url, label, api_version, self.token, min(self.client.timeout, left))

    def run(self, refreshed_at: int) -> dict[str, Any]:
        rate = self.get("rate_limit", "rate limits")
        credential = _credential(self.token, rate, self.scrub)
        if not rate.success:
            head = self.client.head(self.repo, refreshed_at, "ERROR", rate.message, None)
            head["credential"] = credential
            sections = _empty_sections(m.unavailable_copilot("Rate limits could not be loaded"))
            return _report(head, sections, [], self.warnings)
        self.sections["quotas"].extend(m.rate_limit_quotas(rate.json))
        core = m.core_remaining(rate.json)
        if core is not None and core <= max(0, self.settings.github_quota_safety_threshold):
            self.warnings.append(QUOTA_WARNING)
            head = self.client.head(self.repo, refreshed_at, "QUOTA_PROTECTED", QUOTA_MESSAGE, None)
            head["credential"] = credential
            return _report(head, self.sections, m.metrics(None, self.sections, core), self.warnings)
        node = self._load()
        status, message = ("PARTIAL", PARTIAL) if self.warnings else ("CONNECTED", None)
        head = self.client.head(self.repo, refreshed_at, status, message, node)
        head["credential"] = credential
        return _report(head, self.sections, m.metrics(node, self.sections, core), self.warnings)

    def _load(self) -> Any:
        repo = self.get(self.repo_path, "repository metadata")
        node = repo.json if repo.success else None
        if not repo.success:
            self.warnings.append(repo.message or "")
        s, rp, scrub = self.sections, self.repo_path, self.scrub
        pulls = self._json(
            f"{rp}/pulls?state=open&per_page={_positive(self.settings.github_max_pull_requests, 10)}", "pull requests"
        )
        if pulls is not _MISSING:
            s["pullRequests"] = m.pull_requests(pulls, scrub)
        found = self._json(
            f"{rp}/issues?state=open&per_page={_positive(self.settings.github_max_issues, 25)}", "issues"
        )
        if found is not _MISSING:
            s["issueBuckets"], s["issues"] = m.issue_buckets(found), m.issues(found, scrub)
        runs = self._json(
            f"{rp}/actions/runs?per_page={_positive(self.settings.github_max_workflow_runs, 20)}", "workflow runs"
        )
        if runs is not _MISSING:
            s["workflowRuns"] = m.workflow_runs(runs, scrub)
        flows = self._json(f"{rp}/actions/workflows?per_page=100", "workflows")
        if flows is not _MISSING:
            s["workflows"] = m.workflows(flows, self.repo.html_url, s["workflowRuns"], scrub)
        for label, relative, with_alerts in _SIGNALS:
            self._signal(label, relative, with_alerts)
        self._repo_quota(
            "actions-cache", "Actions cache", "actions/cache/usage", ("Storage", "active_caches_size_in_bytes")
        )
        self._repo_quota(
            "actions-artifacts", "Actions artifacts", "actions/artifacts?per_page=1", ("Count", "total_count")
        )
        self._billing(node)
        s["copilotUsage"] = self._copilot(node)
        return node

    def _json(self, path: str, label: str) -> Any:
        """The body on success; otherwise the warning is recorded and ``_MISSING`` returned."""
        response = self.get(path, label)
        if response.success:
            return response.json
        self.warnings.append(response.message or "")
        return _MISSING

    def _signal(self, label: str, relative: str, with_alerts: bool) -> None:
        response = self.get(f"{self.repo_path}/{relative}", label)
        if not response.success:
            self.sections["securitySignals"].append(m.signal(label, None, response.message, []))
            return
        array = isinstance(response.json, list)
        count = self._alert_count(relative, label, response) if array else 0
        limit = _positive(self.settings.github_max_security_alerts, 50)
        alerts = m.dependabot_alerts(response.json, limit, self.scrub) if with_alerts and array else []
        self.sections["securitySignals"].append(m.signal(label, count, None, alerts))

    def _alert_count(self, relative: str, label: str, first: _Response) -> int:
        first_count = len(first.json)
        last = _last_page(first.header("Link"))
        if last is None or last <= 1:
            return first_count
        # sharpit: BootUI resolves this page without the repos/<owner>/<name> prefix (always a 404); fixed here
        final = self.get(f"{self.repo_path}/{relative}&page={last}", f"{label} final page")
        page = final.json if final.success else None
        if not isinstance(page, list):
            return first_count
        return (last - 1) * _PAGE_SIZE + len(m.items(page))

    def _repo_quota(self, key: str, label: str, relative: str, shape: tuple[str, str]) -> None:
        response = self.get(f"{self.repo_path}/{relative}", label)
        if not response.success:
            self.sections["quotas"].append(m.unavailable_quota(key, label, "repository", response.message))
            return
        category, field = shape
        used = m.nullable(m.as_long(response.json, field, -1))
        self.sections["quotas"].append(m.quota(key, label, category, "repository", (None, used, None)))

    def _owner_is_organization(self, node: Any) -> bool:
        return m.text(m.field(node, "owner"), "type") == _ORGANIZATION

    def _billing(self, node: Any) -> None:
        kind = "orgs" if self._owner_is_organization(node) else "users"
        response = self.get(
            f"{kind}/{m.path_segment(self.repo.owner)}/settings/billing/actions", "Actions billing quota"
        )
        if not response.success:
            self.sections["quotas"].append(
                m.unavailable_quota("actions-minutes", "Actions minutes", "owner", response.message)
            )
            return
        limit = m.as_long(response.json, "included_minutes", -1)
        used = m.as_long(response.json, "total_minutes_used", -1)
        remaining = max(0, limit - used) if limit >= 0 and used >= 0 else None
        row = m.quota(
            "actions-minutes", "Actions minutes", "Billing", "owner", (m.nullable(limit), m.nullable(used), remaining)
        )
        row["percentUsed"] = m.percent(used, limit)
        self.sections["quotas"].append(row)

    def _copilot(self, node: Any) -> dict[str, Any]:
        if not self._owner_is_organization(node):
            return m.unavailable_copilot("Copilot organization metrics are only available for organization owners.")
        path = f"orgs/{m.path_segment(self.repo.owner)}/copilot/metrics/reports/organization-28-day/latest"
        response = self.get(path, "Copilot usage metrics", COPILOT_API_VERSION)
        if response.status == 204:
            summary = "No Copilot usage report data was returned for this organization."
            return m.copilot_usage("NO_DATA", summary, scope="organization", links=0)
        if not response.success:
            return m.unavailable_copilot(response.message)
        links = m.field(response.json, "download_links")
        return m.copilot_usage(
            "AVAILABLE",
            "Latest 28-day Copilot usage report is available.",
            scope="organization",
            start=self.scrub(m.text(response.json, "report_start_day")),
            end=self.scrub(m.text(response.json, "report_end_day")),
            links=len(m.items(links)),
        )


_MISSING = object()
