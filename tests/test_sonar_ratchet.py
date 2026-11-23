import pytest
from scripts.ci import sonar_ratchet
from scripts.ci.sonar_ratchet import pull_request_verdict, verdict


def test_pull_request_with_any_new_issue_fails():
    assert pull_request_verdict(1, main_open=10, baseline=10)[0] is False
    assert pull_request_verdict(0, main_open=10, baseline=10)[0] is True


def test_pull_request_fails_while_main_sits_below_the_baseline():
    """A merge that fixed issues leaves the baseline stale; the next pull request lowers it, so main never turns red."""
    ok, message = pull_request_verdict(0, main_open=9, baseline=10)
    assert ok is False
    assert "lower sonar-baseline.txt to 9" in message


def test_pull_request_may_lower_the_baseline_ahead_of_its_own_fixes():
    assert pull_request_verdict(0, main_open=10, baseline=8)[0] is True


def test_main_above_the_baseline_fails():
    assert verdict(11, 10)[0] is False
    assert verdict(10, 10)[0] is True


def test_main_below_the_baseline_passes_with_a_warning():
    """The fixing merge cannot know main's new count; the next pull request is held to it instead."""
    ok, message = verdict(9, 10)
    assert ok is True
    assert "lower sonar-baseline.txt to 9" in message


def test_a_pull_request_reads_its_own_new_issues_and_mains_open_count(monkeypatch: pytest.MonkeyPatch) -> None:
    queried: list[dict[str, str]] = []

    def spy(scope: dict[str, str]) -> int:
        queried.append(scope)
        return 0 if "pullRequest" in scope else 1

    monkeypatch.setattr(sonar_ratchet, "open_issue_count", spy)

    rc = sonar_ratchet.main(["--pull-request", "12"])

    assert queried == [{"pullRequest": "12"}, {"branch": "main"}]
    assert rc == 1


def test_a_release_branch_push_is_not_held_to_mains_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """sonar-baseline.txt counts main's open issues; a release/** push only refreshes the base analysis."""
    queried: list[dict[str, str]] = []

    def spy(scope: dict[str, str]) -> int:
        queried.append(scope)
        return 0

    monkeypatch.setattr(sonar_ratchet, "open_issue_count", spy)

    rc = sonar_ratchet.main(["--branch", "release/0.6.0"])

    assert queried == []
    assert rc == 0
