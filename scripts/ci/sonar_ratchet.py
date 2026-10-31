"""Sonar ratchet: a pull request may add no Sonar issue, and master may never hold more open issues than the baseline.

Run after the SonarCloud scan (which waits for the quality gate, so the analysis is processed):
    python scripts/ci/sonar_ratchet.py --pull-request 12
    python scripts/ci/sonar_ratchet.py --branch master
Lower `sonar-baseline.txt` in the same commit that fixes issues; it may only go down.
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


def verdict(open_issues: int, baseline: int | None) -> tuple[bool, str]:
    """baseline None means a pull request: any issue it adds fails."""
    if baseline is None:
        if open_issues:
            return False, f"this pull request adds {open_issues} Sonar issue(s); fix them before merging"
        return True, "no new Sonar issues"
    if open_issues > baseline:
        return False, f"{open_issues} open Sonar issues on master, above the baseline of {baseline}"
    if open_issues < baseline:
        return True, f"{open_issues} open Sonar issues, below the baseline of {baseline}: lower sonar-baseline.txt"
    return True, f"{open_issues} open Sonar issues, at the baseline"


def open_issue_count(scope: dict[str, str]) -> int:
    query = urllib.parse.urlencode({"componentKeys": PROJECT, "resolved": "false", "ps": 1, **scope})
    request = urllib.request.Request(f"https://sonarcloud.io/api/issues/search?{query}")
    if token := os.environ.get("SONAR_TOKEN"):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:  # fixed https host, scope from CI arguments
        return int(json.load(response)["total"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pull-request", type=int)
    target.add_argument("--branch")
    args = parser.parse_args(argv)
    if args.pull_request is not None:
        ok, message = verdict(open_issue_count({"pullRequest": str(args.pull_request)}), None)
    else:
        ok, message = verdict(open_issue_count({"branch": args.branch}), int(BASELINE.read_text().strip()))
    print(message if ok else f"::error::{message}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
