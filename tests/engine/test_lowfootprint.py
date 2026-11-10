import sharpit.engine.capture as capture


def test_suspend_and_resume_are_idempotent() -> None:
    assert hasattr(capture, "HookRegistry"), "capture hooks need a registry before low-footprint can suspend them"
    from sharpit.engine.lowfootprint import LowFootprintService

    class Hook:
        name = "test"

        def __init__(self) -> None:
            self.attached = True

        def suspend(self) -> None:
            self.attached = False

        def resume(self) -> None:
            self.attached = True

    hook = Hook()
    registry = capture.HookRegistry()
    registry.register(hook)
    service = LowFootprintService(registry)
    service.suspend()
    service.suspend()
    assert hook.attached is False
    service.resume()
    service.resume()
    assert hook.attached is True


def test_concurrent_suspend_and_resume_keep_each_hook_in_balance() -> None:
    """Review R3: two threads toggling at once never suspend (or resume) a hook twice in a row."""
    import sys
    import threading
    import time

    from sharpit.engine.lowfootprint import LowFootprintService

    class Hook:
        name = "counted"

        def __init__(self) -> None:
            self.depth = 0  # suspends minus resumes: 0 or 1 when balanced
            self.seen: set[int] = set()

        def suspend(self) -> None:
            time.sleep(0)  # yield inside the check-then-act window
            self.depth += 1
            self.seen.add(self.depth)

        def resume(self) -> None:
            time.sleep(0)
            self.depth -= 1
            self.seen.add(self.depth)

    hook = Hook()
    registry = capture.HookRegistry()
    registry.register(hook)
    service = LowFootprintService(registry)
    start = threading.Barrier(2)

    def toggle() -> None:
        start.wait()
        for _ in range(1000):
            service.suspend()
            service.resume()

    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=toggle) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(interval)
    assert hook.seen <= {0, 1}, f"a hook was suspended or resumed twice in a row: depths {sorted(hook.seen)}"
    assert hook.depth == 0
    assert service.status()["enabled"] is False
