"""The report says when the application was found through the modules the tests imported (#67)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.pytest_plugin.apps import bare_app_run, reconcile_workers
from sharpit.pytest_plugin.terminal import app_notice

_APP = """
from fastapi import FastAPI
app = FastAPI()
@app.get('/items')
def items():
    return []
"""


def _rest_run(pytester: pytest.Pytester) -> dict[str, Any]:
    data = json.loads((pytester.path / "report.json").read_text())
    return next(run for run in data["advisors"] if run["advisor"] == "rest-api")


def test_the_collected_test_files_decide_whether_the_application_is_found(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod=_APP,
        test_plain="def test_plain():\n    pass",
        test_uses_app="import appmod\n\ndef test_uses_app():\n    assert appmod.app\n",
    )

    subset = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q", "test_plain.py")
    skipped = _rest_run(pytester)
    full = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q", "test_uses_app.py")
    assessed = _rest_run(pytester)

    assert skipped["status"] == "SKIPPED"
    assert "among the modules the tests imported" in str(skipped["reason"])
    assert "among the modules the tests imported" in subset.stdout.str()
    assert assessed["status"] == "PASSED"
    assert assessed["apps"][0]["app"] == "appmod:app"
    assert assessed["apps"][0]["evidence"].get("detectedFrom") == "imports"
    assert "using app appmod:app, detected from the modules the tests imported" in full.stdout.str()


def _detected(worker: str, **evidence: Any) -> SimpleNamespace:
    run = AdvisorRun("rest-api", "PASSED", (), {"detectedFrom": "imports", **evidence}, None, "pkg:app")
    return SimpleNamespace(worker=worker, advisor_runs=[run])


def test_controller_merge_names_the_workers_that_saw_the_app() -> None:
    blind = SimpleNamespace(
        worker="gw2",
        advisor_runs=[AdvisorRun("rest-api", "SKIPPED", (), {"autodetect": True}, "no application found", None)],
    )
    parts = [_detected("gw1"), blind, _detected("gw0")]

    reconcile_workers(parts, ["pkg:app"], False)

    seen = [run.evidence.get("detectedBy") for part in parts for run in part.advisor_runs]
    assert seen == [["gw0", "gw1"], ["gw0", "gw1"]]


def test_controller_merge_orders_workers_naturally_and_shares_no_list() -> None:
    parts = [_detected(worker) for worker in ("gw10", "gw2", "gw1")]

    reconcile_workers(parts, ["pkg:app"], False)

    lists = [part.advisor_runs[0].evidence.get("detectedBy") for part in parts]
    assert lists[0] == ["gw1", "gw2", "gw10"]
    assert lists[0] is not lists[1]


def test_a_bare_app_is_detected_from_imports_and_counted_among_the_workers() -> None:
    bare = bare_app_run("pkg:app", False)
    parts = [_detected("gw0"), SimpleNamespace(worker="gw1", advisor_runs=[bare])]

    reconcile_workers(parts, ["pkg:app"], False)

    assert bare.evidence.get("detectedFrom") == "imports"
    assert parts[1].advisor_runs[0].evidence.get("detectedBy") == ["gw0", "gw1"]


def test_notice_counts_the_workers_that_saw_the_app() -> None:
    evidence = {"detectedFrom": "imports", "detectedBy": ["gw0", "gw1"]}
    data = {"advisors": [{"advisor": "rest-api", "apps": [{"app": "pkg:app", "evidence": evidence}]}]}

    notice = app_notice(["pkg:app"], False, data)

    assert notice == (
        "sharpit: using app pkg:app, detected from the modules the tests imported on 2 xdist workers"
        " (pass --sharpit-app to choose)"
    )
