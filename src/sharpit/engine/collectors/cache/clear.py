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
    status: str
    message: str
    cleared_caches: int
    caches: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "clearedCaches": self.cleared_caches,
            "caches": list(self.caches),
        }


@dataclass(frozen=True)
class CacheClearResponse:
    status: int
    body: CacheClearResult


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
    caches: list[CacheSnapshot] = field(default_factory=list[CacheSnapshot])


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
        key = (manager_name, cache_name)
        if key not in self._cache_objects:
            return False
        cache_obj, is_remote = self._cache_objects[key]
        if is_remote:
            # Remote caches must NEVER be invoked
            return False

        if hasattr(cache_obj, "cache_clear") and callable(cache_obj.cache_clear):
            cache_obj.cache_clear()
            return True
        if hasattr(cache_obj, "clear") and callable(cache_obj.clear):
            cache_obj.clear()
            return True
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
        if self.provider is None or not self.provider.available():
            return self._result(409, "unavailable", "No cache backend is available.", [])

        if not self._clear_enabled or not self.provider.clear_enabled():
            return self._result(
                409,
                "disabled",
                "Cache clearing is disabled. Set SHARPIT_CACHE_CLEAR_ENABLED=true to allow it.",
                [],
            )

        if request is None or not request.confirm:
            return self._result(
                400,
                "confirmation_required",
                "Cache clearing requires explicit confirmation.",
                [],
            )

        unavailable_reason = self.provider.clear_unavailable_reason()
        if unavailable_reason is not None:
            return self._result(409, "unavailable", unavailable_reason, [])

        managers = self._sorted_managers()
        if request.all:
            return self._clear_all(managers)

        manager_name = request.manager_name
        cache_name = request.cache_name
        if not manager_name or not manager_name.strip() or not cache_name or not cache_name.strip():
            return self._result(
                400,
                "invalid_request",
                "managerName and cacheName are required when clearing one cache.",
                [],
            )

        return self._clear_one(managers, manager_name.strip(), cache_name.strip())

    def _sorted_managers(self) -> list[CacheManagerSnapshot]:
        if self.provider is None:
            return []
        return sorted(self.provider.managers(), key=lambda m: m.name)

    def _sorted_caches(self, manager: CacheManagerSnapshot) -> list[CacheSnapshot]:
        return sorted(manager.caches, key=lambda c: c.name)

    def _clear_all(self, managers: list[CacheManagerSnapshot]) -> CacheClearResponse:
        if self.provider is None:
            return self._result(409, "unavailable", "No cache backend is available.", [])
        cleared: list[str] = []
        cleared_count = 0
        for manager in managers:
            if manager.is_remote:
                continue
            for cache in self._sorted_caches(manager):
                if cache.is_remote:
                    continue
                try:
                    evicted = self.provider.evict(manager.name, cache.name)
                except Exception as ex:
                    return self._failed_result(manager.name, cache.name, ex, cleared)
                if evicted:
                    cleared_count += 1
                    if len(cleared) < MAX_CLEARED_NAMES:
                        cleared.append(f"{manager.name}/{cache.name}")

        if cleared_count > len(cleared):
            cleared.append(f"... and {cleared_count - len(cleared)} more")

        message = f"Cleared {cleared_count} cache." if cleared_count == 1 else f"Cleared {cleared_count} caches."
        return self._result(200, "cleared", message, cleared, cleared_count=cleared_count)

    def _clear_one(
        self, managers: list[CacheManagerSnapshot], manager_name: str, cache_name: str
    ) -> CacheClearResponse:
        if self.provider is None:
            return self._result(409, "unavailable", "No cache backend is available.", [])
        manager = next((m for m in managers if m.name == manager_name), None)
        if manager is None:
            return self._result(404, "not_found", f"Cache manager '{manager_name}' was not found.", [])

        cache = next((c for c in manager.caches if c.name == cache_name), None)
        if cache is None:
            return self._result(
                404,
                "not_found",
                f"Cache '{cache_name}' was not found in manager '{manager_name}'.",
                [],
            )

        if manager.is_remote or cache.is_remote:
            return self._result(
                409,
                "unavailable",
                f"Remote cache '{cache_name}' in manager '{manager_name}' does not support clearing.",
                [],
            )

        try:
            evicted = self.provider.evict(manager_name, cache_name)
        except Exception as ex:
            return self._failed_result(manager_name, cache_name, ex, [])

        if not evicted:
            return self._result(
                404,
                "not_found",
                f"Cache '{cache_name}' was not returned by manager '{manager_name}'.",
                [],
            )

        cleared = [f"{manager_name}/{cache_name}"]
        return self._result(
            200,
            "cleared",
            f"Cleared cache '{cache_name}' from manager '{manager_name}'.",
            cleared,
            cleared_count=1,
        )

    def _failed_result(
        self, manager_name: str, cache_name: str, ex: Exception, cleared: list[str]
    ) -> CacheClearResponse:
        type_name = type(ex).__name__
        if self.masker is not None and hasattr(self.masker, "mask_text"):
            type_name = self.masker.mask_text(type_name)
        message = f"Failed to clear cache '{cache_name}' from manager '{manager_name}' ({type_name})."
        return self._result(500, "failed", message, cleared, cleared_count=len(cleared))

    def _result(
        self, status: int, result_status: str, message: str, caches: list[str], cleared_count: int | None = None
    ) -> CacheClearResponse:
        count = len(caches) if cleared_count is None else cleared_count
        return CacheClearResponse(
            status=status,
            body=CacheClearResult(
                status=result_status,
                message=message,
                cleared_caches=count,
                caches=list(caches),
            ),
        )
