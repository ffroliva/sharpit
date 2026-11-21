from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.needs_sqlalchemy


def test_n_plus_one_fails_on_flask_sqlalchemy(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(flask_app=Path(__file__).with_name("flask_app.py").read_text())
    pytester.makepyfile(
        """
        from flask_app import create_app
        unfixed = create_app()
        fixed = create_app(fixed=True)

        def test_n_plus_one():
            assert unfixed.test_client().get('/authors').status_code == 200

        def test_fixed_query():
            assert fixed.test_client().get('/authors').status_code == 200
        """
    )
    result = pytester.runpytest_inprocess(
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-max-queries=3",
        "--sharpit-report=report.json",
        "-q",
    )

    assert result.ret == 1
    assert "sharpit: sharpit.n-plus-one" in result.stdout.str()
    assert "sharpit: sharpit.max-queries" in result.stdout.str()
    report = json.loads((pytester.path / "report.json").read_text())
    assert report["status"] == "fail"
    n_plus_one = next(f for f in report["findings"] if f["ruleId"] == "sharpit.n-plus-one")
    assert "Author.books lazy-loaded 6 times" in n_plus_one["message"]
    assert "FROM book" in n_plus_one["message"]
    budget = next(f for f in report["findings"] if f["ruleId"] == "sharpit.max-queries")
    assert budget["observed"] == 7
    tests = {test["nodeId"].split("::")[-1]: test for test in report["tests"]}
    assert tests["test_n_plus_one"]["phases"]["call"]["queries"] == 7
    assert tests["test_fixed_query"]["phases"]["call"]["queries"] == 2
    assert tests["test_fixed_query"]["findings"] == []
    assert report["totals"]["unattributed"] == 0
