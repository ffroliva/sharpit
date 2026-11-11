"""Low-footprint control for registered capture hooks."""

from __future__ import annotations

import threading
import time

from sharpit.engine.capture import HookRegistry


class LowFootprintService:
    def __init__(self, registry: HookRegistry) -> None:
        self.registry = registry
        self.enabled = False
        self.since_epoch_millis: int | None = None
        self._lock = threading.Lock()  # suspend/resume check-then-act: two callers never toggle a hook twice

    def suspend(self) -> dict[str, object]:
        return self.suspend_with_transition()[0]

    def suspend_with_transition(self) -> tuple[dict[str, object], bool]:
        with self._lock:
            changed = not self.enabled
            if changed:
                self.enabled = True
                self.since_epoch_millis = int(time.time() * 1000)
                self.registry.suspend()
                self.registry.discard()
            status = self.status()
        return status, changed

    def resume(self) -> dict[str, object]:
        with self._lock:
            if self.enabled:
                self.registry.resume()
                self.enabled = False
                self.since_epoch_millis = None
            return self.status()

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "hooks": [hook.name for hook in self.registry.hooks()],
            "failures": list(self.registry.failures),
        }
