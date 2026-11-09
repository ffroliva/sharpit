from __future__ import annotations

import json

import pytest

# an app whose rest-api findings are LOW (RAPI-DTO-002) and INFO (RAPI-DOC-001): notes under the default HIGH gate
NOTES_APP = """
from fastapi import FastAPI
app = FastAPI()
@app.get('/items')
def items(): return []
@app.post('/getUsers')
def get_users(): return []
@app.delete('/items/{item_id}')
def delete(item_id: int): return {}
"""


def test_verbose_keeps_advisor_notes(pytester: pytest.Pytester) -> None:
    from sharpit.pytest_plugin.options import resolve

    assert resolve(pytester.parseconfig()).verbose is False
    assert resolve(pytester.parseconfig("--sharpit-verbose")).verbose is True
    assert resolve(pytester.parseconfig("-vv")).verbose is True
    pytester.makeini("""
        [pytest]
        sharpit_verbose = true
    """)
    assert resolve(pytester.parseconfig()).verbose is True
    pytester.makepyfile(appmod=NOTES_APP, test_notes="def test_ok(): pass")

    result = pytester.runpytest_inprocess(
        "--sharpit", "--sharpit-app=appmod:app", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    stdout = result.stdout.str()
    assert "  RAPI-DOC-001: 3" in stdout
    assert "advisor notes in" not in stdout


def test_gate_failure_still_printed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod=NOTES_APP,
        test_gate="""
        import sqlite3
        def test_n_plus_one():
            db = sqlite3.connect(':memory:')
            db.execute('CREATE TABLE owners (id INTEGER)')
            for _ in range(6):
                db.execute('SELECT * FROM owners WHERE id = 1').fetchall()
        """,
    )

    result = pytester.runpytest_inprocess(
        "--sharpit", "--sharpit-app=appmod:app", "--sharpit-fail-on=LOW", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 1
    stdout = result.stdout.str()
    assert "status: fail" in stdout
    assert "  sharpit.n-plus-one: 1" in stdout
    assert "  RAPI-DTO-002: 3" in stdout
    assert "  RAPI-DOC-001" not in stdout
    data = json.loads((pytester.path / "report.json").read_text())
    notes = [f for f in data["findings"] if f["severity"] == "INFO"]
    assert f"sharpit: {len(notes)} advisor notes in report.json" in stdout


def test_summary_says_what_the_run_checked(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(appmod=NOTES_APP, test_notes="def test_ok(): pass")

    result = pytester.runpytest_inprocess("--sharpit", "--sharpit-app=appmod:app", "--sharpit-report=report.json", "-q")

    stdout = result.stdout.str()
    checked = next((line for line in stdout.splitlines() if line.startswith("sharpit checked:")), "")
    not_checked = next((line for line in stdout.splitlines() if line.startswith("sharpit did not check:")), "")
    assert "sharpit.n-plus-one" in checked
    assert "REST API" in checked
    assert "security" in not_checked
    assert "routes and SQL your tests did not exercise" in not_checked
    assert "security testing" in not_checked


def test_summary_advisor_lists_follow_assessor_registry(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        """
        import sharpit.pytest_plugin.apps as apps
        apps.advisor_assessors = lambda: []
        """
    )
    pytester.makepyfile(appmod=NOTES_APP, test_notes="def test_ok(): pass")

    result = pytester.runpytest_inprocess("--sharpit", "--sharpit-app=appmod:app", "--sharpit-report=report.json", "-q")

    stdout = result.stdout.str()
    checked = next((line for line in stdout.splitlines() if line.startswith("sharpit checked:")), "")
    not_checked = next((line for line in stdout.splitlines() if line.startswith("sharpit did not check:")), "")
    assert "REST API" not in checked
    assert "REST API" in not_checked


def test_summary_never_lists_what_ran_as_not_checked(pytester: pytest.Pytester) -> None:
    """The test-runtime gates run in every session, so the 'did not check' line must not name them too."""
    pytester.makepyfile(appmod=NOTES_APP, test_notes="def test_ok(): pass")

    result = pytester.runpytest_inprocess("--sharpit", "--sharpit-app=appmod:app", "--sharpit-report=report.json", "-q")

    not_checked = next(
        (line for line in result.stdout.str().splitlines() if line.startswith("sharpit did not check:")), ""
    )
    assert "test-runtime" not in not_checked


def test_gate_failure_counted_whatever_fail_on(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        test_gate="""
        import sqlite3
        def test_n_plus_one():
            db = sqlite3.connect(':memory:')
            db.execute('CREATE TABLE owners (id INTEGER)')
            for _ in range(6):
                db.execute('SELECT * FROM owners WHERE id = 1').fetchall()
        """
    )

    result = pytester.runpytest_inprocess(
        "--sharpit",
        "--sharpit-fail-on=CRITICAL",
        "--sharpit-report=report.json",
        "--sharpit-junit=report.xml",
        "-q",
    )

    stdout = result.stdout.str()
    junit = (pytester.path / "report.xml").read_text()
    assert "  sharpit.n-plus-one: 1" in stdout
    assert "advisor notes in" not in stdout
    assert 'type="sharpit.n-plus-one"' in junit


class _Lines:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_line(self, line: str) -> None:
        self.lines.append(line)

    def starting(self, prefix: str) -> str:
        return next((line for line in self.lines if line.startswith(prefix)), "")


def _coverage(apps: list[dict[str, str]], monkeypatch: pytest.MonkeyPatch) -> _Lines:
    from types import SimpleNamespace

    from sharpit.pytest_plugin import terminal

    monkeypatch.setattr(terminal, "advisor_assessors", lambda: [("rest-api", None)])
    out = _Lines()
    state = SimpleNamespace(options=SimpleNamespace(advisors=True))
    terminal._write_coverage(out, state, {"advisors": [{"advisor": "rest-api", "apps": apps}]})  # pyright: ignore[reportPrivateUsage]
    return out


@pytest.mark.parametrize("status", ["SKIPPED", "UNKNOWN"])
def test_an_advisor_whose_app_was_not_assessed_is_not_checked(status: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Council delta 2026-11-08: a skipped or unloadable app was reported as 'checked'. Only an assessed app counts."""
    out = _coverage([{"status": status}], monkeypatch)
    assert "REST API" not in out.starting("sharpit checked:")


def test_the_error_fallback_never_lists_the_test_runtime_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    from sharpit.pytest_plugin import terminal

    def broken() -> list[object]:
        raise RuntimeError("registry unreadable")

    monkeypatch.setattr(terminal, "advisor_assessors", broken)
    out = _Lines()
    from types import SimpleNamespace

    terminal._write_coverage(out, SimpleNamespace(options=SimpleNamespace(advisors=True)), {"advisors": []})  # pyright: ignore[reportPrivateUsage]
    assert "test-runtime" not in out.starting("sharpit did not check:")
