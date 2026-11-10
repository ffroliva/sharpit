"""Low-footprint control for registered capture hooks."""

from __future__ import annotations

import threading

from sharpit.engine.capture import HookRegistry


class LowFootprintService:
    def __init__(self, registry: HookRegistry) -> None:
        self.registry = registry
        self.enabled = False
        self._lock = threading.Lock()  # suspend/resume check-then-act: two callers never toggle a hook twice

    def suspend(self) -> dict[str, object]:
        with self._lock:
            if not self.enabled:
                self.registry.suspend()
                self.enabled = True
            return self.status()

    def resume(self) -> dict[str, object]:
        with self._lock:
            if self.enabled:
                self.registry.resume()
                self.enabled = False
            return self.status()

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "hooks": [hook.name for hook in self.registry.hooks()],
            "failures": list(self.registry.failures),
        }
