"""``SharpitHandle``, what ``install()`` returns: its own module, so ``install`` and ``adapter`` share it, no cycle."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.context import SharpitContext
from sharpit.fastapi.capture import wiring_of
from sharpit.settings import SharpitSettings

_Lifespan = Callable[[Any], AbstractAsyncContextManager[Any]]


@dataclass
class SharpitHandle:
    settings: SharpitSettings
    activation: ActivationStatus
    context: SharpitContext
    original_lifespan: _Lifespan

    def uninstall_capture(self) -> None:
        """Detach every capture hook, as lifespan shutdown does (for tests and apps run without lifespan)."""
        if (wiring := wiring_of(self.context)) is not None:
            wiring.detach(self.context)
