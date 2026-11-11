from __future__ import annotations

import functools

from sharpit.engine.collectors.cache.clear import (
    MAX_CLEARED_NAMES,
    CacheClearRequest,
    CacheManagerSnapshot,
    CacheService,
    CacheSnapshot,
    InProcessCacheProvider,
)


class FakeCacheProvider:
    def __init__(self) -> None:
        self.available_val = True
        self.clear_enabled_val = True
        self.managers_val: list[CacheManagerSnapshot] = []
        self.clear_unavailable_reason_val: str | None = None
        self.evict_returns_false = False
        self.evict_throws = False
        self.evict_false_for: str | None = None
        self.evicted: list[str] = []

    def available(self) -> bool:
        return self.available_val

    def clear_enabled(self) -> bool:
        return self.clear_enabled_val

    def managers(self) -> list[CacheManagerSnapshot]:
        return self.managers_val

    def clear_unavailable_reason(self) -> str | None:
        return self.clear_unavailable_reason_val

    def evict(self, manager_name: str, cache_name: str) -> bool:
        if self.evict_throws:
            raise RuntimeError("IllegalStateException: boom")
        if self.evict_returns_false or cache_name == self.evict_false_for:
            return False
        self.evicted.append(f"{manager_name}/{cache_name}")
        return True


def _single_cache(manager: str, cache: str) -> FakeCacheProvider:
    provider = FakeCacheProvider()
    provider.managers_val = [
        CacheManagerSnapshot(manager, caches=[CacheSnapshot(cache)]),
    ]
    return provider


# ported: CacheServiceTests.nullProviderRendersUnavailableReportAndRefusesClear
def test_null_provider_renders_unavailable_report_and_refuses_clear() -> None:
    service = CacheService(None)
    response = service.clear(CacheClearRequest(confirm=True, all=True))
    assert response.status == 409
    assert response.body.status == "unavailable"
    assert response.body.message == "No cache backend is available."


# ported: CacheServiceTests.clearDisabledIsRejectedWith409
def test_clear_disabled_is_rejected_with_409() -> None:
    provider = FakeCacheProvider()
    provider.clear_enabled_val = False
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(confirm=True, all=True))
    assert response.status == 409
    assert response.body.status == "disabled"
    assert "Cache clearing is disabled. Set SHARPIT_CACHE_CLEAR_ENABLED=true to allow it." in response.body.message


# ported: CacheServiceTests.clearWithoutConfirmationIsRejectedWith400
def test_clear_without_confirmation_is_rejected_with_400() -> None:
    provider = FakeCacheProvider()
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(all=True, confirm=False))
    assert response.status == 400
    assert response.body.status == "confirmation_required"
    assert response.body.message == "Cache clearing requires explicit confirmation."


# ported: CacheServiceTests.clearReportsUnavailableReasonWith409
def test_clear_reports_unavailable_reason_with_409() -> None:
    provider = FakeCacheProvider()
    provider.clear_unavailable_reason_val = "No CacheManager beans are available."
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 409
    assert response.body.status == "unavailable"
    assert response.body.message == "No CacheManager beans are available."


# ported: CacheServiceTests.clearOneRequiresManagerAndCacheName
def test_clear_one_requires_manager_and_cache_name() -> None:
    provider = FakeCacheProvider()
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(confirm=True, all=False))
    assert response.status == 400
    assert response.body.status == "invalid_request"
    assert response.body.message == "managerName and cacheName are required when clearing one cache."


# ported: CacheServiceTests.clearOneUnknownManagerIs404
def test_clear_one_unknown_manager_is_404() -> None:
    provider = FakeCacheProvider()
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(manager_name="missing", cache_name="orders", confirm=True))
    assert response.status == 404
    assert response.body.status == "not_found"
    assert "Cache manager 'missing' was not found." in response.body.message


# ported: CacheServiceTests.clearOneUnknownCacheIs404
def test_clear_one_unknown_cache_is_404() -> None:
    provider = _single_cache("cacheManager", "orders")
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(manager_name="cacheManager", cache_name="ghost", confirm=True))
    assert response.status == 404
    assert response.body.status == "not_found"
    assert "Cache 'ghost' was not found in manager 'cacheManager'." in response.body.message


# ported: CacheServiceTests.clearOneEvictsAndReportsClearedEntry
def test_clear_one_evicts_and_reports_cleared_entry() -> None:
    provider = _single_cache("cacheManager", "orders")
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(manager_name="cacheManager", cache_name="orders", confirm=True))
    assert response.status == 200
    assert response.body.status == "cleared"
    assert response.body.caches == ["cacheManager/orders"]
    assert provider.evicted == ["cacheManager/orders"]


# ported: CacheServiceTests.clearAllEvictsEveryCacheWithPluralizedMessage
def test_clear_all_evicts_every_cache_with_pluralized_message() -> None:
    provider = FakeCacheProvider()
    provider.managers_val = [
        CacheManagerSnapshot(
            "cacheManager",
            caches=[CacheSnapshot("orders"), CacheSnapshot("customers")],
        )
    ]
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 200
    assert response.body.cleared_caches == 2
    assert response.body.message == "Cleared 2 caches."
    assert response.body.caches == ["cacheManager/customers", "cacheManager/orders"]


