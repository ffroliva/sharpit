from typing import Any

from sharpit.engine.headers import security_headers

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
    " img-src 'self' data:; font-src 'self' data:; connect-src 'self';"
    " object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
PERMS = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"


# ported: BootUiSecurityHeadersTests.canonicalHeadersContainTheCompleteBrowserPolicy
def test_exact_policy_headers():
    h = dict(security_headers("shell"))
    assert h["Content-Security-Policy"] == CSP
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert h["Permissions-Policy"] == PERMS


# ported: BootUiSecurityHeadersTests.apiResponsesAreNeverCached, onlyContentHashedAssetsAreImmutable
def test_cache_per_kind():
    api = dict(security_headers("api"))
    assert api["Cache-Control"] == "no-store, must-revalidate"
    assert api["Pragma"] == "no-cache"
    shell = dict(security_headers("shell"))
    assert shell["Cache-Control"] == "no-cache"
    assert shell["Pragma"] == "no-cache"
    asset = dict(security_headers("asset"))
    assert asset["Cache-Control"] == "public, max-age=31536000, immutable"
    assert "Pragma" not in asset


def _guarded(inner_headers: dict[str, str]) -> Any:
    """GuardMiddleware of an active install, in front of an app answering with ``inner_headers``."""
    from fastapi.testclient import TestClient
    from starlette.responses import Response

    from fastapi import FastAPI
    from sharpit import install
    from sharpit.fastapi.adapter import GuardMiddleware

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await Response("{}", media_type="application/json", headers=inner_headers)(scope, receive, send)

    ctx = install(FastAPI(), enabled="ON", show_banner=False).context
    client = TestClient(GuardMiddleware(inner, ctx), base_url="http://localhost", client=("127.0.0.1", 50000))
    return client.get("/api/anything").headers


# BootUI 2.2.0 SecurityHeadersFilter: baseline headers are deduplicated on repeated host writes (drift contract §1.4)
def test_security_headers_are_not_duplicated_when_downstream_sets_them():
    headers = _guarded({"x-content-type-options": "nosniff"})
    assert headers.get_list("x-content-type-options") == ["nosniff"]
    assert headers.get_list("content-security-policy") == [CSP]
    assert headers.get_list("pragma") == ["no-cache"]


def test_a_response_that_sets_its_own_policy_keeps_it_whole():
    asset = dict(security_headers("asset"))
    headers = _guarded(asset)
    assert "pragma" not in headers  # an immutable asset never gains Pragma: no-cache
    assert headers.get_list("cache-control") == [asset["Cache-Control"]]
