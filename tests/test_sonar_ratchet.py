from scripts.ci.sonar_ratchet import verdict


def test_pull_request_with_any_new_issue_fails():
    assert verdict(1, None)[0] is False
    assert verdict(0, None)[0] is True


def test_master_above_baseline_fails_and_at_or_below_passes():
    assert verdict(11, 10)[0] is False
    assert verdict(10, 10)[0] is True
    ok, message = verdict(9, 10)
    assert ok is True
    assert "lower sonar-baseline.txt" in message
