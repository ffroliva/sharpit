import pytest

from sharpit.engine.collectors.vulns.deadline import DEFAULT_SCAN_TIMEOUT, ScanDeadline


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_request_budget_uses_request_timeout_until_deadline_caps_it():
    clock = FakeClock()
    deadline = ScanDeadline(10.0, clock)
    first = deadline.request_budget(4.0)
    assert first.timeout == 4.0
    assert first.capped_by_deadline is False
    clock.now = 7.0
    last = deadline.request_budget(4.0)
    assert last.timeout == 3.0
    assert last.capped_by_deadline is True


def test_expired_deadline_raises_from_request_budget():
    clock = FakeClock()
    deadline = ScanDeadline(2.0, clock)
    clock.now = 2.0
    with pytest.raises(TimeoutError, match="OSV scan deadline exceeded"):
        deadline.request_budget(1.0)


@pytest.mark.parametrize("timeout", [None, 0.0, -1.0])
def test_invalid_scan_timeout_uses_sixty_seconds(timeout: float | None):
    clock = FakeClock()
    deadline = ScanDeadline(timeout, clock)
    clock.now = DEFAULT_SCAN_TIMEOUT - 0.1
    assert deadline.check_expired() is False
    clock.now = DEFAULT_SCAN_TIMEOUT
    assert deadline.check_expired() is True
