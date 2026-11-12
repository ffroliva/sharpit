from __future__ import annotations

import functools
import sys
import threading
import types
from typing import Any

import pytest

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
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(confirm=True, all=True))
    assert response.status == 409
    assert response.body.status == "disabled"
    assert "Cache clearing is disabled. Set SHARPIT_CACHE_CLEAR_ENABLED=true to allow it." in response.body.message


# ported: CacheServiceTests.clearWithoutConfirmationIsRejectedWith400
def test_clear_without_confirmation_is_rejected_with_400() -> None:
    provider = FakeCacheProvider()
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(all=True, confirm=False))
    assert response.status == 400
    assert response.body.status == "confirmation_required"
    assert response.body.message == "Cache clearing requires explicit confirmation."


# ported: CacheServiceTests.clearReportsUnavailableReasonWith409
def test_clear_reports_unavailable_reason_with_409() -> None:
    provider = FakeCacheProvider()
    provider.clear_unavailable_reason_val = "No CacheManager beans are available."
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 409
    assert response.body.status == "unavailable"
    assert response.body.message == "No CacheManager beans are available."


# ported: CacheServiceTests.clearOneRequiresManagerAndCacheName
def test_clear_one_requires_manager_and_cache_name() -> None:
    provider = FakeCacheProvider()
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(confirm=True, all=False))
    assert response.status == 400
    assert response.body.status == "invalid_request"
    assert response.body.message == "managerName and cacheName are required when clearing one cache."


# ported: CacheServiceTests.clearOneUnknownManagerIs404
def test_clear_one_unknown_manager_is_404() -> None:
    provider = FakeCacheProvider()
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(manager_name="missing", cache_name="orders", confirm=True))
    assert response.status == 404
    assert response.body.status == "not_found"
    assert "Cache manager 'missing' was not found." in response.body.message


# ported: CacheServiceTests.clearOneUnknownCacheIs404
def test_clear_one_unknown_cache_is_404() -> None:
    provider = _single_cache("cacheManager", "orders")
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(manager_name="cacheManager", cache_name="ghost", confirm=True))
    assert response.status == 404
    assert response.body.status == "not_found"
    assert "Cache 'ghost' was not found in manager 'cacheManager'." in response.body.message


# ported: CacheServiceTests.clearOneEvictsAndReportsClearedEntry
def test_clear_one_evicts_and_reports_cleared_entry() -> None:
    provider = _single_cache("cacheManager", "orders")
    service = CacheService(provider, clear_enabled=True)
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
    service = CacheService(provider, clear_enabled=True)
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
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 200
    assert response.body.message == f"Cleared {total} caches."
    assert len(provider.evicted) == total
    assert len(response.body.caches) == MAX_CLEARED_NAMES + 1
    assert response.body.caches[MAX_CLEARED_NAMES] == "... and 25 more"


# ported: CacheServiceTests.clearAllSingularMessageForOneCache
def test_clear_all_singular_message_for_one_cache() -> None:
    provider = _single_cache("cacheManager", "orders")
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 200
    assert response.body.message == "Cleared 1 cache."


# ported: CacheServiceTests.clearOneOnCacheThatVanishedReturns404NotFound
def test_clear_one_on_cache_that_vanished_returns_404_not_found() -> None:
    provider = _single_cache("cacheManager", "orders")
    provider.evict_returns_false = True
    service = CacheService(provider, clear_enabled=True)
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
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(all=True, confirm=True))
    assert response.status == 200
    assert response.body.status == "cleared"
    assert response.body.caches == ["cacheManager/orders"]


# ported: CacheServiceTests.clearMapsGenuineEvictionFailureTo500
def test_clear_maps_genuine_eviction_failure_to_500() -> None:
    provider = _single_cache("cacheManager", "orders")
    provider.evict_throws = True
    service = CacheService(provider, clear_enabled=True)
    response = service.clear(CacheClearRequest(manager_name="cacheManager", cache_name="orders", confirm=True))
    assert response.status == 500
    assert response.body.status == "failed"
    assert "(RuntimeError)" in response.body.message


def test_cache_clear_never_calls_remote_backend() -> None:
    def _boom() -> None:
        raise AssertionError("Remote backend clear was called!")

    remote = _lru()
    remote.cache_clear = _boom

    provider = InProcessCacheProvider()
    provider.register("redis", "session_cache", remote, is_remote=True)

    service = CacheService(provider, clear_enabled=True)
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
    service = CacheService(provider, clear_enabled=True)

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
    service = CacheService(provider, clear_enabled=True)

    resp = service.clear(CacheClearRequest(all=True, confirm=True))
    assert resp.status == 200
    assert fib.cache_info().currsize == 0


def test_cache_clear_clears_cachetools_mapping(fake_cachetools: type) -> None:
    cache = fake_cachetools()
    cache.update({"k1": "v1", "k2": "v2"})
    assert len(cache) == 2

    provider = InProcessCacheProvider()
    provider.register("in_process", "items", cache)
    service = CacheService(provider, clear_enabled=True)

    resp = service.clear(CacheClearRequest(manager_name="in_process", cache_name="items", confirm=True))
    assert resp.status == 200
    assert len(cache) == 0


