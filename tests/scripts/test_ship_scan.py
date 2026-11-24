"""Release gate responses derived from the public evidence on pull request 298."""

import json
import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from _load import load_script

scan = load_script("scripts/ci/ship_scan.py")


@pytest.fixture
def evidence(monkeypatch):
    data = json.loads(Path(__file__).with_name("ship_scan_298.json").read_text(encoding="utf-8"))
    pr = data["pr"]
    pr.update(state="open", draft=True)
    head = pr["head"]["sha"]
    base = pr["base"]["sha"]
    run = data["run"]
    run.update(pull_requests=[{"number": 298, "base": {"ref": "main"}}], run_attempt=2)
    ref = "ref=refs/pull/298/head"
    main_ref = {"object": {"sha": base}}
    replies = {
        "pr": pr,
        "final_pr": deepcopy(pr),
        "main": main_ref,
        "final_main": deepcopy(main_ref),
        "compare": {"behind_by": 0},
        "analyses": [data["analyses"][:1], data["analyses"][1:]],
        "alerts": [[], []],
        "events": [[{"event": "labeled"}], []],
        "checks": [{"check_runs": []}, {"check_runs": [data["check"]]}],
        "runs": [{"workflow_runs": []}, {"workflow_runs": [run]}],
        "jobs": [{"jobs": []}, {"jobs": [data["job"]]}],
    }
    replies["older_jobs"] = deepcopy(replies["jobs"])
    routes = {
        "issues/298/events": ["events"],
        "pulls/298": ["pr", "final_pr"],
        "git/ref/heads/main": ["main", "final_main"],
        f"compare/{base}...{head}": ["compare"],
        f"code-scanning/analyses?{ref}": ["analyses"],
        f"code-scanning/alerts?{ref}&state=open": ["alerts"],
        f"commits/{head}/check-runs?filter=all": ["checks"],
        f"actions/workflows/ci.yml/runs?event=pull_request&head_sha={head}": ["runs"],
        "actions/runs/1/attempts/2/jobs": ["older_jobs"],
        f"actions/runs/{run['id']}/attempts/1/jobs": ["older_jobs"],
        f"actions/runs/{run['id']}/attempts/2/jobs": ["jobs"],
    }

    def respond(path, *, paginate=False):
        key = routes[path].pop(0)
        value = replies[key]
        assert paginate == (key in {"events", "analyses", "alerts", "checks", "runs", "jobs", "older_jobs"})
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, str) else json.dumps(value)

    monkeypatch.setattr(scan, "gh", respond)
    return replies


def test_verified(evidence, capsys):
    assert scan.main(["298"]) == 0
    out = capsys.readouterr().out
    assert evidence["pr"]["head"]["sha"] in out
    assert evidence["main"]["object"]["sha"] in out


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("pr.state", "closed"),
        ("pr.draft", False),
        ("pr.base.ref", "develop"),
        ("compare.behind_by", 1),
        ("analyses.0", []),
        ("analyses.0.0.category", "/extra"),
        ("analyses.0.0.commit_sha", "old"),
        ("analyses.0.0.tool.name", "other"),
        ("analyses.0.0.error", "failed"),
        ("checks.1.check_runs", []),
        ("checks.1.check_runs.0.status", "queued"),
        ("checks.1.check_runs.0.conclusion", "neutral"),
        ("checks.1.check_runs.0.conclusion", "skipped"),
        ("checks.1.check_runs.0.conclusion", "failure"),
        ("checks.1.check_runs.0.app.slug", "other"),
        ("checks.1.check_runs.0.name", "other"),
        ("checks.1.check_runs.0.head_sha", "old"),
        ("runs.1.workflow_runs.0.event", "push"),
        ("runs.1.workflow_runs.0.path", "other"),
        ("runs.1.workflow_runs.0.pull_requests", []),
        ("runs.1.workflow_runs.0.pull_requests", [{"number": 9}]),
        ("runs.1.workflow_runs.0.head_sha", "old"),
        ("jobs.1.jobs", []),
        ("jobs.1.jobs.0.name", "other"),
        ("jobs.1.jobs.0.steps.0.name", "other"),
        ("jobs.1.jobs.0.status", "queued"),
        ("jobs.1.jobs.0.conclusion", "failure"),
        ("jobs.1.jobs.0.steps", []),
        ("jobs.1.jobs.0.steps.0.conclusion", "skipped"),
        ("jobs.1.jobs.0.steps.0.conclusion", "failure"),
        ("alerts.1", [{"state": "open"}]),
        ("final_pr.head.sha", "f" * 40),
        ("final_pr.base.ref", "dev"),
        ("final_main.object.sha", "a" * 40),
        ("final_pr.state", "closed"),
        ("final_pr.draft", False),
    ],
)
def test_refuses(evidence, path, value, capsys):
    parts = [int(p) if p.isdigit() else p for p in path.split(".")]
    parent = evidence
    for key in parts[:-1]:
        parent = parent[key]
    parent[parts[-1]] = value
    assert scan.main(["298"]) == 1, path
    assert capsys.readouterr().err.strip()


