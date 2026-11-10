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
