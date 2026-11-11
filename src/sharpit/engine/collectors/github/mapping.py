"""GitHub REST JSON to BootUI's ``GitHub*`` DTOs (the pure half of BootUI ``GitHubApiClient``, no I/O).

Every string GitHub returns is emitted through ``scrub`` (the context's ``mask_text``), so a secret pasted into a PR
title or label never reaches the panel (proposed deviation P-G1: BootUI shows fetched text verbatim).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any, cast
from urllib.parse import quote

Scrub = Callable[[str | None], str | None]
Json = Any

COPILOT_DOCS = "https://docs.github.com/en/rest/copilot/copilot-usage-metrics"
_THIRTY_DAYS_MS = 30 * 24 * 3600 * 1000
_NOT_FAILED = frozenset({"success", "neutral", "skipped"})
_WORKFLOWS_DIR = ".github/workflows/"
_BADGE = "/badge.svg"
_OPEN_ISSUES = "Open issues"


def field(node: Json, name: str) -> Json:
    """Jackson ``path(name)``: the child of an object, else ``None``."""
    return cast(dict[str, Any], node).get(name) if isinstance(node, dict) else None


def text(node: Json, name: str) -> str | None:
    """BootUI ``text``: a non-blank scalar as a string, else ``None``."""
    value = field(node, name)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return value if isinstance(value, str) and value.strip() else None


def as_long(node: Json, name: str, default: int) -> int:
    """Jackson ``asLong(default)`` for numbers; anything else gives ``default``."""
    value = field(node, name)
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else default


def nullable(value: int) -> int | None:
    return None if value < 0 else value


def instant_ms(value: str | None) -> int | None:
    """``Instant.parse``: an ISO-8601 instant with a zone, as epoch ms; anything else gives ``None``."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000) if parsed.tzinfo is not None else None


def percent(used: int, limit: int) -> int | None:
    """``Math.min(100, Math.round(used * 100.0 / limit))``; Java rounds half up."""
    return min(100, math.floor(used * 100.0 / limit + 0.5)) if limit > 0 and used >= 0 else None


def path_segment(segment: str) -> str:
    """``URLEncoder.encode`` with ``+`` as ``%20``: one URL path segment."""
    return quote(segment, safe="")


def items(node: Json) -> list[Json]:
    return cast(list[Any], node) if isinstance(node, list) else []


def _label(key: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in key.replace("_", " ").split(" ") if word.strip())


def _rate_status(limit: int, remaining: int) -> str:
    if remaining == 0:
        return "EXHAUSTED"
    if limit > 0 and remaining >= 0 and remaining * 100.0 / limit <= 10.0:
        return "LOW"
    return "OK"


def quota(
    key: str,
    label: str,
    category: str,
    scope: str,
    values: tuple[int | None, int | None, int | None] = (None, None, None),
) -> dict[str, Any]:
    limit, used, remaining = values
    return {
        "key": key,
        "label": label,
        "category": category,
        "scope": scope,
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "resetAt": None,
        "percentUsed": None,
        "status": "OK",
        "unavailableReason": None,
    }


def unavailable_quota(key: str, label: str, scope: str, reason: str | None) -> dict[str, Any]:
    return quota(key, label, "Quota", scope) | {"status": "UNAVAILABLE", "unavailableReason": reason}


def rate_limit_quotas(root: Json) -> list[dict[str, Any]]:
    resources = field(root, "resources")
    if not isinstance(resources, dict):
        return []
    quotas: list[dict[str, Any]] = []
    for key, value in cast(dict[str, Any], resources).items():
        limit = as_long(value, "limit", -1)
        remaining = as_long(value, "remaining", -1)
        used = as_long(value, "used", max(0, limit - remaining) if limit >= 0 and remaining >= 0 else -1)
        reset = as_long(value, "reset", -1)
        row = quota(
            key, _label(key), "Rate limit", "credential", (nullable(limit), nullable(used), nullable(remaining))
        )
        row["resetAt"] = reset * 1000 if reset > 0 else None
        row["percentUsed"] = percent(used, limit)
        row["status"] = _rate_status(limit, remaining)
        quotas.append(row)
    return quotas


