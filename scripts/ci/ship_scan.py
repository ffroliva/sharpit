"""Check scan evidence for a draft release pull request into main."""

import json
import re
import subprocess
import sys


class Refused(Exception):
    """A release condition lacks passing evidence."""


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def gh(path, *, paginate=False):
    command = ["gh", "api", "--method", "GET"]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    command.append(f"repos/ffroliva/sharpit/{path}")
    return subprocess.run(command, capture_output=True, check=True, encoding="utf-8", timeout=120).stdout


def array(value):
    if not isinstance(value, list):
        raise ValueError("expected an array")
    return value


def rows(path, field=None):
    pages = array(json.loads(gh(path, paginate=True)))
    if not pages:
        raise ValueError("missing response page")
    return [row for page in pages for row in array(page if field is None else page[field])]


def sha(value):
    if not re.fullmatch("[0-9a-f]{40}", value):
        raise ValueError("invalid commit SHA")
    return value


def snapshot(number):
    pr = json.loads(gh(f"pulls/{number}"))
    require(pr["state"] == "open", "pull request is closed")
    require(pr["draft"] is True, "pull request must be a draft")
    require(pr["base"]["ref"] == "main", "base must be main")
    head = sha(pr["head"]["sha"])
    base = sha(json.loads(gh("git/ref/heads/main"))["object"]["sha"])
    return head, base


def codeql(number, head):
    ref = f"ref=refs/pull/{number}/head"
    latest = {}
    for item in sorted(rows(f"code-scanning/analyses?{ref}"), key=lambda a: (a["created_at"], a["id"])):
        if item["tool"]["name"] == "CodeQL" and item["commit_sha"] == head:
            latest[item["category"]] = item["error"]
    require(
        latest.keys() == {"/language:actions", "/language:javascript-typescript", "/language:python"},
        "unexpected or missing CodeQL analysis category",
    )
    require(all(error == "" for error in latest.values()), "CodeQL analysis reported an error")
    require(not rows(f"code-scanning/alerts?{ref}&state=open"), "open code scanning alert")


def successful(row, name):
    require(row["status"] == "completed", f"{name} is incomplete")
    require(row["conclusion"] == "success", f"{name} did not succeed")


def check_codeql(head):
    checks = rows(f"commits/{head}/check-runs?filter=all", "check_runs")
    matches = [
        c
        for c in checks
        if c["name"] == "CodeQL" and c["app"]["slug"] == "github-advanced-security" and c["head_sha"] == head
    ]
    require(matches, "missing CodeQL check run")
    successful(max(matches, key=lambda c: c["id"]), "CodeQL check")


def check_base_history(number):
    for entry in rows(f"issues/{number}/events"):
        event = entry["event"]
        if not isinstance(event, str) or not event:
            raise ValueError("missing issue event name")
        require(event != "base_ref_changed", "PR base changed: close the PR and open a new draft against main")


def matches_run(run, head, number):
    return (
        run["path"] == ".github/workflows/ci.yml"
        and run["event"] == "pull_request"
        and run["head_sha"] == head
        and any(p["number"] == number and p["base"]["ref"] == "main" for p in array(run["pull_requests"]))
    )


def sonar(number, head):
    runs = rows(f"actions/workflows/ci.yml/runs?event=pull_request&head_sha={head}", "workflow_runs")
    matches = [run for run in runs if matches_run(run, head, number)]
    require(matches, "missing associated pull request CI run")
    run = max(matches, key=lambda r: r["run_number"])
    jobs = rows(f"actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", "jobs")
    matching = [job for job in jobs if job["name"] == "sonar"]
    require(len(matching) == 1, "expected one sonar job")
    successful(matching[0], "sonar job")
    name = "Sonar ratchet (no new issues; main never above sonar-baseline.txt)"
    steps = [s for s in array(matching[0]["steps"]) if s["name"] == name]
    require(len(steps) == 1, "expected one Sonar ratchet step")
    require(steps[0]["conclusion"] == "success", "Sonar ratchet did not succeed")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) != 1 or not re.fullmatch("[1-9][0-9]*", args[0]):
            raise ValueError("expected a positive pull request number")
        number = int(args[0])
        head, base = snapshot(number)
        check_base_history(number)
        comparison = json.loads(gh(f"compare/{base}...{head}"))
        require(type(comparison["behind_by"]) is int and comparison["behind_by"] == 0, "head is behind main")
        codeql(number, head)
        check_codeql(head)
        sonar(number, head)
        require(snapshot(number) == (head, base), "release head or main changed during checks")
    except Refused as exc:
        print(exc, file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Unable to verify release: {exc.stderr or exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError, RecursionError, ValueError, TypeError, KeyError) as exc:
        print(f"Unable to verify release: {exc}", file=sys.stderr)
        return 2
    print(f"Verified head {head} and base {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
