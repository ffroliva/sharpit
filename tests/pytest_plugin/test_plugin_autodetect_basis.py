"""The report says when the application was found through the modules the tests imported (#67)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from sharpit.engine.advisors.findings import AdvisorRun
from sharpit.pytest_plugin.apps import reconcile_workers
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


def test_subset_that_imports_no_app_names_the_imports_basis_and_the_stable_options(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(test_plain="def test_plain():\n    pass")

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    reason = str(_rest_run(pytester)["reason"])
    assert "the selected tests imported" in reason
    assert "--sharpit-app module:attr" in reason
    assert "--sharpit-require-app" in reason
    assert "the same result on any selection" in reason
    assert "the selected tests imported" in result.stdout.str()


def test_imported_app_report_and_notice_state_the_detection_basis(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(appmod=_APP, test_single="import appmod\n\ndef test_uses_app():\n    assert appmod.app\n")

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    app = _rest_run(pytester)["apps"][0]
    assert app["app"] == "appmod:app"
    assert app["evidence"].get("detectedFrom") == "imports"
    assert "using app appmod:app, detected from the modules the tests imported" in result.stdout.str()


def test_several_imported_apps_name_the_candidates_and_their_source(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        first_app=_APP,
        second_app=_APP,
        test_both="import first_app\nimport second_app\n\ndef test_both():\n    assert first_app.app\n",
    )

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    expected = "several apps found in the modules the tests imported (first_app:app, second_app:app); pass --sharpit-app"
    assert expected in str(_rest_run(pytester)["reason"])
    assert expected in result.stdout.str()


def test_explicit_app_says_nothing_about_autodetection(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(appmod=_APP, test_single="import appmod\n\ndef test_uses_app():\n    assert appmod.app\n")

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=appmod:app", "--sharpit-report=report.json", "-q"
    )

    app = _rest_run(pytester)["apps"][0]
    assert app["app"] == "appmod:app"
    assert "detectedFrom" not in app["evidence"]
    assert "detected from" not in result.stdout.str()


def _detected(worker: str) -> SimpleNamespace:
    run = AdvisorRun("rest-api", "PASSED", (), {"detectedFrom": "imports"}, None, "pkg:app")
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


def test_notice_names_the_workers_that_saw_the_app() -> None:
    evidence = {"detectedFrom": "imports", "detectedBy": ["gw0", "gw1"]}
    data = {"advisors": [{"advisor": "rest-api", "apps": [{"app": "pkg:app", "evidence": evidence}]}]}

    notice = app_notice(["pkg:app"], False, data)

    assert notice == (
        "sharpit: using app pkg:app, detected from the modules the tests imported in gw0, gw1"
        " (pass --sharpit-app to choose)"
    )
