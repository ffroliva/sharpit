from scripts.ci.sonar_ratchet import verdict


def test_pull_request_with_any_new_issue_fails():
    assert verdict(1, None)[0] is False
    assert verdict(0, None)[0] is True


def test_main_must_sit_exactly_at_the_baseline():
    assert verdict(11, 10)[0] is False
    assert verdict(10, 10)[0] is True


def test_main_below_the_baseline_fails_until_the_baseline_is_lowered():
    """A fix that leaves the baseline high would let a later change add an issue back unnoticed."""
    ok, message = verdict(9, 10)
    assert ok is False
    assert "lower sonar-baseline.txt to 9" in message
