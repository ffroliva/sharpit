from scripts.pytest_speed.check import _verdict


def test_zero_baseline_is_flagged_after_a_significant_rise():
    assert _verdict(1.0, 0.0, 1.0, None, 2.0, 0.0, None) == "flagged"
