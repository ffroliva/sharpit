"""Fail a pull request whose commits lack a Signed-off-by trailer of their author (Developer Certificate of Origin).

Runs from the dco workflow on `pull_request_target`, so the pull request is data only: this script reads the commit list
through the GitHub API (`gh api`) and never fetches or runs the head. Merge commits and Dependabot commits are exempt.
The environment carries GH_TOKEN, REPO (`owner/name`) and PR_NUMBER. Standard library only.
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Any, NamedTuple

BOT_LOGIN = "dependabot[bot]"
MISSING = "missing Signed-off-by"
MISMATCH = "Signed-off-by does not match the commit author"
REPAIR = "git rebase --signoff <base> && git push --force-with-lease"
TRAILER = re.compile(r"Signed-off-by: (?P<name>.+) <(?P<email>[^<>]*)>")
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


def check_commits(commits: list[dict[str, Any]]) -> list[Failure]:
    """The commits of a pull request (GitHub API JSON) that fail the sign-off rule, with the reason."""
    failures: list[Failure] = []
    for commit in commits:
        if _is_exempt(commit):
            continue
        if reason := _reason(commit):
            subject = (commit["commit"]["message"].splitlines() or [""])[0]
            failures.append(Failure(commit["sha"], subject, reason))
    return failures


def main() -> int:
    out = subprocess.run(["gh", "api", "--paginate", "x"], capture_output=True, text=True, check=False).stdout
    print(out)
    return 3


if __name__ == "__main__":
    sys.exit(main())
