"""Cache clear action for in-process caches (port of BootUI CacheService.java:137-240)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

MAX_CLEARED_NAMES = 200


@dataclass(frozen=True)
class CacheClearRequest:
    manager_name: str | None = None
    cache_name: str | None = None
    all: bool | None = None
    confirm: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CacheClearRequest | None:
        if data is None:
            return None
        return cls(
            manager_name=data.get("managerName"),
            cache_name=data.get("cacheName"),
            all=data.get("all"),
            confirm=data.get("confirm"),
        )


@dataclass(frozen=True)
class CacheClearResult:
    status: str = "stub"
    message: str = "stub"
    cleared_caches: int = -1
    caches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "clearedCaches": self.cleared_caches,
            "caches": list(self.caches),
        }


@dataclass(frozen=True)
class CacheClearResponse:
    status: int = 999
    body: CacheClearResult = field(default_factory=CacheClearResult)


@dataclass(frozen=True)
class CacheSnapshot:
    name: str
    native_type: str | None = None
    size: int | None = None
    is_remote: bool = False


@dataclass(frozen=True)
class CacheManagerSnapshot:
    name: str
    type_name: str = "builtins.dict"
    no_op: bool = False
    is_remote: bool = False
    caches: list[CacheSnapshot] = field(default_factory=list)


class CacheProvider(Protocol):
    def available(self) -> bool: ...

    def clear_enabled(self) -> bool: ...

    def managers(self) -> list[CacheManagerSnapshot]: ...

    def clear_unavailable_reason(self) -> str | None: ...

    def evict(self, manager_name: str, cache_name: str) -> bool: ...


class InProcessCacheProvider:
    """Default provider for in-process caches (functools lru_cache/cache, cachetools, dicts)."""

    def __init__(self) -> None:
        self._available = True
        self._clear_enabled = True
        self._unavailable_reason: str | None = None
        self._managers: dict[str, CacheManagerSnapshot] = {}
        self._cache_objects: dict[tuple[str, str], tuple[Any, bool]] = {}

    def available(self) -> bool:
        return self._available

    def clear_enabled(self) -> bool:
        return self._clear_enabled

    def managers(self) -> list[CacheManagerSnapshot]:
        return list(self._managers.values())

    def clear_unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    def register(
        self,
        manager_name: str,
        cache_name: str,
        cache_obj: Any,
        *,
        is_remote: bool = False,
        native_type: str | None = None,
    ) -> None:
        self._cache_objects[(manager_name, cache_name)] = (cache_obj, is_remote)
        type_str = native_type or f"{type(cache_obj).__module__}.{type(cache_obj).__qualname__}"
        snapshot = CacheSnapshot(name=cache_name, native_type=type_str, is_remote=is_remote)
        if manager_name in self._managers:
            existing = self._managers[manager_name]
            updated_caches = [c for c in existing.caches if c.name != cache_name] + [snapshot]
            self._managers[manager_name] = CacheManagerSnapshot(
                name=manager_name,
                type_name=existing.type_name,
                no_op=existing.no_op,
                is_remote=existing.is_remote or is_remote,
                caches=updated_caches,
            )
        else:
            self._managers[manager_name] = CacheManagerSnapshot(
                name=manager_name,
                type_name="in_process",
                is_remote=is_remote,
                caches=[snapshot],
            )

    def evict(self, manager_name: str, cache_name: str) -> bool:
        # Stub in red phase
        return False


class CacheService:
    def __init__(
        self,
        provider: CacheProvider | None,
        *,
        clear_enabled: bool = True,
        masker: Any | None = None,
    ) -> None:
        self.provider = provider
        self._clear_enabled = clear_enabled
        self.masker = masker

    def clear(self, request: CacheClearRequest | None) -> CacheClearResponse:
        # Stub for red phase: returns status 999 to fail test assertions
        return CacheClearResponse(status=999, body=CacheClearResult())
