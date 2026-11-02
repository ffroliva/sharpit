"""Lane F review round 1 (review.md findings 1-3): regression tests, each red before its fix."""

from __future__ import annotations

import pytest

from fastapi import FastAPI
from sharpit import install


def _type_error(models: object) -> str | None:
    try:
        install(FastAPI(), enabled="ON", show_banner=False, models=models)
    except TypeError as exc:
        return str(exc)
    return None


@pytest.mark.parametrize("models", ["Base", b"Base", {"Base": 1}], ids=["str", "bytes", "mapping"])
def test_models_hook_rejects_a_string(models: object) -> None:
    message = _type_error(models)
    assert message == f"models must be a model class or an iterable of models, not {type(models).__name__}"


def test_report_only_with_baseline_exits_zero_and_writes_the_report(pytester: pytest.Pytester) -> None:
    import json

    pytester.makepyfile("def test_one(): assert True")
    common = ["-q", "-p", "no:cacheprovider", "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown"]
    pytester.runpytest_subprocess(*common, "--sharpit-write-baseline=baseline.json")
    assert (pytester.path / "baseline.json").exists()
    result = pytester.runpytest_subprocess(
        *common, "--sharpit-report=options.json", "--sharpit-report-only", "--sharpit-baseline=baseline.json"
    )
    report = json.loads((pytester.path / "options.json").read_text())
    assert result.ret == 0
    assert report["mode"] == "report-only"
    assert report["baseline"]["new"] == 0
