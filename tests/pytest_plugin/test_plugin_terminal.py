from __future__ import annotations

import json

import pytest

# an app whose rest-api findings include LOW (RAPI-DTO-002): notes under the default HIGH gate
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
CHECKED_GATES = (
    "sharpit checked: test-runtime gates (sharpit.max-queries, sharpit.n-plus-one, sharpit.exception, "
    "sharpit.swallowed-exception, sharpit.unbounded-read)"
)


def test_summary_names_every_runtime_gate_when_a_swallow_is_found(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_swallow():
            try:
                raise TypeError('example')
            except Exception:
                pass
        """
    )

    result = pytester.runpytest_inprocess("--sharpit", "--sharpit-no-advisors", "-q", "-n", "0")

    assert result.ret == 1
    assert "sharpit: sharpit.swallowed-exception:" in result.stdout.str()
    assert _checked_line(result) == CHECKED_GATES


@pytest.mark.parametrize(("workers", "unattached", "missing"), [(0, 1, 0), (2, 0, 0), (2, 1, 0), (2, 2, 0), (2, 1, 1)])
def test_summary_reports_unattached_swallowed_capture(
    pytester: pytest.Pytester, workers: int, unattached: int, missing: int
) -> None:
    pytester.makeconftest(
        f"""
        import pytest
        from sharpit.pytest_plugin.swallowed import allocator

        def pytest_configure(config):
            worker = getattr(config, 'workerinput', {{}}).get('workerid')
            if {unattached} == 2 or ({unattached} == 1 and ({workers} == 0 or worker == 'gw0')):
                patch = pytest.MonkeyPatch()
                patch.setattr(allocator, 'claim', lambda: None)
                config.add_cleanup(patch.undo)

        @pytest.hookimpl(tryfirst=True, optionalhook=True)
        def pytest_testnodedown(node, error):
            if {missing} and node.gateway.id == 'gw1':
                node.workeroutput.pop('sharpit')
        """
    )
    pytester.makepyfile("def test_first(): pass\ndef test_second(): pass")

    result = pytester.runpytest_inprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q", "-n", str(workers)
    )

    checked = _checked_line(result)
    if unattached:
        note = (
            f"sharpit.swallowed-exception not attached on {unattached} of {workers or 1} processes: "
            "sys.monitoring tool ids 3 and 4 are in use"
        )
        assert note in checked
        assert checked == f"{CHECKED_GATES}. {note}"
    else:
        assert checked == CHECKED_GATES


def _checked_line(result: pytest.RunResult) -> str:
    return next((line for line in result.stdout.lines if line.startswith("sharpit checked:")), "")


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
    assert "  RAPI-DTO-002: 3" in stdout
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


# --- #68: the summary names each swallowing clause once, with the tests it failed -------------------------------


def _swallowed_finding(location: str, node: str, *, double: bool = False) -> dict[str, object]:
    note = "a test double raised this, so this code path did not run; " if double else ""
    return {
        "ruleId": "sharpit.swallowed-exception",
        "target": location,
        "testNodeId": node,
        "message": f"TypeError swallowed by a broad except clause at {location} (neither re-raised nor logged); {note}"
        f"identity {location}:TypeError",
    }


def _summary(findings: list[dict[str, object]]) -> list[str]:
    from sharpit.pytest_plugin import terminal

    out = _Lines()
    terminal._write_swallowed(out, findings)  # pyright: ignore[reportPrivateUsage]
    return out.lines


def test_swallowed_findings_group_by_clause_most_tests_first() -> None:
    findings = [
        *(_swallowed_finding("c.py:9", f"t::c{i}") for i in range(3)),
        *(_swallowed_finding("a.py:3", f"t::a{i}") for i in range(3)),
        _swallowed_finding("b.py:5", "t::a0"),
    ]

    assert _summary(findings) == [
        "swallowed exceptions: 3 clauses, 6 tests",
        "  a.py:3: 3 tests",
        "  c.py:9: 3 tests",
        "  b.py:5: 1 test",
    ]


def test_thirteen_clauses_and_ninety_five_tests_are_capped_at_five_locations() -> None:
    findings = [_swallowed_finding(f"app/m{i % 13:02}.py:7", f"tests/test_x.py::test_{i}") for i in range(95)]

    lines = _summary(findings)

    assert lines[:1] == ["swallowed exceptions: 13 clauses, 95 tests"]
    assert len(lines) == 6


def test_a_clause_counts_a_test_once_whatever_its_attempts() -> None:
    findings = [_swallowed_finding("a.py:3", "t::a"), _swallowed_finding("a.py:3", "t::a")]

    assert _summary(findings) == ["swallowed exceptions: 1 clause, 1 test", "  a.py:3: 1 test"]


def test_a_real_raise_clears_a_test_double_note_for_the_same_clause() -> None:
    findings = [
        _swallowed_finding("a.py:3", "t::a", double=True),
        _swallowed_finding("a.py:3", "t::a"),
    ]

    assert _summary(findings) == ["swallowed exceptions: 1 clause, 1 test", "  a.py:3: 1 test"]


def test_swallowed_clause_order_uses_numeric_line_numbers() -> None:
    findings = [_swallowed_finding("a.py:10", "t::ten"), _swallowed_finding("a.py:9", "t::nine")]

    assert _summary(findings)[1:] == ["  a.py:9: 1 test", "  a.py:10: 1 test"]


def test_swallowed_clause_list_is_capped_at_five() -> None:
    findings = [_swallowed_finding(f"a.py:{line}", f"t::{line}") for line in range(8)]

    assert len(_summary(findings)) == 6


def test_a_clause_only_test_doubles_reached_says_so() -> None:
    findings = [_swallowed_finding("a.py:3", f"t::a{i}", double=True) for i in range(2)]

    assert _summary(findings) == [
        "swallowed exceptions: 1 clause, 2 tests",
        "  a.py:3: 2 tests, a test double raised this, so this code path did not run",
    ]


def test_a_clause_a_test_double_reached_in_some_tests_counts_them() -> None:
    findings = [_swallowed_finding("a.py:3", "t::a0", double=True), _swallowed_finding("a.py:3", "t::a1")]

    assert _summary(findings) == [
        "swallowed exceptions: 1 clause, 2 tests",
        "  a.py:3: 2 tests, 1 raised by a test double",
    ]


def test_other_rules_are_not_summarised_as_swallowed() -> None:
    other = {"ruleId": "sharpit.n-plus-one", "target": "SELECT 1", "testNodeId": "t::a", "message": "m"}

    assert _summary([other]) == []


def test_swallowed_findings_display_reason_in_terminal_summary() -> None:
    finding = _swallowed_finding("a.py:3", "t::a0")
    finding["reason"] = "fallback for mock client"

    lines = _summary([finding])

    assert lines == [
        "swallowed exceptions: 1 clause, 1 test",
        "  a.py:3: 1 test, reason: fallback for mock client",
    ]
