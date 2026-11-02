from __future__ import annotations

import pytest


def test_write_baseline_refused_on_partial_xdist_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_x(): pass\ndef test_y(): pass")
    result = pytester.runpytest_subprocess(
        "-n",
        "2",
        "-k",
        "x",
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-write-baseline=baseline.json",
        "-q",
    )
    assert result.ret == 4
    output = result.stdout.str() + result.stderr.str()
    assert "refusing to write baseline: partial run" in output
    assert not (pytester.path / "baseline.json").exists()