def test_cache_clear_eviction_error_masked() -> None:
    class MaskerSpy:
        def mask_text(self, text: str) -> str:
            return text.replace("SecretError", "***REDACTED***")

    class SecretError(RuntimeError):
        pass

    def _boom() -> None:
        raise SecretError("boom")

    failing = _lru()
    failing.cache_clear = _boom

    provider = InProcessCacheProvider()
    provider.register("in_process", "secret", failing)
    service = CacheService(provider, clear_enabled=True, masker=MaskerSpy())

    resp = service.clear(CacheClearRequest(manager_name="in_process", cache_name="secret", confirm=True))
    assert resp.status == 500
    assert "***REDACTED***" in resp.body.message
    assert "SecretError" not in resp.body.message


@pytest.fixture
def fake_cachetools(monkeypatch: pytest.MonkeyPatch) -> type:
    """A stand-in ``cachetools`` module in ``sys.modules`` (the library is not a dependency, never imported)."""

    class Cache(dict[str, Any]):
        pass

    module = types.ModuleType("cachetools")
    module.Cache = Cache  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cachetools", module)
    return Cache


def _lru() -> Any:
    @functools.lru_cache
    def compute(x: int) -> int:
        return x

    compute(1)
    return compute


def _service(manager: str = "m", name: str = "c") -> tuple[CacheService, Any]:
    fn = _lru()
    provider = InProcessCacheProvider()
    provider.register(manager, name, fn)
    return CacheService(provider, clear_enabled=True), fn


# finding 2: BootUI Boolean.TRUE.equals, so only JSON true counts
@pytest.mark.parametrize(
    "body",
    [
        {"all": True, "confirm": "false"},
        {"all": "no", "confirm": "no"},
        {"all": True, "confirm": 1},
        {"all": True, "confirm": "true"},
    ],
)
def test_confirm_must_be_json_true(body: dict[str, Any]) -> None:
    service, fn = _service()
    response = service.clear(CacheClearRequest.from_dict(body))
    assert response.status == 400
    assert response.body.status == "confirmation_required"
    assert fn.cache_info().currsize == 1


@pytest.mark.parametrize("flag", ["yes", 1, "true", ["x"]])
def test_all_must_be_json_true(flag: object) -> None:
    service, fn = _service()
    response = service.clear(CacheClearRequest.from_dict({"all": flag, "confirm": True}))
    assert response.status == 400
    assert response.body.status == "invalid_request"
    assert fn.cache_info().currsize == 1


def _outcome(service: CacheService, body: dict[str, Any]) -> tuple[object, object]:
    """``(status, result status)``, or ``("raised", ExceptionName)``: a crash must fail an assert, not error."""
    try:
        response = service.clear(CacheClearRequest.from_dict(body))
    except Exception as exc:
        return "raised", type(exc).__name__
    return response.status, response.body.status


# finding 3: a non-string name is an invalid request, never a crash
@pytest.mark.parametrize("bad", [5, ["c"], {"a": 1}, True])
def test_non_string_manager_name_is_invalid_request(bad: object) -> None:
    service, fn = _service()
    assert _outcome(service, {"managerName": bad, "cacheName": "c", "confirm": True}) == (400, "invalid_request")
    assert fn.cache_info().currsize == 1


@pytest.mark.parametrize("bad", [5, ["c"], {"a": 1}, True])
def test_non_string_cache_name_is_invalid_request(bad: object) -> None:
    service, fn = _service()
    assert _outcome(service, {"managerName": "m", "cacheName": bad, "confirm": True}) == (400, "invalid_request")
    assert fn.cache_info().currsize == 1


# finding 4: echoed request text is masked and bounded
def test_echoed_name_is_bounded() -> None:
    service, _ = _service()
    name = "x" * 100_000
    response = service.clear(CacheClearRequest(manager_name=name, cache_name="c", confirm=True))
    assert response.status == 404
    assert len(response.body.message) < 500


def test_echoed_name_is_masked() -> None:
    from sharpit.engine.masking import Exposure, Masker

    secret = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
    service, _ = _service()
    service.masker = Masker(Exposure.MASKED, True)
    response = service.clear(CacheClearRequest(manager_name=f"token={secret}", cache_name="c", confirm=True))
    assert response.status == 404
    assert secret not in response.body.message


# finding 5: BootUI matches names exactly; no whitespace stripping
def test_names_match_exactly_no_strip() -> None:
    service, fn = _service()
    response = service.clear(CacheClearRequest(manager_name=" m ", cache_name=" c ", confirm=True))
    assert response.status == 404
    assert response.body.status == "not_found"
    assert fn.cache_info().currsize == 1


def test_blank_names_still_invalid_request() -> None:
    service, _ = _service()
    response = service.clear(CacheClearRequest(manager_name="  ", cache_name="c", confirm=True))
    assert response.status == 400
    assert response.body.status == "invalid_request"