@pytest.mark.parametrize(
    "reply",
    [
        OSError("gh unavailable"),
        subprocess.CalledProcessError(1, ["gh"], stderr="rate limited"),
        subprocess.TimeoutExpired(["gh"], 120),
        "{",
        {},
    ],
)
def test_unreadable(evidence, reply, capsys):
    evidence["pr"] = reply
    assert scan.main(["298"]) == 2
    message = capsys.readouterr().err.strip()
    assert message
    if isinstance(reply, subprocess.CalledProcessError):
        assert reply.stderr in message


@pytest.mark.parametrize("paginate", [False, True])
def test_gh_transport(monkeypatch, paginate):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout="payload"))
    monkeypatch.setattr(scan.subprocess, "run", run)
    assert scan.gh("pulls/298", paginate=paginate) == "payload"
    flags = ["--paginate", "--slurp"] if paginate else []
    run.assert_called_once_with(
        ["gh", "api", "--method", "GET", *flags, "repos/ffroliva/sharpit/pulls/298"],
        capture_output=True,
        check=True,
        encoding="utf-8",
        timeout=120,
    )


@pytest.mark.parametrize("argv", [[], ["0"], ["-1"], ["x"], ["1", "2"]])
def test_invalid(argv, capsys):
    assert scan.main(argv) == 2
    assert capsys.readouterr().err.strip()


def test_newest_check(evidence):
    checks = evidence["checks"][1]["check_runs"]
    checks.append(dict(checks[0], id=checks[0]["id"] + 1, conclusion="failure"))
    assert scan.main(["298"]) == 1


def test_newest_run(evidence):
    runs = evidence["runs"][1]["workflow_runs"]
    runs.insert(0, dict(runs[0], run_number=995, id=1))
    evidence["jobs"][1]["jobs"].clear()
    assert scan.main(["298"]) == 1


def test_extra_category(evidence):
    analyses = evidence["analyses"][0]
    analyses.append(dict(analyses[0], category="/extra"))
    assert scan.main(["298"]) == 1


def test_newest_analysis(evidence):
    analyses = evidence["analyses"][0]
    analyses.append(dict(analyses[0], id=1, created_at="2020-01-01T00:00:00Z", error="old failure"))
    assert scan.main(["298"]) == 0


def test_older_attempt_success(evidence):
    evidence["jobs"][1]["jobs"][0]["steps"][0]["conclusion"] = "skipped"
    assert scan.main(["298"]) == 1


@pytest.mark.parametrize(
    ("field", "reply"), [("analyses", []), ("alerts", [{}]), ("main", {"object": {"sha": "invalid"}})]
)
def test_invalid_response(evidence, field, reply):
    evidence[field] = reply
    assert scan.main(["298"]) == 2


def test_invalid_final_sha(evidence, capsys):
    evidence["final_main"]["object"]["sha"] = "invalid"
    assert scan.main(["298"]) == 2
    assert "invalid commit SHA" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["job", "step"])
def test_ambiguous_sonar_evidence(evidence, kind):
    jobs = evidence["jobs"][1]["jobs"]
    entries = jobs if kind == "job" else jobs[0]["steps"]
    entries.append(deepcopy(entries[0]))
    assert scan.main(["298"]) == 1


def test_deep_json_exits_two(evidence):
    evidence["pr"] = RecursionError("response nested too deeply")
    try:
        status = scan.main(["298"])
    except RecursionError:
        status = "uncaught RecursionError"
    assert status == 2


@pytest.mark.parametrize(("association", "expected"), [({"ref": "release/1"}, 1), ({}, 2)])
def test_run_base(evidence, association, expected):
    evidence["runs"][1]["workflow_runs"][0]["pull_requests"][0]["base"] = association
    assert scan.main(["298"]) == expected


def test_changed_base_history(evidence, capsys):
    evidence["events"][1].append({"event": "base_ref_changed"})
    assert scan.main(["298"]) == 1
    assert "close the PR and open a new draft against main" in capsys.readouterr().err


@pytest.mark.parametrize("events", [OSError("unavailable"), [[{}]], [[{"event": None}]], "broken"])
def test_unreadable_events(evidence, events):
    evidence["events"] = events
    assert scan.main(["298"]) == 2