def core_remaining(root: Json) -> int | None:
    return nullable(as_long(field(field(root, "resources"), "core"), "remaining", -1))


def _labels(node: Json, scrub: Scrub) -> list[str | None]:
    return [scrub(name) for name in (text(label, "name") for label in items(node)) if name is not None]


def pull_requests(root: Json, scrub: Scrub) -> list[dict[str, Any]]:
    return [
        {
            "number": as_long(item, "number", 0),
            "title": scrub(text(item, "title")),
            "author": scrub(text(field(item, "user"), "login")),
            "draft": field(item, "draft") is True,
            "htmlUrl": scrub(text(item, "html_url")),
            "updatedAt": instant_ms(text(item, "updated_at")),
            "reviewDecision": None,
            "checksConclusion": None,
            "labels": _labels(field(item, "labels"), scrub),
        }
        for item in items(root)
    ]


def _actor(run: Json) -> str | None:
    triggering = text(field(run, "triggering_actor"), "login")
    return triggering if triggering is not None else text(field(run, "actor"), "login")


def workflow_runs(root: Json, scrub: Scrub) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for item in items(field(root, "workflow_runs")):
        updated = instant_ms(text(item, "updated_at"))
        started = instant_ms(text(item, "run_started_at"))
        runs.append(
            {
                "id": as_long(item, "id", 0),
                "workflowId": nullable(as_long(item, "workflow_id", -1)),
                "name": scrub(text(item, "name")),
                "displayTitle": scrub(text(item, "display_title")),
                "runNumber": nullable(as_long(item, "run_number", -1)),
                "event": scrub(text(item, "event")),
                "status": scrub(text(item, "status")),
                "conclusion": scrub(text(item, "conclusion")),
                "branch": scrub(text(item, "head_branch")),
                "actor": scrub(_actor(item)),
                "htmlUrl": scrub(text(item, "html_url")),
                "createdAt": instant_ms(text(item, "created_at")),
                "updatedAt": updated,
                "durationMillis": max(0, updated - started) if started is not None and updated is not None else None,
            }
        )
    return runs


def _run_time(run: dict[str, Any]) -> int:
    created = run["createdAt"]
    if created is not None:
        return created
    return run["updatedAt"] or 0


def _latest(runs: Iterable[tuple[object, dict[str, Any]]]) -> dict[object, dict[str, Any]]:
    """``Map.merge`` keeping the current run unless the candidate is strictly newer."""
    latest: dict[object, dict[str, Any]] = {}
    for key, run in runs:
        current = latest.get(key)
        if current is None or _run_time(run) > _run_time(current):
            latest[key] = run
    return latest


def _trim_slash(value: str) -> str:
    return value.removesuffix("/") if value.strip() else ""


def _workflow_url(html_url: str, workflow: Json) -> str | None:
    workflow_path = text(workflow, "path")
    if workflow_path is not None and workflow_path.startswith(_WORKFLOWS_DIR):
        return f"{_trim_slash(html_url)}/actions/workflows/{path_segment(workflow_path.rsplit('/', 1)[-1])}"
    own = text(workflow, "html_url")
    if own is not None:
        return own
    badge = text(workflow, "badge_url")
    if badge is not None and badge.endswith(_BADGE):
        return badge.removesuffix(_BADGE)
    return f"{_trim_slash(html_url)}/actions"


def workflows(root: Json, html_url: str, runs: list[dict[str, Any]], scrub: Scrub) -> list[dict[str, Any]]:
    latest = _latest((run["workflowId"], run) for run in runs if run["workflowId"] is not None)
    rows: list[dict[str, Any]] = []
    for item in items(field(root, "workflows")):
        workflow_id = as_long(item, "id", 0)
        rows.append(
            {
                "id": workflow_id,
                "name": scrub(text(item, "name")),
                "path": scrub(text(item, "path")),
                "state": scrub(text(item, "state")),
                "htmlUrl": scrub(_workflow_url(html_url, item)),
                "latestRun": latest.get(workflow_id),
            }
        )
    return rows