# finding 6: only functools wrappers and cachetools.Cache instances are accepted; host code is never probed
def test_register_rejects_plain_dict() -> None:
    provider = InProcessCacheProvider()
    with pytest.raises(TypeError):
        provider.register("m", "c", {"k": "v"})


def test_register_never_probes_host_getattr() -> None:
    probed: list[str] = []

    class Hostile:
        def __getattr__(self, name: str) -> Any:
            probed.append(name)
            raise AssertionError(name)

    provider = InProcessCacheProvider()
    hostile = Hostile()
    with pytest.raises(TypeError):
        provider.register("m", "c", hostile)
    assert probed == []


def test_unsupported_object_clear_never_runs() -> None:
    cleared: list[str] = []

    class Plain:
        def clear(self) -> None:
            cleared.append("clear")

    provider = InProcessCacheProvider()
    plain = Plain()
    with pytest.raises(TypeError):
        provider.register("m", "c", plain)
    response = CacheService(provider, clear_enabled=True).clear(CacheClearRequest(all=True, confirm=True))
    assert response.body.cleared_caches == 0
    assert cleared == []


def test_cachetools_instance_is_cleared(fake_cachetools: type) -> None:
    cache = fake_cachetools()
    cache["k"] = "v"
    provider = InProcessCacheProvider()
    provider.register("m", "c", cache)
    response = CacheService(provider, clear_enabled=True).clear(CacheClearRequest(all=True, confirm=True))
    assert response.body.cleared_caches == 1
    assert len(cache) == 0


def test_register_does_not_import_cachetools() -> None:
    sys.modules.pop("cachetools", None)
    provider = InProcessCacheProvider()
    provider.register("m", "c", _lru())
    assert "cachetools" not in sys.modules


# finding 7: clear actions are serialised, so two requests never interleave evictions
def test_clear_actions_are_serialised(fake_cachetools: type) -> None:
    entered = threading.Event()
    release = threading.Event()
    b_cleared = threading.Event()

    class Slow(fake_cachetools):
        def clear(self) -> None:
            entered.set()
            release.wait(5)

    class Fast(fake_cachetools):
        def clear(self) -> None:
            b_cleared.set()

    provider = InProcessCacheProvider()
    provider.register("m", "a", Slow())
    provider.register("m", "b", Fast())
    service = CacheService(provider, clear_enabled=True)
    one = CacheClearRequest(manager_name="m", cache_name="a", confirm=True)
    two = CacheClearRequest(manager_name="m", cache_name="b", confirm=True)
    first = threading.Thread(target=lambda: service.clear(one))
    second = threading.Thread(target=lambda: service.clear(two))
    first.start()
    assert entered.wait(5)
    second.start()
    ran_while_first_blocked = b_cleared.wait(0.3)
    release.set()
    first.join(5)
    second.join(5)
    assert not ran_while_first_blocked
    assert b_cleared.is_set()


# round 3 finding 3: every echo of a cache name is masked and bounded
SECRET = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
SECRET_NAME = f"token={SECRET}"


def _masked(service: CacheService) -> CacheService:
    from sharpit.engine.masking import Exposure, Masker

    service.masker = Masker(Exposure.MASKED, True)
    return service


def test_remote_cache_message_masks_name() -> None:
    provider = InProcessCacheProvider()
    provider.register("redis", SECRET_NAME, _lru(), is_remote=True)
    service = _masked(CacheService(provider, clear_enabled=True))
    response = service.clear(CacheClearRequest(manager_name="redis", cache_name=SECRET_NAME, confirm=True))
    assert response.status == 409
    assert SECRET not in response.body.message


def test_not_returned_message_masks_name() -> None:
    fake = FakeCacheProvider()
    fake.managers_val = [CacheManagerSnapshot(name="m", caches=[CacheSnapshot(name=SECRET_NAME)])]
    fake.evict_returns_false = True
    service = _masked(CacheService(fake, clear_enabled=True))
    response = service.clear(CacheClearRequest(manager_name="m", cache_name=SECRET_NAME, confirm=True))
    assert response.status == 404
    assert SECRET not in response.body.message


def test_failed_message_masks_name() -> None:
    fake = FakeCacheProvider()
    fake.managers_val = [CacheManagerSnapshot(name="m", caches=[CacheSnapshot(name=SECRET_NAME)])]
    fake.evict_throws = True
    service = _masked(CacheService(fake, clear_enabled=True))
    response = service.clear(CacheClearRequest(manager_name="m", cache_name=SECRET_NAME, confirm=True))
    assert response.status == 500
    assert SECRET not in response.body.message


def test_cleared_message_masks_name() -> None:
    provider = InProcessCacheProvider()
    provider.register("m", SECRET_NAME, _lru())
    service = _masked(CacheService(provider, clear_enabled=True))
    response = service.clear(CacheClearRequest(manager_name="m", cache_name=SECRET_NAME, confirm=True))
    assert response.status == 200
    assert SECRET not in response.body.message
