"""Sonar ratchet: a pull request may add no Sonar issue, and the baseline tracks main's open issues, only downwards.

Run after the SonarCloud scan (which waits for the quality gate, so the analysis is processed):
    python scripts/ci/sonar_ratchet.py --pull-request 12
    python scripts/ci/sonar_ratchet.py --branch main
Lower `sonar-baseline.txt` in the same commit that fixes issues; it may only go down. main above the baseline fails.
main below it passes (the merge that fixed issues could not know main's new count), and every pull request then fails
until it lowers the baseline to main's count, so the slack never outlives one merge and main never turns red.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = "ffroliva_sharpit"
BASELINE = Path(__file__).resolve().parents[2] / "sonar-baseline.txt"


def _lower(open_issues: int, baseline: int) -> str:
    below = f"main has {open_issues} open Sonar issues, below the baseline of {baseline}"
    return f"{below}: lower sonar-baseline.txt to {open_issues}"


def verdict(open_issues: int, baseline: int) -> tuple[bool, str]:
    """main: only an issue count above the baseline fails."""
    if open_issues > baseline:
        return False, f"{open_issues} open Sonar issues on main, above the baseline of {baseline}"
    if open_issues < baseline:
        return True, f"{_lower(open_issues, baseline)} (the next pull request must)"
    return True, f"{open_issues} open Sonar issues, at the baseline"


def pull_request_verdict(new_issues: int, main_open: int, baseline: int) -> tuple[bool, str]:
    """A pull request adds no issue and carries a baseline no higher than main's count (lower: it fixes some)."""
    if new_issues:
        return False, f"this pull request adds {new_issues} Sonar issue(s); fix them before merging"
    if main_open < baseline:
        return False, _lower(main_open, baseline)
    return True, "no new Sonar issues; the baseline is current"


def open_issue_count(scope: dict[str, str]) -> int:
    query = urllib.parse.urlencode({"componentKeys": PROJECT, "resolved": "false", "ps": 1, **scope})
    request = urllib.request.Request(f"https://sonarcloud.io/api/issues/search?{query}")
    if token := os.environ.get("SONAR_TOKEN"):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:  # fixed https host, scope from CI arguments
        return int(json.load(response)["total"])


def _baseline() -> int:
    return int(BASELINE.read_text().strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pull-request", type=int)
    target.add_argument("--branch")
    args = parser.parse_args(argv)
    if args.pull_request is not None:
        new_issues = open_issue_count({"pullRequest": str(args.pull_request)})
        ok, message = pull_request_verdict(new_issues, open_issue_count({"branch": "main"}), _baseline())
    elif args.branch != "main":  # the baseline counts main's issues; a release/** push only refreshes its analysis
        ok, message = True, f"{args.branch}: no baseline (only main is ratcheted; its pull requests add no issue)"
    else:
        ok, message = verdict(open_issue_count({"branch": args.branch}), _baseline())
    print(message if ok else f"::error::{message}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