# ported: CacheServiceTests.clearAllReportsAnExactCountButABoundedListOfNames
def test_clear_all_reports_an_exact_count_but_a_bounded_list_of_names() -> None:
    total = MAX_CLEARED_NAMES + 25
    caches = [CacheSnapshot(f"cache-{i:04d}") for i in range(total)]
    provider = FakeCacheProvider()
    provider.managers_val = [CacheManagerSnapshot("cacheManager", caches=caches)]
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 200
    assert response.body.message == f"Cleared {total} caches."
    assert len(provider.evicted) == total
    assert len(response.body.caches) == MAX_CLEARED_NAMES + 1
    assert response.body.caches[MAX_CLEARED_NAMES] == "... and 25 more"


# ported: CacheServiceTests.clearAllSingularMessageForOneCache
def test_clear_all_singular_message_for_one_cache() -> None:
    provider = _single_cache("cacheManager", "orders")
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 200
    assert response.body.message == "Cleared 1 cache."


# ported: CacheServiceTests.clearOneOnCacheThatVanishedReturns404NotFound
def test_clear_one_on_cache_that_vanished_returns_404_not_found() -> None:
    provider = _single_cache("cacheManager", "orders")
    provider.evict_returns_false = True
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(manager_name="cacheManager", cache_name="orders", confirm=True))
    assert response.status == 404
    assert response.body.status == "not_found"
    assert "was not returned by manager 'cacheManager'" in response.body.message


# ported: CacheServiceTests.clearAllSkipsAVanishedCacheInsteadOfAborting
def test_clear_all_skips_a_vanished_cache_instead_of_aborting() -> None:
    provider = FakeCacheProvider()
    provider.managers_val = [
        CacheManagerSnapshot(
            "cacheManager",
            caches=[CacheSnapshot("orders"), CacheSnapshot("vanished")],
        )
    ]
    provider.evict_false_for = "vanished"
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 200
    assert response.body.status == "cleared"
    assert response.body.caches == ["cacheManager/orders"]


# ported: CacheServiceTests.clearMapsGenuineEvictionFailureTo500
def test_clear_maps_genuine_eviction_failure_to_500() -> None:
    provider = _single_cache("cacheManager", "orders")
    provider.evict_throws = True
    service = CacheService(provider)
    response = service.clear(CacheClearRequest(manager_name="cacheManager", cache_name="orders", confirm=True))
    assert response.status == 500
    assert response.body.status == "failed"
    assert "(RuntimeError)" in response.body.message


def test_cache_clear_never_calls_remote_backend() -> None:
    class ExplodingRemoteCache:
        def clear(self) -> None:
            raise AssertionError("Remote backend clear was called!")

    provider = InProcessCacheProvider()
    provider.register("redis", "session_cache", ExplodingRemoteCache(), is_remote=True)

    service = CacheService(provider)
    # Clear one remote cache refuses with 409 unavailable
    resp1 = service.clear(CacheClearRequest(manager_name="redis", cache_name="session_cache", confirm=True))
    assert resp1.status == 409
    assert resp1.body.status == "unavailable"

    # Clear all skips remote cache and does not call clear()
    resp2 = service.clear(CacheClearRequest(all=True, confirm=True))
    assert resp2.status == 200
    assert resp2.body.cleared_caches == 0


def test_cache_clear_clears_functools_lru_cache() -> None:
    calls = 0

    @functools.lru_cache(maxsize=128)
    def compute(x: int) -> int:
        nonlocal calls
        calls += 1
        return x * 2

    compute(1)
    compute(2)
    assert compute.cache_info().currsize == 2

    provider = InProcessCacheProvider()
    provider.register("functions", "compute", compute)
    service = CacheService(provider)

    resp = service.clear(CacheClearRequest(manager_name="functions", cache_name="compute", confirm=True))
    assert resp.status == 200
    assert compute.cache_info().currsize == 0


def test_cache_clear_clears_functools_cache() -> None:
    @functools.cache
    def fib(n: int) -> int:
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    fib(5)
    assert fib.cache_info().currsize > 0

    provider = InProcessCacheProvider()
    provider.register("functions", "fib", fib)
    service = CacheService(provider)

    resp = service.clear(CacheClearRequest(all=True, confirm=True))
    assert resp.status == 200
    assert fib.cache_info().currsize == 0


def test_cache_clear_clears_cachetools_mapping() -> None:
    cache: dict[str, str] = {"k1": "v1", "k2": "v2"}
    assert len(cache) == 2

    provider = InProcessCacheProvider()
    provider.register("in_process", "items", cache)
    service = CacheService(provider)

    resp = service.clear(CacheClearRequest(manager_name="in_process", cache_name="items", confirm=True))
    assert resp.status == 200
    assert len(cache) == 0


def test_cache_clear_eviction_error_masked() -> None:
    class MaskerSpy:
        def mask_text(self, text: str) -> str:
            return text.replace("SecretError", "***REDACTED***")

    class SecretError(RuntimeError):
        pass

    class FailingCache:
        def clear(self) -> None:
            raise SecretError("boom")

    provider = InProcessCacheProvider()
    provider.register("in_process", "secret", FailingCache())
    service = CacheService(provider, masker=MaskerSpy())

    resp = service.clear(CacheClearRequest(manager_name="in_process", cache_name="secret", confirm=True))
    assert resp.status == 500
    assert "***REDACTED***" in resp.body.message
    assert "SecretError" not in resp.body.message
