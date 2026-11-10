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


def test_a_hook_that_raises_on_suspend_does_not_strand_the_others() -> None:
    """Review: BootUI's LowFootprintService catches each component's failure and carries on; resume still works."""
    from sharpit.engine.lowfootprint import LowFootprintService

    class Hook:
        def __init__(self, name: str, *, fails: bool = False) -> None:
            self.name = name
            self.fails = fails
            self.attached = True

        def suspend(self) -> None:
            if self.fails:
                raise RuntimeError("boom")
            self.attached = False

        def resume(self) -> None:
            self.attached = True

    hooks = [Hook("a"), Hook("bad", fails=True), Hook("c")]
    registry = capture.HookRegistry()
    for hook in hooks:
        registry.register(hook)
    service = LowFootprintService(registry)
    status = service.suspend()
    assert [hook.attached for hook in hooks] == [False, True, False]
    assert status["enabled"] is True
    assert status["failures"] == ["bad: RuntimeError: boom"]
    status = service.resume()
    assert [hook.attached for hook in hooks] == [True, True, True]
    assert status["enabled"] is False


def test_low_footprint_discards_each_hook_once_and_disable_does_not_restore_data() -> None:
    # ported: LowFootprintServiceTests.enablingTwiceAndDisablingTwiceChangeNothingTheSecondTime
    from sharpit.engine.lowfootprint import LowFootprintService

    class BufferedHook:
        name = "buffered"

        def __init__(self) -> None:
            self.items = ["diagnostic"]
            self.discards = 0

        def suspend(self) -> None:
            pass

        def resume(self) -> None:
            pass

        def discard(self) -> None:
            self.discards += 1
            self.items.clear()

    class LegacyHook:
        name = "no-discard"

        def suspend(self) -> None:
            pass

        def resume(self) -> None:
            pass

    registry = capture.HookRegistry()
    buffered = BufferedHook()
    registry.register(buffered)
    registry.register(LegacyHook())
    service = LowFootprintService(registry)

    service.suspend()
    service.suspend()

    assert buffered.items == []
    assert buffered.discards == 1
    service.resume()
    assert buffered.items == []
