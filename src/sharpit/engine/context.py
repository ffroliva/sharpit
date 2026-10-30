"""Per-install state shared by the adapter, collectors and (later) tools; framework-free so the engine can use it."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.masking import Masker
from sharpit.engine.singleflight import SingleFlight
from sharpit.engine.spi import AppIntrospector
from sharpit.settings import SharpitSettings


@dataclass(eq=False)
class SharpitContext:
    settings: SharpitSettings
    activation: ActivationStatus
    introspector: AppIntrospector
    token: str | None = None
    profiles: tuple[str, ...] = ()
    app_settings: tuple[object, ...] = ()
    caller_module: str | None = None  # ``__name__`` of the module that called install(): the default config scan root
    single_flight: SingleFlight = field(default_factory=SingleFlight)
    installed_at: float = field(default_factory=time.monotonic)
    startup_time_ms: int | None = None
    masker: Masker = field(init=False)
    _cache: dict[str, Any] = field(default_factory=dict[str, Any], init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.masker = Masker(self.settings.expose_values, self.settings.mask_secrets)

    def lazy[T](self, key: str, factory: Callable[[], T]) -> T:
        """Memoised ``factory()``; one lock, so a factory runs at most once per key (re-entrant)."""
        with self._lock:
            if key not in self._cache:
                self._cache[key] = factory()
            return cast("T", self._cache[key])