def _issues_only(root: Json) -> list[Json]:
    return [item for item in items(root) if not (isinstance(item, dict) and "pull_request" in item)]


def issue_buckets(root: Json) -> list[dict[str, Any]]:
    if not isinstance(root, list):
        return []
    found = _issues_only(root)
    labeled = sum(1 for item in found if items(field(item, "labels")))
    stale_before = int(time.time() * 1000) - _THIRTY_DAYS_MS
    stale = 0
    for item in found:
        updated = instant_ms(text(item, "updated_at"))
        stale += updated is not None and updated < stale_before
    return [
        {"label": _OPEN_ISSUES, "count": len(found), "tone": "primary"},
        {"label": "With labels", "count": labeled, "tone": "info"},
        {"label": "No label", "count": len(found) - labeled, "tone": "warning"},
        {"label": "Stale 30d+", "count": stale, "tone": "warning" if stale > 0 else "success"},
    ]


def issues(root: Json, scrub: Scrub) -> list[dict[str, Any]]:
    return [
        {
            "number": as_long(item, "number", 0),
            "title": scrub(text(item, "title")),
            "author": scrub(text(field(item, "user"), "login")),
            "htmlUrl": scrub(text(item, "html_url")),
            "createdAt": instant_ms(text(item, "created_at")),
            "updatedAt": instant_ms(text(item, "updated_at")),
            "comments": as_long(item, "comments", 0),
            "labels": _labels(field(item, "labels"), scrub),
        }
        for item in _issues_only(root)
    ]


def dependabot_alerts(root: Json, limit: int, scrub: Scrub) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for item in items(root)[:limit]:
        dependency = field(item, "dependency")
        package = field(dependency, "package")
        advisory = field(item, "security_advisory")
        vulnerability = field(item, "security_vulnerability")
        severity = text(vulnerability, "severity")
        alerts.append(
            {
                "number": as_long(item, "number", 0),
                "state": scrub(text(item, "state")),
                "packageName": scrub(text(package, "name")),
                "ecosystem": scrub(text(package, "ecosystem")),
                "manifestPath": scrub(text(dependency, "manifest_path")),
                "severity": scrub(severity if severity is not None else text(advisory, "severity")),
                "ghsaId": scrub(text(advisory, "ghsa_id")),
                "cveId": scrub(text(advisory, "cve_id")),
                "summary": scrub(text(advisory, "summary")),
                "vulnerableVersionRange": scrub(text(vulnerability, "vulnerable_version_range")),
                "firstPatchedVersion": scrub(text(field(vulnerability, "first_patched_version"), "identifier")),
                "htmlUrl": scrub(text(item, "html_url")),
                "createdAt": instant_ms(text(item, "created_at")),
                "updatedAt": instant_ms(text(item, "updated_at")),
            }
        )
    return alerts


def signal(label: str, count: int | None, reason: str | None, alerts: list[dict[str, Any]]) -> dict[str, Any]:
    status = "UNAVAILABLE" if reason is not None else "AVAILABLE"
    return {"label": label, "status": status, "count": count, "unavailableReason": reason, "alerts": alerts}


def copilot_usage(status: str, summary: str, reason: str | None = None, **report: Any) -> dict[str, Any]:
    return {
        "status": status,
        "scope": report.get("scope"),
        "summary": summary,
        "reportStartDay": report.get("start"),
        "reportEndDay": report.get("end"),
        "downloadLinkCount": report.get("links"),
        "documentationUrl": COPILOT_DOCS,
        "unavailableReason": reason,
    }


