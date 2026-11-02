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


def test_report_only_options_leave_the_sharpit_report_unchanged(pytester: pytest.Pytester) -> None:
    # review minor 5: under --sharpit too, the inert options change neither the exit status nor the report verdict
    import json

    pytester.makepyfile("def test_one(): assert True")
    common = ["-q", "-p", "no:cacheprovider", "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown"]
    plain = pytester.runpytest(*common, "--sharpit-report=plain.json")
    with_options = pytester.runpytest(
        *common,
        "--sharpit-report=options.json",
        "--sharpit-report-only",
        "--sharpit-baseline",
        "baseline.json",
        "--sharpit-write-baseline",
    )
    before = json.loads((pytester.path / "plain.json").read_text())
    after = json.loads((pytester.path / "options.json").read_text())
    assert with_options.ret == plain.ret
    assert after["status"] == before["status"]
    assert after["findings"] == before["findings"]
    assert after["gates"] == before["gates"]
    assert not (pytester.path / "baseline.json").exists()
