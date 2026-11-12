"""Cache clear action for in-process caches (port of BootUI CacheService.java:137-240)."""

from __future__ import annotations

import functools
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

MAX_CLEARED_NAMES = 200
MAX_ECHOED_NAME = 120
_NO_BACKEND = "No cache backend is available."
_LRU_WRAPPER = type(functools.lru_cache(maxsize=1)(lambda: None))


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
        manager_name = data.get("managerName")
        cache_name = data.get("cacheName")
        # BootUI reads Boolean.TRUE.equals: only JSON true counts. A non-string name is no name.
        return cls(
            manager_name=manager_name if isinstance(manager_name, str) else None,
            cache_name=cache_name if isinstance(cache_name, str) else None,
            all=data.get("all") is True,
            confirm=data.get("confirm") is True,
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
        self._lock = threading.RLock()

    def available(self) -> bool:
        return self._available

    def clear_enabled(self) -> bool:
        return self._clear_enabled

    def managers(self) -> list[CacheManagerSnapshot]:
        with self._lock:
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
        if not _is_supported(cache_obj):
            raise TypeError("only functools cache wrappers and cachetools.Cache instances can be registered")
        with self._lock:
            self._register(manager_name, cache_name, cache_obj, is_remote, native_type)

    def _register(
        self, manager_name: str, cache_name: str, cache_obj: Any, is_remote: bool, native_type: str | None
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
        with self._lock:
            entry = self._cache_objects.get((manager_name, cache_name))
        if entry is None or entry[1]:  # a remote cache is NEVER invoked
            return False
        cache_obj = entry[0]
        if type(cache_obj) is _LRU_WRAPPER:
            cache_obj.cache_clear()
        else:
            cache_obj.clear()
        return True


def _cachetools_cache() -> type | None:
    module = sys.modules.get("cachetools")  # never imported: the host's own copy, if it has one
    cls = getattr(module, "Cache", None)
    return cls if isinstance(cls, type) else None


def _is_supported(cache_obj: object) -> bool:
    """A functools wrapper or a cachetools.Cache, by type alone: no attribute of a host object is read."""
    if type(cache_obj) is _LRU_WRAPPER:
        return True
    cache_cls = _cachetools_cache()
    return cache_cls is not None and issubclass(type(cache_obj), cache_cls)


class CacheService:
    def __init__(
        self,
        provider: CacheProvider | None,
        *,
        clear_enabled: bool = False,
        masker: Any | None = None,
    ) -> None:
        self.provider = provider
        self._clear_enabled = clear_enabled
        self.masker = masker
        self._lock = threading.Lock()  # clear actions run one at a time; reads never take it

    def _echo(self, name: str) -> str:
        """A request name as shown in a message: masked first, then bounded."""
        text = name
        if self.masker is not None and hasattr(self.masker, "mask_text"):
            text = self.masker.mask_text(text) or ""
        return text if len(text) <= MAX_ECHOED_NAME else text[:MAX_ECHOED_NAME] + "..."

    def clear(self, request: CacheClearRequest | None) -> CacheClearResponse:
        with self._lock:
            return self._clear(request)

    def _clear(self, request: CacheClearRequest | None) -> CacheClearResponse:
        refusal = self._refusal(request)
        if refusal is not None:
            return refusal
        request = cast("CacheClearRequest", request)  # _refusal returned None, so it is not None
        managers = self._sorted_managers()
        if request.all is True:
            return self._clear_all(managers)
        return self._clear_named(managers, request)

    def _refusal(self, request: CacheClearRequest | None) -> CacheClearResponse | None:
        """The first gate that refuses the request, in gate order, or None when it may proceed."""
        if self.provider is None or not self.provider.available():
            return self._result(409, "unavailable", _NO_BACKEND, [])

        if not self._clear_enabled or not self.provider.clear_enabled():
            return self._result(
                409,
                "disabled",
                "Cache clearing is disabled. Set SHARPIT_CACHE_CLEAR_ENABLED=true to allow it.",
                [],
            )

        if request is None or request.confirm is not True:
            return self._result(
                400,
                "confirmation_required",
                "Cache clearing requires explicit confirmation.",
                [],
            )

        unavailable_reason = self.provider.clear_unavailable_reason()
        if unavailable_reason is not None:
            return self._result(409, "unavailable", unavailable_reason, [])
        return None

    def _clear_named(self, managers: list[CacheManagerSnapshot], request: CacheClearRequest) -> CacheClearResponse:
        manager_name = request.manager_name
        cache_name = request.cache_name
        if manager_name is None or not manager_name.strip() or cache_name is None or not cache_name.strip():
            return self._result(
                400,
                "invalid_request",
                "managerName and cacheName are required when clearing one cache.",
                [],
            )
        return self._clear_one(managers, manager_name, cache_name)

    def _sorted_managers(self) -> list[CacheManagerSnapshot]:
        if self.provider is None:
            return []
        return sorted(self.provider.managers(), key=lambda m: m.name)

    def _sorted_caches(self, manager: CacheManagerSnapshot) -> list[CacheSnapshot]:
        return sorted(manager.caches, key=lambda c: c.name)

    def _clear_all(self, managers: list[CacheManagerSnapshot]) -> CacheClearResponse:
        if self.provider is None:
            return self._result(409, "unavailable", _NO_BACKEND, [])
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
            return self._result(409, "unavailable", _NO_BACKEND, [])
        manager = next((m for m in managers if m.name == manager_name), None)
        if manager is None:
            return self._result(404, "not_found", f"Cache manager '{self._echo(manager_name)}' was not found.", [])

        cache = next((c for c in manager.caches if c.name == cache_name), None)
        if cache is None:
            return self._result(
                404,
                "not_found",
                f"Cache '{self._echo(cache_name)}' was not found in manager '{self._echo(manager_name)}'.",
                [],
            )

        if manager.is_remote or cache.is_remote:
            return self._result(
                409,
                "unavailable",
                f"Remote cache '{self._echo(cache_name)}' in manager '{self._echo(manager_name)}' "
                "does not support clearing.",
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
                f"Cache '{self._echo(cache_name)}' was not returned by manager '{self._echo(manager_name)}'.",
                [],
            )

        cleared = [f"{manager_name}/{cache_name}"]
        return self._result(
            200,
            "cleared",
            f"Cleared cache '{self._echo(cache_name)}' from manager '{self._echo(manager_name)}'.",
            cleared,
            cleared_count=1,
        )

    def _failed_result(
        self, manager_name: str, cache_name: str, ex: Exception, cleared: list[str]
    ) -> CacheClearResponse:
        type_name = type(ex).__name__
        if self.masker is not None and hasattr(self.masker, "mask_text"):
            type_name = self.masker.mask_text(type_name)
        message = (
            f"Failed to clear cache '{self._echo(cache_name)}' from manager '{self._echo(manager_name)}' ({type_name})."
        )
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
