"""Per-install state shared by the adapter, collectors and (later) tools; framework-free so the engine can use it."""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture import CaptureState
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
    engines: tuple[object, ...] = ()  # install(engines=...): seeds the engine registry (Task 5)
    health_checks: Mapping[str, Callable[[], object]] = field(default_factory=dict[str, Callable[[], object]])
    context_id: str = field(default_factory=lambda: secrets.token_hex(8))
    capture: CaptureState = field(default_factory=CaptureState)
    masker: Masker = field(init=False)
    _cache: dict[str, Any] = field(default_factory=dict[str, Any], init=False, repr=False)
    _locks: dict[str, threading.RLock] = field(default_factory=dict[str, threading.RLock], init=False, repr=False)
    _locks_guard: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.masker = Masker(
            self.settings.expose_values,
            self.settings.mask_secrets,
            self.settings.authentication_token,
            capture_parameters=self.settings.sql_trace_capture_parameters,
        )

    def peek(self, key: str) -> object | None:
        """The value ``lazy(key, ...)`` cached, or None; never builds it."""
        return self._cache.get(key)

    def lazy[T](self, key: str, factory: Callable[[], T]) -> T:
        """Memoised ``factory()``, at most once per key; a slow factory only holds up callers of its own key."""
        if key in self._cache:  # fast path: a cached value never takes a lock
            return cast("T", self._cache[key])
        with self._locks_guard:
            lock = self._locks.setdefault(key, threading.RLock())
        with lock:
            if key not in self._cache:
                self._cache[key] = factory()
            return cast("T", self._cache[key])
