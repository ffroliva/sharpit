"""Fail a pull request whose commits lack a Signed-off-by trailer of their author (Developer Certificate of Origin).

Runs from the dco workflow on `pull_request_target`, so the pull request is data only: this script reads the commit list
through the GitHub API (`gh api`) and never fetches or runs the head. Merge commits and Dependabot commits are exempt.
The environment carries GH_TOKEN, REPO (`owner/name`) and PR_NUMBER. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any, NamedTuple

BOT_LOGIN = "dependabot[bot]"
MISSING = "missing Signed-off-by"
MISMATCH = "Signed-off-by does not match the commit author"
REPAIR = "git rebase --signoff <base> && git push --force-with-lease"
TRAILER = re.compile(r"Signed-off-by: (?P<name>.+) <(?P<email>[^<>]*)>")
REMEDIATION = re.compile(
    r"I, (?P<name>.+) <(?P<email>[^<>]*)>, hereby add my Signed-off-by to this commit: (?P<sha>[0-9a-f]{7,40})"
)
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SUBJECT_WIDTH = 100


class Failure(NamedTuple):
    sha: str
    subject: str
    reason: str


def _is_exempt(commit: dict[str, Any]) -> bool:
    author = commit.get("author") or {}
    return len(commit.get("parents") or []) > 1 or author.get("login") == BOT_LOGIN


def _reason(commit: dict[str, Any]) -> str | None:
    """Why the commit fails, or None when one trailer names its author."""
    meta = commit["commit"]
    author = meta["author"]
    trailers = [m for line in meta["message"].splitlines() if (m := TRAILER.fullmatch(line.rstrip()))]
    if not trailers:
        return MISSING
    for trailer in trailers:
        if trailer["name"] == author["name"] and trailer["email"].casefold() == author["email"].casefold():
            return None
    return MISMATCH


def _same_person(commit: dict[str, Any], name: str, email: str) -> bool:
    author = commit["commit"]["author"]
    return name == author["name"] and email.casefold() == author["email"].casefold()


def _remediated(commits: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(name, email, sha) of each remediation line a validly signed commit of that same person carries."""
    found: list[tuple[str, str, str]] = []
    for commit in commits:
        if _is_exempt(commit) or _reason(commit):
            continue
        for line in commit["commit"]["message"].splitlines():
            m = REMEDIATION.fullmatch(line.rstrip())
            if m and _same_person(commit, m["name"], m["email"]):
                found.append((m["name"], m["email"], m["sha"]))  # noqa: PERF401
    return found


def check_commits(commits: list[dict[str, Any]]) -> list[Failure]:
    """The commits of a pull request (GitHub API JSON) that fail the sign-off rule, with the reason.

    A commit also passes when a validly signed commit of its author, in the same pull request, carries the line
    `I, <name> <email>, hereby add my Signed-off-by to this commit: <sha>` naming it.
    """
    failures: list[Failure] = []
    remediated = _remediated(commits)
    for commit in commits:
        if _is_exempt(commit):
            continue
        if reason := _reason(commit):
            if any(commit["sha"].startswith(sha) and _same_person(commit, n, e) for n, e, sha in remediated):
                continue
            subject = (commit["commit"]["message"].splitlines() or [""])[0]
            failures.append(Failure(commit["sha"], subject, reason))
    return failures


def _printable(text: str) -> str:
    """The text with every control character replaced by a space (a subject is author-controlled log output)."""
    return "".join(char if char.isprintable() else " " for char in text)


def _parse_pages(output: str) -> list[dict[str, Any]]:
    """The commits in `gh api --paginate` output: one JSON array per page, concatenated."""
    decoder = json.JSONDecoder()
    commits: list[dict[str, Any]] = []
    position = 0
    while position < len(output):
        if output[position].isspace():
            position += 1
            continue
        page, position = decoder.raw_decode(output, position)
        if not isinstance(page, list):
            raise ValueError("the commit list is not a JSON array")
        commits.extend(page)
    return commits


def _gh(*args: str) -> str:
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=False, shell=False)
    if result.returncode != 0:
        raise ValueError(f"gh api failed: {result.stderr.strip()[:200]}")
    return result.stdout


def _fetch(repo: str, number: str) -> list[dict[str, Any]]:
    """The pull request's commits. The commits endpoint stops at 250: a short list falls back to the compare range."""
    commits = _parse_pages(_gh("--paginate", f"repos/{repo}/pulls/{number}/commits"))
    info = json.loads(
        _gh(f"repos/{repo}/pulls/{number}", "--jq", "{commits: .commits, base: .base.sha, head: .head.sha}")
    )
    if len(commits) != info["commits"]:
        compare = f"repos/{repo}/compare/{info['base']}...{info['head']}"
        commits = _parse_pages(_gh("--paginate", compare, "--jq", ".commits"))
    if len(commits) != info["commits"]:
        raise ValueError(f"read {len(commits)} of {info['commits']} commits")
    return commits


def main() -> int:
    repo = os.environ.get("REPO", "")
    number = os.environ.get("PR_NUMBER", "")
    if not REPO_PATTERN.fullmatch(repo) or not number.isdecimal():
        print("REPO must be owner/name and PR_NUMBER a number", file=sys.stderr)
        return 2
    try:
        commits = _fetch(repo, number)
    except (ValueError, KeyError, TypeError) as error:
        print(f"cannot read the pull request commits: {error}", file=sys.stderr)
        return 2
    failures = check_commits(commits)
    if not failures:
        print(f"{len(commits)} commit(s) checked; every one is signed off or exempt")
        return 0
    print(f"{len(failures)} commit(s) lack a valid Signed-off-by trailer of their author:")
    for failure in failures:
        print(f"{failure.sha[:7]} {_printable(failure.subject)[:SUBJECT_WIDTH]} - {failure.reason}")
    print("To repair, sign off each commit and push again (<base> is the pull request's base branch):")
    print(f"  {REPAIR}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