def unavailable_copilot(reason: str | None) -> dict[str, Any]:
    return copilot_usage("UNAVAILABLE", "Copilot usage report unavailable", reason)


def _failures(runs: list[dict[str, Any]]) -> int:
    def scope(run: dict[str, Any]) -> str:
        if run["workflowId"] is None:
            return f"run:{run['id']}"
        return f"workflow:{run['workflowId']}:branch:{(run['branch'] or '').strip()}"

    latest = _latest((scope(run), run) for run in runs).values()
    return sum(
        1 for run in latest if (run["conclusion"] or "").strip() and run["conclusion"].lower() not in _NOT_FAILED
    )


def _core_tone(quotas: list[dict[str, Any]]) -> str:
    core = next((q for q in quotas if q["key"] == "core"), None)
    if core is None:
        return "success"
    return {"EXHAUSTED": "danger", "LOW": "warning"}.get(core["status"], "success")


def _copilot_metric(usage: dict[str, Any]) -> dict[str, Any]:
    if usage["status"] == "AVAILABLE":
        start, end = usage["reportStartDay"], usage["reportEndDay"]
        detail = "Organization report links available" if start is None or end is None else f"{start} to {end}"
        return metric("Copilot usage", "Available", detail, "info")
    if usage["status"] == "NO_DATA":
        return metric("Copilot usage", "No data", usage["summary"], "secondary")
    return metric("Copilot usage", "Unavailable", usage["summary"], "secondary")


def metric(label: str, value: str, detail: str | None, tone: str) -> dict[str, Any]:
    return {"label": label, "value": value, "detail": detail, "tone": tone}


def metrics(repo: Json, sections: dict[str, Any], core: int | None) -> list[dict[str, Any]]:
    """The five headline cards; ``sections`` holds the report's lists and its ``copilotUsage``."""
    failures = _failures(sections["workflowRuns"])
    bucket = next((b for b in sections["issueBuckets"] if b["label"] == _OPEN_ISSUES), None)
    open_issues = str(bucket["count"]) if bucket is not None else str(as_long(repo, "open_issues_count", 0))
    return [
        metric("Open pull requests", str(len(sections["pullRequests"])), "Bounded live queue", "primary"),
        metric(_OPEN_ISSUES, open_issues, "Issues returned by this refresh", "info"),
        metric(
            "Workflow failures",
            str(failures),
            "Latest run per workflow/branch",
            "danger" if failures > 0 else "success",
        ),
        metric(
            "Core quota remaining",
            "unknown" if core is None else str(core),
            "GitHub REST core resource",
            _core_tone(sections["quotas"]),
        ),
        _copilot_metric(sections["copilotUsage"]),
    ]


def repository(repo: Any, node: Json, scrub: Scrub) -> dict[str, Any]:
    """``GitHubRepositoryDto`` from the detected repository and, when loaded, the repository JSON."""

    def flag(name: str) -> bool | None:
        value = field(node, name)
        return value if isinstance(value, bool) else None

    def count(name: str) -> int | None:
        return nullable(as_long(node, name, -1)) if field(node, name) is not None else None

    html = text(node, "html_url")
    return {
        "owner": repo.owner,
        "name": repo.name,
        "fullName": repo.full_name,
        "host": repo.host,
        "apiBaseUrl": repo.api_base_uri,
        "htmlUrl": scrub(html) if html is not None else repo.html_url,
        "defaultBranch": scrub(text(node, "default_branch")),
        "localBranch": repo.local_branch,
        "upstreamBranch": repo.upstream_branch,
        "visibility": scrub(text(node, "visibility")),
        "privateRepository": flag("private"),
        "fork": flag("fork"),
        "archived": flag("archived"),
        "pushedAt": instant_ms(text(node, "pushed_at")),
        "stars": count("stargazers_count"),
        "forks": count("forks_count"),
        "watchers": count("subscribers_count"),
        "openIssues": count("open_issues_count"),
        "latestRelease": None,
    }
