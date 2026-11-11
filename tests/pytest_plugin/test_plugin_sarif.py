"""``--sharpit-sarif PATH`` end to end: written once, by the xdist controller, with every worker's findings."""

from __future__ import annotations

import json

import pytest

_SQL = "import sqlite3\nconn = sqlite3.connect(':memory:')\nfor _ in range(5): conn.execute('SELECT 1').fetchone()"
_RECORD_WRITES = (
    "import os\n"
    "import sharpit.engine.testsession.sarif as sarif\n"
    "_write = sarif.write_sarif\n"
    "def _recording(*args, **kwargs):\n"
    "    with open('sarif-writes.txt', 'a') as log:\n"
    "        log.write(os.environ.get('PYTEST_XDIST_WORKER', 'controller') + '\\n')\n"
    "    return _write(*args, **kwargs)\n"
    "sarif.write_sarif = _recording\n"
)


def _tests(*names: str) -> str:
    body = _SQL.replace("\n", "\n    ")
    return "\n\n".join(f"def {name}():\n    {body}" for name in names)


def test_xdist_controller_alone_writes_the_sarif_file(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)  # this outer worker's id would leak into the controller
    pytester.makeconftest(_RECORD_WRITES)
    pytester.makepyfile(test_one=_tests("test_a"), test_two=_tests("test_b"))

    pytester.runpytest_subprocess(
        "-n",
        "2",
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "--sharpit-sarif=out/sharpit.sarif",
        "-q",
    )

    log = pytester.path / "sarif-writes.txt"
    assert log.is_file(), "no process wrote the SARIF file"
    assert log.read_text().splitlines() == ["controller"]
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    sarif = json.loads((pytester.path / "out" / "sharpit.sarif").read_text(encoding="utf-8"))
    fingerprints = [r["partialFingerprints"]["sharpitFingerprint/v1"] for r in sarif["runs"][0]["results"]]
    assert sorted(fingerprints) == sorted(f["fingerprint"] for f in report["findings"])
    assert len(fingerprints) == 2


def test_no_sarif_option_writes_no_sarif_file(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_RECORD_WRITES)
    pytester.makepyfile(_tests("test_a"))

    # a subprocess: the conftest replaces ``sarif.write_sarif`` and would leak into this worker in-process
    pytester.runpytest_subprocess("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q")

    assert not (pytester.path / "sarif-writes.txt").exists()


def test_sarif_write_failure_is_in_the_json_report(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_clean(): pass")
    (pytester.path / "taken.sarif").mkdir()  # a directory where the file should go: the write fails

    pytester.runpytest_inprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-report=report.json", "--sharpit-sarif=taken.sarif", "-q"
    )

    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert any("SARIF write failed" in reason for reason in report["unknownReasons"])
    assert any("SARIF write failed" in warning for warning in report["warnings"])
